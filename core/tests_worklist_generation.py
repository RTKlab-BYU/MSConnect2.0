from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from core.services.worklist_generation import (
    GeneratedWorklist,
    WorklistGenerationError,
    generate_vendor_worklists,
    generated_worklist_rows,
)


class WorklistGenerationBoundaryTests(SimpleTestCase):
    def test_missing_workbook_is_rejected_before_optional_dependencies_load(self):
        with TemporaryDirectory() as output_directory:
            with self.assertRaises(WorklistGenerationError):
                generate_vendor_worklists(Path(output_directory) / "missing.xlsx", Path(output_directory))

    def test_generated_ms_csv_becomes_run_ground_truth_rows(self):
        with TemporaryDirectory() as output_directory:
            output = Path(output_directory) / "plate_MS.csv"
            output.write_text(
                "Bracket Type=4,,,,,\n"
                "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\n"
                "Sample,run_001.raw,/data,method_a,A1,2\n",
                encoding="utf-8",
            )
            generated = GeneratedWorklist(
                input_path=Path(output_directory) / "input.xlsx",
                output_directory=Path(output_directory),
                ms_path=output,
                lc_path=Path(output_directory) / "plate_LC.csv",
                filenames=("run_001.raw",),
                condition_names=("healthy",),
                replicate_numbers=(1,),
            )
            rows = generated_worklist_rows(generated)
            self.assertEqual(rows[0]["expected_filename"], "run_001.raw")
            self.assertEqual(rows[0]["metadata"]["ms_method"], "method_a")
