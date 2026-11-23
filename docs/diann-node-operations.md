# DIA-NN processor node operations

The default Compose service named `processor` is the pinned DIA-NN 2.7.0 +
Nextflow 26.10.6 worker. It reports engine `diann`, version `2.7.0`, and profile
`diann:2.7.0`; it reads raw files and references read-only, writes results, and
keeps Nextflow scratch data in a Docker volume. This replaces the old generic
command processor and the separate `processor-diann` profile service.

## Choose a node runtime

For a Windows processor computer, use **WSL2 with Docker Desktop's WSL
integration**. WSL2 supplies the Linux environment and mounted file shares;
Docker runs the same pinned Linux image used on the server. This keeps DIA-NN,
.NET, Java, Nextflow, the helper, and their versions together in one image.

Running DIA-NN directly inside WSL2 without Docker is technically possible, but
it requires installing and pinning DIA-NN, .NET 8, Java, Nextflow, the Python
helper, and the workflow catalog on each computer. The repository's older native
WSL scripts describe the earlier 2.2.0 arrangement. The container path is the
validated 2.7.0 setup for new nodes.

Each worker container must see the API's logical paths at `/data/raw`,
`/data/results`, and `/data/shared`. On a remote WSL2 worker, mount the server
shares in WSL (for example under `/mnt/msconnect`) and bind those host paths to
the same container paths. Raw and shared-reference mounts are read-only; results
are writable. Use Tailscale DNS or the server's Tailscale IP for the API URL.

## Pull and update a live server

Run this from the deployment checkout on the live server. Back up the database
first and review pending jobs before replacing the worker; starting a processor
lets it claim eligible queued jobs.

For a Postgres deployment, create a backup before updating:

```sh
sudo ops/backup-msconnect-postgres.sh \
  --project-dir /opt/msconnect2 \
  --env-file /opt/msconnect2/.env \
  --project-name msconnect-methodlab \
  --output /srv/msconnect-methodlab/backup/database/msconnect-pre-diann.dump
```

```sh
cd /opt/msconnect2
git status --short
git fetch origin
git switch main
git pull --ff-only origin main

scripts/check-production-env.sh /opt/msconnect2/.env
```

If the checkout has local changes, stop and preserve/reconcile them before
pulling. Keep the deployment `.env` outside Git and mode `0600`. It must contain
the API/database settings, durable mount paths, and `MSCONNECT_PROCESSOR_TOKEN`.
Set `MSCONNECT_DIANN_IMAGE` to the approved image name if it is in a registry;
otherwise Compose builds the pinned image locally from this checkout.
If the existing env file still pins DIA-NN 2.0, update `MSCONNECT_DIANN_IMAGE`
to `msconnect-processor-diann:2.7.0-nextflow` (or the matching private-registry
tag) before building.

Use the deployment's existing Compose project name, `.env`, and overlays. The
examples below use `msconnect-methodlab`:

```sh
docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  config --services

# Stop only the current processor while keeping the API and database online.
docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  stop processor

# Build the updated API and pinned DIA-NN worker, then start the server.
docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  up -d --build web nginx postgres

docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  exec web python manage.py migrate

curl -f http://127.0.0.1/readyz/
```

For TLS terminated by a separate proxy, check the public `/readyz/` URL as
well. After confirming the queue contains work you intend to run, either build
the image on the server or pull its approved registry tag, then start the
worker:

```sh
docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  build processor

# Use this instead of `build` when the approved image is already in a registry.
docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  pull processor

docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  up -d processor

docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  ps processor
docker compose -p msconnect-methodlab --env-file /opt/msconnect2/.env \
  -f docker-compose.msconnect2.server.yml -f docker-compose.production.yml \
  logs --tail=100 processor
```

The processor can also be started by the Linux systemd helper with
`ops/install-msconnect-node.sh --role processor`; its default service list is
now `processor` and therefore uses this DIA-NN image.

### Keep the existing `processor-1` record

The default service keeps the existing agent name `processor-1` unless
`DIANN_AGENT_NAME` is set. Its next heartbeat updates that row to engine
`diann`; existing job history remains attached. If you prefer a new name, set
`DIANN_AGENT_NAME` in `.env`, provision that same name in Admin → Agent setup,
and retire the old node after the new one reports healthy. Do not run the old
generic processor and the DIA-NN worker concurrently under one name.

For the built-in server worker, the container reads
`MSCONNECT_PROCESSOR_TOKEN` from `.env`. For remote workers, provision a
separate key per computer in Admin → Agent setup and keep it only in that
computer's private env file.

### Provision the server-local worker with an individual key

For a fresh node identity, create a processor in Admin → Agent setup and choose
`diann-server-01`. Put the one-time key into the server `.env` as
`MSCONNECT_PROCESSOR_TOKEN` and set `DIANN_AGENT_NAME=diann-server-01`. Keep the
file mode `0600`, then click **Ready to connect** and start the `processor`
service. On an existing deployment where `processor-1` is already registered,
either continue using its configured service token and existing name or create
a new identity and retire `processor-1` after the new node reports healthy.

## Add a remote Windows/WSL2 node

1. Install WSL2 with Ubuntu and Docker Desktop. Enable Docker Desktop's WSL
   integration for that Ubuntu distribution, then open Ubuntu from Windows and
   confirm Docker is available there:

   ```sh
   docker version
   docker compose version
   ```

2. Mount the server's storage shares from WSL at stable paths. Use a
   root-owned CIFS credentials file with restrictive permissions; do not put
   SMB credentials in the MSConnect worker env file. The setup block creates
   the mount directories if needed, but it cannot mount site shares without
   their server/share names and credentials. Check that the raw share contains
   expected files, the shared path contains approved references, and the
   results share is writable.

3. In MSConnect, open **Admin → Agent setup**, register a **DIA-NN processor
   (WSL2)**, and use a unique name such as `diann-wsl-01`. Enter the WSL mount
   roots for raw, results, and shared references. Click **Ready to connect** to
   activate the one-time key, then copy the single setup block shown by the
   page.

4. Open Ubuntu (WSL2) on the processor, paste the copied block, and run it once.
   It creates the expected mount directories, verifies the server shares are
   mounted, clones or fast-forward updates `~/MSConnect2` from GitHub `main`,
   writes the private worker env file, builds the pinned image, checks API
   authentication and storage access, and starts the processor. If a check
   fails, the script stops and prints what needs fixing; rerun the same block
   after fixing it. Confirm that the node is healthy in **Nodes & compute** and
   its engine/version are `diann` / `2.7.0`.

5. For a first operational check, queue one known DIA-NN job with an approved
   reference, watch `docker compose logs -f processor-diann`, and confirm the
   job completes with a report, log, workflow manifest, and imported results.
   The provisioned worker's Compose service is named `processor-diann` in its
   standalone worker project.

Docker Desktop must start after Windows sign-in for the worker to restart.
Enable Docker Desktop startup on sign-in, keep the WSL storage mounts available,
and check the worker project after reboot with `docker compose ps` and
`docker compose logs`.

## Native WSL2 without Docker

Native WSL2 can run `run_processor_agent --engine diann` when the pinned DIA-NN
binary, .NET 8, Java, Nextflow, helper, workflow, and catalog are installed and
visible at the configured paths. Use a separate env file and supervisor, and
run `check_agent_runtime --role processor --engine diann --write-test` before
starting. Treat this as a site-maintained deployment: verify the exact 2.7.0
workflow against representative inputs before assigning production jobs. New
nodes should use Docker Desktop + WSL2 unless the site has a specific reason to
manage these runtimes directly.
