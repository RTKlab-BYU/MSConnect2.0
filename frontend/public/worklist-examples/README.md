# Anonymized sequence examples

The MS and LC files show three instrument sequence layouts. Names, paths, methods, positions, and identifiers are demo values. Prep-QC rows are synthetic examples.

Upload the MS sequence to the project worklist importer. The LC sequence is retained with the experiment for acquisition reference. Tag roles and sample metadata directly in the MS preview; MSConnect saves those values with the sample, run, and worklist. The `-tags.csv` files are read-only examples of the intended classifications and are not an upload step.

## Tagging guide

- Choose `sample` for an experimental specimen, then enter its sample type and condition. Optional subject, matrix, species, digestion, enrichment, batch, replicate, and notes fields are stored as metadata.
- Choose `blank` or `true_blank` and provide `blank_type` to distinguish solvent, process, extraction, and other lab-defined blanks. Do not infer the distinction from a file name or path.
- Choose `qc` and provide both `qc_stage` and `qc_material`, such as `sample_preparation` and `Pooled digest`.
- HYE controls are recognized from paired A/B names. Confirm the names and shared pair label in the preview.
- `subject_id` values in the examples are pseudonymous placeholders. Use study IDs rather than direct identifiers.
