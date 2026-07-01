from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase

from core.models import RawFile, RawFileStatus
from ingest.services import discover_raw_paths, hash_path, import_raw_path


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

