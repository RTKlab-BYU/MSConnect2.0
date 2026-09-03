# Processor validation report

Validated 2026-09-03 against the shared test RAW (`CW0615_Hela_250pg_rep240_ch2_G3_DIAex480.raw`).

| Check | Result |
| --- | --- |
| DIA-NN 1.8.1 image starts and reports its version | Pass |
| DIA-NN 1.9.2 image starts and reports its version | Pass |
| DIA-NN 2.0 image starts and reports its version | Pass |
| DIA-NN 1.9.2 bounded FASTA/library smoke run | Pass through library generation; vendor RAW reader rejected the RAW in this environment |
| Upstream ProteoWizard Wine conversion | Pass; produced mzML |
| `processor-pwiz` headless conversion | Pass; produced a 14 MB mzML artifact |
| Compose configuration and Python compilation | Pass |

The ProteoWizard image now reuses the vendor Wine, Xvfb, xauth, and X11 runtime components, uses HTTPS Debian sources, and runs headlessly. The DIA-NN RAW-reader limitation remains environment-specific; production Thermo RAW handling should use the watcher conversion path before submitting mzML to DIA-NN.
