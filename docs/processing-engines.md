# Processing Engines

MSConnect keeps the Django app image separate from heavy or licensed search engines. The default `processor` service remains a generic command runner. Engine-specific workers can be enabled with Compose profiles when the site has approved binaries and licenses.

## Runner Images

- `processor-diann`: DIA-NN worker. Build with `DIANN_LINUX_URL` pointing at the site-approved Linux DIA-NN archive.
- `processor-fragpipe`: FragPipe worker. Build with `FRAGPIPE_URL` pointing at the site-approved FragPipe archive.
- `processor-pwiz`: ProteoWizard conversion worker. This image derives from the ProteoWizard/Skyline vendor-license-acceptance container and exposes `msconvert`.
- Enterprise tools such as Proteome Discoverer and Spectronaut should run as external licensed workers. Configure their pipelines with `adapter` set to `proteome-discoverer`, `spectronaut`, or `enterprise-handoff` plus a site-specific `command` array.

Example builds:

```sh
docker compose --profile engines build processor-diann processor-fragpipe
docker compose --profile conversion build processor-pwiz
```

Example runtime:

```sh
docker compose --profile engines --profile conversion up -d web watcher processor processor-diann processor-fragpipe processor-pwiz nginx
```

## Pipeline Adapter Parameters

Legacy pipelines can continue using `parameters.command`. New pipelines should prefer `parameters.adapter`.

```json
{
  "adapter": "msconvert",
  "executable": "msconvert",
  "output_format": "mzML",
  "filters": ["peakPicking true 1-"]
}
```

```json
{
  "adapter": "fragpipe",
  "workflow": "/data/reference/workflows/fragpipe.workflow",
  "threads": 8,
  "ram_gb": 32,
  "data_type": "DDA"
}
```

```json
{
  "adapter": "diann",
  "executable": "diann",
  "library": "/data/reference/project.speclib",
  "fasta": "/data/reference/project.fasta",
  "options": ["--threads", "8"]
}
```

## Spectra Viewing

The web viewer reads spectrum index derivatives, not vendor RAW files directly. A conversion worker should create an mzML or mzMLb derivative and an index JSON derivative for the raw file.

Index JSON shape:

```json
{
  "spectra": [
    {
      "id": "scan=1",
      "index": 0,
      "scan_number": 1,
      "ms_level": 2,
      "retention_time_seconds": 42.5,
      "precursor_mz": 678.9,
      "base_peak_mz": 445.2,
      "base_peak_intensity": 12000,
      "tic": 45000,
      "peaks": [[445.2, 12000], [500.1, 3000]]
    }
  ],
  "chromatograms": {
    "tic": [[42.5, 45000]],
    "bpc": [[42.5, 12000]]
  }
}
```

Set `MSCONNECT_AUTO_QUEUE_SPECTRA_CONVERSION=1` only after a working conversion runner is available.
