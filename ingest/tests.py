from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import (
    Experiment,
    Facility,
    IngestionFailure,
    Lab,
    Project,
    RawFile,
    RawFileStatus,
    Run,
    Sample,
    University,
)
from ingest.services import (
    discover_raw_paths,
    hash_path,
    import_raw_path,
    parse_filename_metadata,
    record_ingestion_failure,
)

User = get_user_model()


class RawFileIngestTests(TestCase):
    def test_import_raw_file_copies_and_records_metadata(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as storage_dir:
            source = Path(source_dir) / "sample.raw"
            source.write_bytes(b"raw-data")

            result = import_raw_path(source, storage_root=Path(storage_dir))

            raw_file = RawFile.objects.get()
            self.assertTrue(result.created)
            self.assertEqual(raw_file.filename, "sample.raw")
            self.assertEqual(raw_file.status, RawFileStatus.IMPORTED)
            self.assertEqual(raw_file.size_bytes, len(b"raw-data"))
            self.assertTrue(Path(raw_file.storage_path).exists())

    def test_import_is_idempotent_by_checksum_and_size(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as storage_dir:
            source = Path(source_dir) / "sample.raw"
            source.write_bytes(b"raw-data")

            first = import_raw_path(source, storage_root=Path(storage_dir))
            second = import_raw_path(source, storage_root=Path(storage_dir))

            self.assertTrue(first.created)
            self.assertTrue(second.skipped)
            self.assertEqual(RawFile.objects.count(), 1)

    def test_directory_hash_includes_relative_file_names(self):
        with TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first.d"
            second = Path(tmp_dir) / "second.d"
            first.mkdir()
            second.mkdir()
            (first / "a.bin").write_bytes(b"same")
            (second / "b.bin").write_bytes(b"same")

            first_hash, first_size = hash_path(first)
            second_hash, second_size = hash_path(second)

            self.assertEqual(first_size, second_size)
            self.assertNotEqual(first_hash, second_hash)

    def test_discovery_does_not_walk_inside_vendor_directory(self):
        with TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir)
            vendor_dir = source / "sample.d"
            vendor_dir.mkdir()
            (vendor_dir / "nested.raw").write_bytes(b"nested")

            discovered = list(discover_raw_paths(source, recursive=True))

            self.assertEqual(discovered, [vendor_dir])

    def test_filename_metadata_parsing_extracts_run_and_date(self):
        metadata = parse_filename_metadata(Path("/tmp/SampleA_run07_20260701.raw"))
        self.assertEqual(metadata["run_name"], "run07")
        self.assertEqual(metadata["acquisition_date"], "20260701")

    def test_import_can_match_run_by_name(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as storage_dir:
            user = User.objects.create_user(username="pi", password="password123")
            university = University.objects.create(name="BYU")
            facility = Facility.objects.create(university=university, name="Core", slug="core")
            lab = Lab.objects.create(facility=facility, name="Lab A", slug="lab-a")
            project = Project.objects.create(lab=lab, title="Project A", code="P-A", pi=user)
            experiment = Experiment.objects.create(project=project, name="Exp 1")
            sample = Sample.objects.create(experiment=experiment, name="Sample A")
            run = Run.objects.create(sample=sample, run_name="run07")

            source = Path(source_dir) / "SampleA_run07_20260701.raw"
            source.write_bytes(b"raw-data")

            result = import_raw_path(source, storage_root=Path(storage_dir), match_run_by_name=True)

            self.assertTrue(result.created)
            raw_file = RawFile.objects.get()
            self.assertEqual(raw_file.run_id, run.id)

    def test_import_can_match_run_by_expected_filename(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as storage_dir:
            user = User.objects.create_user(username="pi", password="password123")
            university = University.objects.create(name="BYU")
            facility = Facility.objects.create(university=university, name="Core", slug="core")
            lab = Lab.objects.create(facility=facility, name="Lab A", slug="lab-a")
            project = Project.objects.create(lab=lab, title="Project A", code="P-A", pi=user)
            experiment = Experiment.objects.create(project=project, name="Exp 1")
            sample = Sample.objects.create(experiment=experiment, name="Blank")
            run = Run.objects.create(
                sample=sample,
                run_name="COHORT_DIA_100_001_BLANK",
                expected_filename="COHORT_DIA_100_001_BLANK.raw",
            )

            source = Path(source_dir) / "COHORT_DIA_100_001_BLANK.raw"
            source.write_bytes(b"raw-data")

            result = import_raw_path(source, storage_root=Path(storage_dir), match_run_by_name=True)

            self.assertTrue(result.created)
            raw_file = RawFile.objects.get()
            self.assertEqual(raw_file.run_id, run.id)

    def test_record_ingestion_failure_creates_and_increments_seen_count(self):
        missing = Path("/tmp/nonexistent-file.raw")

        first = record_ingestion_failure(missing, "missing")
        second = record_ingestion_failure(missing, "missing again")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(IngestionFailure.objects.count(), 1)
        updated = IngestionFailure.objects.get(pk=first.pk)
        self.assertEqual(updated.seen_count, 2)
        self.assertEqual(updated.failure_reason, "missing again")
