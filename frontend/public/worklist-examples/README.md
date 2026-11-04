# Anonymized sequence worklist examples

The paired MS and LC files use the vendor sequence columns. Their file names, paths, methods, positions, and sample identifiers are demo values. The bracketed and preamble examples are curated from distinct export layouts. The prep-QC rows are synthetic demonstrations, not role assignments inferred from source path codes.

Upload the MS sequence, its matching LC sequence, and the matching `-tags.csv` file together. The annotation file joins on the exact `File Name` value (written as `expected_filename`). Rows whose vendor `Sample Type` is `Unknown` need an explicit role.

## Tagging guide

- `file_role=sample` means a biological or experimental specimen. Put the group in `condition`; use `sample_type` for its material description.
- Use `file_role=blank` or `true_blank` for the appropriate blank category and describe its lab-specific meaning in `blank_type`. Do not infer this distinction from a file name or path alone.
- Use `file_role=qc` with `qc_stage` and `qc_material`; `sample_preparation` and `instrument` are shown in the synthetic example.
- HYE injections use `file_role=hye`, `qc_program=hye`, sample names `HYE-A` and `HYE-B`, and one shared `hye_pair_label`.
- `subject_id` values in these examples are pseudonymous placeholders. Avoid patient names or other direct identifiers.

`condition`, `sample_type`, `blank_type`, `qc_stage`, `qc_material`, `prep_batch`, `replicate`, `subject_id`, and `notes` are captured as sample/run metadata; the structured role and HYE fields populate MSConnect's existing worklist tags.
