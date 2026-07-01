from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import (
    Experiment,
    Facility,
    PeptideIdentification,
    PeptideQuant,
    ProcessingJob,
    ProcessingPipeline,
    Project,
    ProteinIdentification,
    ProteinQuant,
    RawFile,
    Run,
    Sample,
    University,
)
from ingest.result_import import import_result_tables

User = get_user_model()


class ResultTableImportTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="pi", password="password123")
        university = University.objects.create(name="BYU")
        facility = Facility.objects.create(university=university, name="Core", slug="core")
        lab = facility.labs.create(name="Lab A", slug="lab-a")
        project = Project.objects.create(lab=lab, title="Project A", code="P-A", pi=user)
        experiment = Experiment.objects.create(project=project, name="Exp 1")
        sample = Sample.objects.create(experiment=experiment, name="Sample A")
        run = Run.objects.create(sample=sample, run_name="run01")
        raw = RawFile.objects.create(
            run=run,
            source_path="/tmp/source.raw",
            storage_path="/tmp/storage.raw",
            filename="source.raw",
            checksum_sha256="a" * 64,
            size_bytes=10,
            status="imported",
        )
        pipeline = ProcessingPipeline.objects.create(name="FragPipe", version="1.0")
        self.job = ProcessingJob.objects.create(run=run, pipeline=pipeline, raw_file=raw)

    def test_imports_protein_and_peptide_results(self):
        with TemporaryDirectory() as tmp_dir:
            protein_file = Path(tmp_dir) / "proteins.csv"
            protein_file.write_text(
                (
                    "accession,organism,label,value,unit,score,q_value,coverage_percent,peptide_count\n"
                    "P12345,Homo sapiens,abundance,1234.5,intensity,55.5,0.01,42.0,6\n"
                ),
                encoding="utf-8",
            )

            peptide_file = Path(tmp_dir) / "peptides.tsv"
            peptide_file.write_text(
                (
                    "sequence\tmodified_sequence\tcharge\tlabel\tvalue\tscore\tq_value\tretention_time_seconds\tmz\n"
                    "PEPTIDE\tPEP[+80]TIDE\t2\tabundance\t321.5\t44.0\t0.02\t1200.0\t550.2\n"
                ),
                encoding="utf-8",
            )

            summary = import_result_tables(job=self.job, protein_table=protein_file, peptide_table=peptide_file)

        self.assertEqual(summary["protein_quant_rows"], 1)
        self.assertEqual(summary["protein_ident_rows"], 1)
        self.assertEqual(summary["peptide_quant_rows"], 1)
        self.assertEqual(summary["peptide_ident_rows"], 1)
        self.assertEqual(ProteinQuant.objects.count(), 1)
        self.assertEqual(ProteinIdentification.objects.count(), 1)
        self.assertEqual(PeptideQuant.objects.count(), 1)
        self.assertEqual(PeptideIdentification.objects.count(), 1)

    def test_reimport_updates_existing_quant_and_ident_rows(self):
        with TemporaryDirectory() as tmp_dir:
            protein_file = Path(tmp_dir) / "proteins.csv"
            protein_file.write_text(
                (
                    "accession,organism,label,value,score,q_value\n"
                    "P12345,Homo sapiens,abundance,100.0,50.0,0.05\n"
                ),
                encoding="utf-8",
            )

            import_result_tables(job=self.job, protein_table=protein_file)

            protein_file.write_text(
                (
                    "accession,organism,label,value,score,q_value\n"
                    "P12345,Homo sapiens,abundance,222.0,99.0,0.001\n"
                ),
                encoding="utf-8",
            )
            import_result_tables(job=self.job, protein_table=protein_file)

        self.assertEqual(ProteinQuant.objects.count(), 1)
        self.assertEqual(ProteinIdentification.objects.count(), 1)
        quant = ProteinQuant.objects.get()
        ident = ProteinIdentification.objects.get()
        self.assertEqual(quant.value, 222.0)
        self.assertEqual(ident.score, 99.0)
        self.assertEqual(ident.q_value, 0.001)

