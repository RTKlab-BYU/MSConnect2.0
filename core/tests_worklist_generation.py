from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from core.services.worklist_generation import (
    GeneratedWorklist,
    WorklistGenerationError,
    generate_vendor_worklists,
    generated_worklist_rows,
    validate_generated_hye_pairs,
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

    def test_generated_vendor_hye_names_become_matching_pair_tags(self):
        with TemporaryDirectory() as output_directory:
            output = Path(output_directory) / "plate_MS.csv"
            output.write_text(
                "Bracket Type=4,,,,,\n"
                "Sample Type,File Name,Path,Instrument Method,Position,Inj Vol\n"
                "Unknown,Example_HYE_A_15Cycles_Blo1_BC3_Rep1_Ch1_Run1,ExampleData,Method,BC3,1\n"
                "Unknown,Example_HYE_B_15Cycles_Blo1_BC20_Rep1_Ch1_Run2,ExampleData,Method,BC20,1\n"
                "Unknown,Example_HYE_A_15Cycles_Blo1_BC3_Rep_Ch2_Run3,ExampleData,Method,BC3,1\n"
                "Unknown,Example_HYE_B_15Cycles_Blo1_BC20_Rep_Ch2_Run4,ExampleData,Method,BC20,1\n",
                encoding="utf-8",
            )
            generated = GeneratedWorklist(
                input_path=Path(output_directory) / "input.xlsx",
                output_directory=Path(output_directory),
                ms_path=output,
                lc_path=Path(output_directory) / "plate_LC.csv",
                filenames=(),
                condition_names=(),
                replicate_numbers=(),
            )
            rows = generated_worklist_rows(generated)
            validate_generated_hye_pairs(rows)
            self.assertEqual([row["sample_name"] for row in rows], ["HYE-A", "HYE-B", "HYE-A", "HYE-B"])
            self.assertTrue(all(row["qc_program"] == "hye" for row in rows))
            self.assertEqual(rows[0]["hye_pair_label"], rows[1]["hye_pair_label"])
            self.assertEqual(rows[2]["hye_pair_label"], rows[3]["hye_pair_label"])
            self.assertNotEqual(rows[0]["hye_pair_label"], rows[2]["hye_pair_label"])

    def test_generated_unpaired_hye_controls_are_rejected(self):
        with self.assertRaisesRegex(WorklistGenerationError, "exactly one A and one B"):
            validate_generated_hye_pairs([
                {"file_role": "hye", "qc_program": "hye", "hye_pair_label": "HYE-01", "sample_name": "HYE-A"},
            ])
