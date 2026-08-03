# MSConnect Worklog

## 2026-08-03

### Completed

- Seeded and documented four demo accounts for the live walkthrough: `demo-admin`, `demo-pi`, `demo-researcher`, and `demo-collaborator`.
- Added a live `system-health` API and admin dashboard warning surface for readiness, node heartbeat status, failed jobs, and unmatched raw files.
- Reworked the dashboard landing page into a role-aware welcome view with quick stats, a "what you missed" summary, and direct paths into Projects, Uploads, and Monitoring.
- Fixed the live `/app/dashboard` blank-page issue by enabling DEBUG staticfiles serving so Django on port `8000` can serve the built React bundle directly.
- Confirmed the live stack is accessible again after rebuilding the web container and reloading the app routes.

### Verified

- `./.venv/bin/python manage.py check`
- `./.venv/bin/python manage.py test core.tests_api_permissions.ApiPermissionTests.test_system_health_reports_warnings_for_connected_and_downed_nodes core.tests_api_permissions.ApiPermissionTests.test_qc_overview_and_details_return_hye_metrics`
- `docker compose exec -T web python manage.py shell -c "...demo role snapshot..."`
- `docker compose exec -T web python manage.py shell -c "...dashboard/js/css 200 checks..."`

### Current review state

- `demo-admin` can see `/api/system-health/`; collaborator, researcher, and PI users remain restricted from the admin health endpoint.
- The dashboard is now visibly branded and role-aware instead of appearing as a blank shell.
- `archive-worker`, `watcher`, and `processor` can still need follow-up runtime review depending on the currently seeded demo data and raw-file paths.

### Deferred / next session

- Bring the DIA-NN processor container to a fully visible smoke-test state.
- Tighten collaborator submission validation and make the collaborator intake flow stricter.
- Continue splitting views by user role so admin, PI, researcher, and collaborator surfaces are more distinct.
- Expand the processor health and node-control UX further once the DIA-NN path is stable.

## 2026-07-30

### Completed

- Added the central processor registry for versioned engine profiles, shared reference assets, and engine settings under `PROCESSOR_SHARED_STORAGE_ROOT`.
- Built and validated a real DIA-NN 2.0 Linux processor image from the DIA-NN 2.0 Academia Linux ZIP, including .NET 8 and runtime dependency handling.
- Registered `diann/2.0` in shared processor storage and started the `processor-diann` Compose service with engine version/profile metadata.
- Added a real Skyline 26.1 processor image based on the ProteoWizard/Skyline vendor-license container, with MSConnect Python runtime and a `SkylineCmd` Wine wrapper.
- Registered `skyline/26.1.0` in shared processor storage and started the `processor-skyline` Compose service.
- Added Skyline PRTC postprocessing: Skyline report CSV to normalized peptide table, PRTC stats JSON, imported peptide quant rows, and saved `ProcessingJob.stats`.
- Added upload-time PRTC routing through `MSCONNECT_PRTC_SKYLINE_PIPELINE_ID`, while leaving routine sample/HYE/library runs on the existing worklist pipeline path.
- Replaced the placeholder PRTC QC API/UI with Skyline PRTC run summaries, peptide counts, missing/out-of-tolerance peptides, area, and retention-shift metrics.
- Updated processor docs, env examples, Compose profiles, and added a PRTC 15-peptide Skyline settings template.

### Verified

- `docker build -f docker/processor/diann.Dockerfile --build-arg DIANN_VERSION=2.0 --build-arg DIANN_LINUX_URL=https://github.com/vdemichev/DiaNN/releases/download/2.0/DIA-NN-2.0-Academia-Linux.zip -t msconnect-processor-diann:2.0 .`
- `docker run --rm msconnect-processor-diann:2.0 diann`
- `docker compose --profile engines build processor-skyline`
- `docker run --rm msconnect-processor-skyline:26.1 python manage.py check`
- `docker run --rm msconnect-processor-skyline:26.1 SkylineCmd --help`
- `docker compose --profile engines run --rm --no-deps processor-skyline SkylineCmd --version`
- `docker compose run --rm --no-deps web python manage.py processor_registry validate-engine --engine skyline --version 26.1.0 --require-image`
- `docker compose --profile engines up -d web nginx watcher processor-diann processor-skyline`
- `docker compose ps web nginx watcher processor-diann processor-skyline`
- `docker compose exec processor-skyline python manage.py agent_healthcheck --role processor`
- `docker compose exec watcher python manage.py agent_healthcheck --role watcher`
- `curl -I http://localhost:8080/app/qc?program=prtc`
- `ruff check core/processing/postprocess.py core/agents/processor.py core/management/commands/run_processor_agent.py core/processing/adapters.py core/api.py core/tests_processor.py core/tests_api_permissions.py`
- `.venv/bin/python manage.py test`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `docker compose -f docker-compose.yml -f compose.engines.example.yml config --quiet`

### Current review state

- Local live stack is up with `web`, `nginx`, `watcher`, `processor-diann`, and `processor-skyline` healthy.
- Built image IDs: `msconnect-processor-diann:2.0` -> `sha256:e1b89b2a6108b2258a520378971381c42bd0c82aa78251db736b9572342f2078`; `msconnect-processor-skyline:26.1` -> `sha256:e9daf2898471cfdef16c69998dc4df77556b60cb16a78718df98a6b11fb308c3`.
- `shared/config/processor-registry.json` is local runtime state and is intentionally not committed.
- Skyline PRTC processing is code-complete but still needs the lab-approved `prtc-15.sky`, real 15 peptide definitions, and a created `Skyline PRTC` pipeline ID configured in `MSCONNECT_PRTC_SKYLINE_PIPELINE_ID`.

### Deferred / next session

- Register the real `skyline_document/prtc-15`, replace the example PRTC peptide settings with lab-approved sequences/transitions, create the production `Skyline PRTC` pipeline, and run a real PRTC raw/mzML upload through watcher -> Skyline -> QC UI.
- Add a UI/admin action for selecting the active PRTC Skyline pipeline instead of configuring `MSCONNECT_PRTC_SKYLINE_PIPELINE_ID` by environment variable.
- Run true vendor-engine jobs for FragPipe and enterprise workers once site-approved installers/images are available.

## 2026-07-29

### Completed

- Added a tagged operations smoke fixture and verifier for multi-project sample, HYE, PRTC, library, blank, and wash run flows.
- Proved the watcher-to-processor path in Docker with generated incoming files, matched worklist runs, role/QC tag propagation, raw-storage import, queued jobs, completed jobs, artifacts, runtime manifests, and imported protein/peptide quants.
- Added lab-drive archive and backup support without S3/MinIO: configurable archive/backup roots, capacity thresholds, zip archive creation, checksum verification, restore verification, and per-copy redundancy tracking.
- Added `RawFileArchiveCopy` so each logical raw archive can record independent physical archive and backup copies with path, status, checksum, size, root, and verification timestamp.
- Added storage/operator commands for archiving, archive verification, capacity reporting, processor workspace cleanup, engine-specific fixture setup, and consolidated operations reports.
- Added Compose wiring for `archive-worker` and `processor-skyline`, while keeping `processor-diann`, generic `processor`, watcher, web, and nginx flows intact.
- Added real-engine worklist/pipeline fixture setup for DIA-NN and Skyline jobs so files placed in `incoming/` can route to `diann` and `skyline` processor nodes when site-approved binaries/images and assets are available.
- Updated README, Make targets, environment templates, admin/API routes, and operational tests for the new archive/backup and engine-routing workflows.

### Verified

- `docker compose build web archive-worker`
- `docker compose config --services`
- `docker compose --profile engines --profile conversion config --services`
- `docker compose run --rm --no-deps web python manage.py makemigrations --check --dry-run`
- `docker compose run --rm --no-deps web python manage.py test core.tests_operational`
- `docker compose run --rm --no-deps web python manage.py test`
- `docker compose up -d web nginx`
- `docker compose exec web python manage.py check`
- `docker compose exec web python manage.py storage_capacity_report --projected-files 120 --average-raw-gb 4`
- `docker compose run --rm archive-worker python manage.py archive_raw_files --raw-file-id 154`
- `docker compose run --rm archive-worker python manage.py archive_raw_files --raw-file-id 155`
- `docker compose exec web python manage.py verify_archives --raw-file-id 154 --restore-test`
- `docker compose exec web python manage.py verify_archives --raw-file-id 155 --restore-test`
- `docker compose exec web python manage.py generate_operations_report --output /app/data/operations-report-final.txt --tail 8`

### Current review state

- Docker storage reporting shows the current local Docker-mounted filesystem at warning threshold, which validates the capacity alerting path.
- Two small tagged raw files were archived and verified with both archive and backup copies; active raw-storage copies were intentionally retained.
- `archive-worker` can run one-shot or loop mode and records failures without deleting originals.
- `processor-skyline` is wired as an engine-profile service, but real Skyline execution still depends on a site-approved Skyline/SkylineCmd image and valid `.sky` document.
- `processor-diann` is already wired, but real DIA-NN execution still depends on a site-approved DIA-NN binary/image and valid FASTA/library settings.

### Deferred / next session

- Provide real DIA-NN and Skyline assets and run true vendor-engine jobs through the new engine-specific fixture.
- Add first-class UI views for storage capacity, archive copies, and restore/verification status.
- Define retention rules for when verified archived raw files may become cold-only and when active raw-storage copies can be removed.

## 2026-07-28

### Completed

- Added the post-login `/app/dashboard` project portfolio view with system stats, attention summaries, recent project report cards, and login redirect defaults.
- Integrated the Findings AI collaboration workflow as a capability app with per-project workspace preparation, indexing, Claude command/walkthrough metadata, and shared/personal storage modes.
- Expanded project workspaces with selected-run queueing and sample-level continuous report pages for run, raw file, processing, protein, peptide, artifact, and derivative context.
- Extended processor support for DIA-NN, FragPipe, Skyline, Spectronaut, Proteome Discoverer, and enterprise handoff adapters with runtime manifests, version capture, shared-storage metadata, and processor smoke tests.
- Added `/app/processing/admin` for live processor inventory, IP address, heartbeat age, health, storage roots, settings/metadata inspection, and admin controls for pause, resume, drain, restart, stop, and mark-offline.
- Added `/app/admin` as the system-wide admin dashboard with portfolio metrics, feature links, live processor health, heartbeat summaries, processor boot recipes, and an end-to-end readiness runbook.
- Added web liveness/readiness endpoints, authenticated agent ping, agent preflight checks, heartbeat marker healthchecks, Docker Compose healthchecks, and end-to-end smoke fixture creation/verification commands.
- Updated README and processor docs with startup, network preflight, shared-storage, Windows worker, and full smoke-test runbooks.
- Implemented the first three-machine operations slice with engine-aware processor job claiming, explicit HYE/PRTC/true-blank run roles, `qc_program` tagging, raw-file archive tracking, and role-specific deployment env templates.
- Updated worklist import and project workspace parsing so vendor role strings such as HYE, PRTC, and true blank normalize into canonical run/worklist metadata while preserving HYE dashboard compatibility.
- Added `docs/three-machine-deployment.md` for the server, uploader/watcher, and processor-node topology, including shared-storage contracts and the cross-host smoke-test sequence.

### Verified

- `.venv/bin/python manage.py check`
- `docker compose config --quiet`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `.venv/bin/ruff check msconnect/health.py core/agents/client.py core/agents/diagnostics.py core/api.py core/urls.py core/management/commands/check_agent_runtime.py core/management/commands/agent_healthcheck.py core/management/commands/create_e2e_smoke_fixture.py core/management/commands/verify_e2e_smoke_fixture.py core/management/commands/run_watcher_agent.py core/management/commands/run_processor_agent.py core/tests_api_permissions.py core/tests_operational.py`
- `.venv/bin/python manage.py test core.tests_api_permissions core.tests_operational core.tests_processor`
- `.venv/bin/python manage.py test core.tests_api_permissions.HealthEndpointTests core.tests_api_permissions.AgentApiTests.test_agent_ping_reports_authenticated_role`
- `.venv/bin/python manage.py test core.tests_operational core.tests_api_permissions.HealthEndpointTests core.tests_api_permissions.AgentApiTests.test_agent_ping_reports_authenticated_role`
- `.venv/bin/python manage.py test core.tests_processor`
- `.venv/bin/python manage.py makemigrations --check --dry-run`
- `.venv/bin/python manage.py test`
- `.venv/bin/python manage.py test core.tests_api_permissions.AgentApiTests core.tests_processor`
- `.venv/bin/python manage.py test core.tests_api_permissions.ApiPermissionTests.test_pre_acquisition_setup_creates_expected_worklist_and_processing_plan core.tests_api_permissions.AgentApiTests`
- `.venv/bin/ruff check core/api.py core/tests_api_permissions.py core/admin.py`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

### Current review state

- `/app/dashboard` is the authenticated landing page.
- `/app/admin` is the system-wide operations hub.
- `/app/processing/admin` is the focused processor control surface.
- The default Docker LAN readiness flow is documented and implemented, but the live Docker stack smoke sequence has not been executed in this session.
- Processor controls are applied between jobs and heartbeats; running vendor subprocesses are not interrupted mid-run.
- Jobs with `parameters.adapter` or `parameters.required_engine` now require a compatible processor node type; legacy generic command pipelines remain claimable by the default processor for smoke tests.
- Raw-file archive state is modeled and exposed for operators, but the actual zip/restore worker automation is still pending.
- Whole-repo Ruff still has unrelated pre-existing lint failures in findings-workflow and processor smoke utility files; touched Python files pass Ruff.

### Deferred / next session

- Run the full documented Docker smoke sequence against a fresh Compose stack and record the live result.
- Add production supervisor examples for Windows processors, such as Task Scheduler or service runner wrappers.
- Add real vendor-engine validation jobs once site-licensed DIA-NN, FragPipe, Skyline, Spectronaut, and Proteome Discoverer installations are available.
- Expand health/readiness into deployment monitoring alerts when production infrastructure is chosen.
- Add actual archive/restore worker commands that create and validate zip archives from `RawFileArchive` records.

## 2026-07-23

### Completed

- Cleaned the Docker runtime back to the four-service app shape: `web`, `watcher`, `processor`, and `nginx`.
- Added automatic processing-job queueing when the watcher imports a raw file matched to a pre-acquisition worklist run.
- Added a local executable demo command to generated DIA-NN processing plans so the processor can complete smoke jobs and import result tables without DIA-NN installed.
- Added a processing adapter layer for command, DIA-NN, FragPipe, ProteoWizard/msconvert, and enterprise handoff runners.
- Added raw-file derivative tracking for mzML/mzMLb/MGF, spectrum indexes, previews, and vendor metadata.
- Added spectra/chromatogram APIs and a React `/app/spectra` viewer that reads indexed mzML-derived previews.
- Added optional Compose profiles and Dockerfiles for DIA-NN, FragPipe, and ProteoWizard processor runners while keeping the default four-service stack unchanged.

### Verified

- `docker compose up -d --build web watcher processor nginx`
- `docker compose up -d --remove-orphans web watcher processor nginx`
- `docker compose run --rm watcher python manage.py run_watcher_agent --once --match-run-by-name`
- `docker compose run --rm processor python manage.py run_processor_agent --once`
- Smoke project `SMOKE-DOCKER-0723B` moved from expected raw filename to imported raw file, queued job, complete processor job, processed run/raw statuses, and imported protein/peptide quant rows.
- `/app/projects` returned `200 OK` through nginx at `127.0.0.1:8080`.
- `/app/spectra` returned `200 OK` through nginx at `127.0.0.1:8080`.
- `.venv/bin/python manage.py test core.tests_api_permissions.AgentApiTests.test_watcher_import_queues_processing_job_for_pre_acquisition_run core.tests_api_permissions.AgentApiTests.test_processor_claim_start_and_complete_job`
- `.venv/bin/python manage.py test core.tests_api_permissions.AgentApiTests.test_processor_complete_records_derivative_and_spectra_api_reads_index core.tests_api_permissions.AgentApiTests.test_watcher_import_queues_processing_job_for_pre_acquisition_run core.tests_api_permissions.AgentApiTests.test_processor_claim_start_and_complete_job`
- `.venv/bin/ruff check core/api.py core/agents/processor.py core/processing/adapters.py core/management/commands/run_processor_agent.py core/models.py core/admin.py core/tests_api_permissions.py`
- `npm run build`

## 2026-07-18

### Completed

- Fixed localhost CSRF trust for login through `localhost:8080` and simplified the login page to match the cleaner MSConnect UI direction.
- Completed the intended `/app` migration path by retiring the experimental UI route, adding route fallbacks, and preserving project/workspace navigation.
- Rebuilt the React UI around a simpler sans-serif visual system, shared page hero/metric components, cleaner cards/tables/tabs, and less crowded production pages.
- Added a pre-acquisition project setup flow that creates projects, experiments, samples, planned runs, acquisition worklists, HYE QC injections, expected raw filenames, and a DIA-NN processing plan before LC-MS acquisition.
- Expanded the setup flow into a researcher-friendly wizard with project basics, pasteable sample metadata, 96/384-well plate review, saved LC-MS configuration selection, organism presets, optional FASTA/SPECLIB upload labels, and final review.
- Updated the backend setup API to accept `sample_rows`, plate metadata, organism presets, managed reference asset metadata, processing presets, and selected `InstrumentConfiguration` while keeping the old count-based smoke path compatible.
- Added server-side metadata capture for plate/well position, sample condition, source-table fields, HYE pseudo-project/QC context, watcher match keys, reference assets, and initial export targets.
- Restarted the local Docker stack with `web`, `watcher`, `processor`, and `nginx`; opened `/app/projects` on localhost for review.

### Verified

- `ruff check .`
- `npm run build`
- `docker compose build web`
- `docker compose run --rm web python manage.py check`
- `docker compose run --rm web python manage.py test core.tests_api_permissions.ApiPermissionTests.test_pre_acquisition_setup_creates_expected_worklist_and_processing_plan core.tests_api_permissions.ApiPermissionTests.test_pre_acquisition_setup_accepts_sample_rows_plate_and_reference_presets`
- `docker compose up -d --force-recreate web watcher processor nginx`
- Internal nginx route check returned `200 OK` for `/app/projects`.

### Current review state

- `/app/projects` is the main starting point for pre-acquisition setup.
- The new wizard can generate a smoke-test worklist from minimal sample metadata: `sample_id` and `condition`.
- HYE is not a separate project; HYE injections are interspersed as QC entries and marked with pseudo-project metadata for downstream QC/statistics.
- Managed FASTA/SPECLIB support is represented as resolved server-side reference asset metadata; actual binary upload/storage wiring is still pending.
- The watcher can continue matching incoming raw files by expected filename generated before acquisition.

### Deferred / next session

- Wire real FASTA/SPECLIB upload storage and reference asset versioning instead of storing upload filenames/placeholders.
- Generate downloadable Thermo/MS and LC worklist export files from `WorklistEntry` rows.
- Add drag/reorder interactions to the plate map; current v1 auto-fills and visually reviews wells.
- Add automatic processing-job creation when watcher imports a raw file that matches a planned run.
- Add project-level rollup jobs after run-level DIA-NN completion and define the supercomputer handoff contract.
- Commit the current UI rebuild and pre-acquisition wizard work in clean, reviewable commits.

## 2026-07-17

### Completed

- Split the deployment shape into repo-embedded `web`, `watcher`, and `processor` services while keeping a single shared application image.
- Added bearer-token agent authentication and agent-only API endpoints for heartbeat, raw-file import registration, ingestion-failure reporting, and processing job claim/start/complete/fail flows.
- Added long-running watcher and processor management commands plus shared agent client/runtime helpers.
- Reworked Compose, env examples, Docker image layout, Make targets, and README deployment notes for the new service topology.
- Added tag-triggered Docker Hub publish workflow for `v*.*.*` releases.
- Added test coverage for agent auth, watcher idempotent import behavior, ingestion failure reporting, and processor claim/complete result-import flow.

### Verified

- `.venv/bin/python manage.py check`
- `.venv/bin/python manage.py test core.tests_api_permissions ingest.tests ingest.tests_result_import`
- `ruff check core msconnect ingest`
- `docker compose config`

### Current review state

- Main server responsibilities are now isolated from the watcher and processor runtime loops.
- Watched-share ingestion is deployable as its own service and reports back through the main API instead of writing directly through a long-running DB-bound process.
- Processing jobs can now be claimed and completed by a separate processor agent using the existing `ProcessingJob` and `ProcessingPipeline` models.
- Deployment remains Compose-first and repo-local, with one image and service-specific commands.

### Deferred / next session

- Add a concrete seeded example of `ProcessingPipeline.parameters` so processor execution can be demoed end-to-end without manual pipeline setup.
- Decide whether watcher import should also enqueue `ProcessingJob` creation automatically or remain an explicit operator action.
- Add health endpoints or container health checks for `web`, `watcher`, and `processor`.
- Replace placeholder direct-upload object-storage settings with the real target environment implementation.

## 2026-07-16

### Completed

- Added top-level React navigation and routes for `/app/qc` and `/app/processing`.
- Built a dedicated QC workspace where HYE system-suitability injections are grouped as a derived pseudo-project with project/worklist filtering and pair-level pass, warning, and failed states.
- Scaffolded a PRTC tab in the QC workspace so standards can be added without changing navigation or layout.
- Added read-only QC aggregate APIs at `/api/qc/overview/` and `/api/qc/details/`.
- Expanded processing jobs with read-only project, run, raw-file, and pipeline display fields needed for global queue views.
- Built a dedicated Processing page for node inventory, queue state, retries, failed jobs, and project drill-down.
- Added `View QC` and `View Processing` links from the project workspace.
- Updated the `/app` review guide and Phase 2 notes to reflect the new surfaces.

### Verified

- `python manage.py check`
- `ruff check core/api.py core/tests_api_permissions.py`
- `npm run lint`
- `npm run build`
- `python manage.py test`

### Current review state

- `/app/projects` remains the primary record-centric workspace.
- `/app/qc` is ready for HYE pseudo-project review now.
- `/app/processing` is ready for node and queue review now.
- `/app/monitoring` remains the compact global operations summary.
- `/ui/*` is retired as a rendered interface and now redirects to `/app/*`.

### Deferred / next session

- Add first-class intake/review/promotion flows to `/app` when that workflow becomes active again.
- Add real PRTC data contracts and acceptance thresholds.
- Replace placeholder signed upload targets with the real object-storage signing implementation in the target environment.
