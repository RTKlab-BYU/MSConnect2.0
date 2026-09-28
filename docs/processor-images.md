# Processor image release workflow

MSConnect runs one agent per engine. The web service assigns jobs by engine
and engine version, while each processor agent advertises its capabilities at
heartbeat time. Keep processor images versioned and immutable; do not use
`:latest` for a facility node.

## Linux images

The supported initial release set is:

| Image | Engine | Compose profile | Required external runtime |
| --- | --- | --- | --- |
| `processor-pwiz` | ProteoWizard `msconvert` | `conversion` | approved ProteoWizard/Wine image |
| `processor-diann` | DIA-NN | `engines` | approved DIA-NN Linux archive and pinned version |
| `processor-fragpipe` | FragPipe | `engines` | approved FragPipe archive and site-pinned version |
| `processor-skyline` | SkylineCmd | `engines` | approved Skyline/ProteoWizard image and license acceptance |

Build all four on a machine with Docker BuildKit:

```bash
DIANN_LINUX_URL='https://site-approved.example/diann-linux.zip' \
FRAGPIPE_URL='https://github.com/Nesvilab/FragPipe/releases/download/24.0/FragPipe-24.0-linux.zip' \
DIANN_ENGINE_VERSION='2.0' \
FRAGPIPE_ENGINE_VERSION='24.0' \
./scripts/build-processor-images.sh
```

The build script refuses to run without DIA-NN and FragPipe URLs. This is
intentional: an image with a stub executable is useful for local API tests but
must never be registered as a production processing node.

Before publishing an image, verify the resolved Compose configuration and
start each agent against the target server:

```bash
docker compose --profile engines --profile conversion config
docker compose --profile engines --profile conversion up -d \
  processor-diann processor-fragpipe processor-pwiz processor-skyline
docker compose ps
```

Run the lightweight executable smoke check before registering the release:

```bash
MSCONNECT_FRAGPIPE_IMAGE='registry.example.org/msconnect/processor-fragpipe:23.0' \
./scripts/check-processor-images.sh
```

The check intentionally fails if any image is absent or if an executable is a
placeholder. The local development cache may therefore pass DIA-NN,
ProteoWizard, and Skyline while correctly failing until FragPipe is built.

The node must report healthy and advertise the expected `engine` and
`engine_version`. Record the image digest and the external runtime checksum in
the deployment release metadata. Use separate agent names when placing two
processors on one host.

## Fast-node layout

For the method-development lab, put the web service, watcher, and one
processor host on the same trusted network with the shared storage mounted at
`PROCESSOR_SHARED_STORAGE_ROOT`. For the facility, use independent Postgres
and storage per deployment, then add processor nodes as capacity requires.
The raw, results, archive, backup, and reference/library paths must be mounted
consistently on every processor that may claim the job.

## Windows-enterprise workers

`windows-enterprise` is not a Linux image. It must run as a separately
provisioned Windows worker (Windows service or scheduled task) with the
enterprise vendor runtime and licensing installed locally. It should use the
same processor-agent API and advertise `MSCONNECT_PROCESSOR_ENGINE=windows-enterprise`.
The processor registry now treats it as an external engine with an
`enterprise-handoff` adapter. Configure a site-specific `command` array and
result/artifact mappings in the registry; the job writes a handoff manifest
and executes that command on the Windows worker. Do not attempt to wrap that
runtime in the Linux Compose images above; add it to the deployment only
after its vendor license, result schema, and reboot recovery procedure are
accepted.

## Acceptance evidence

For each engine, retain:

1. image digest and external runtime checksum;
2. agent heartbeat showing engine/version;
3. one representative input and output artifact checksum;
4. processor log and runtime manifest;
5. a failed-input test proving the job is marked failed and does not remain leased.

The first release should operationally enable DIA-NN plus ProteoWizard
conversion. FragPipe, Skyline, and Windows-enterprise should remain disabled
until their corresponding evidence exists.
