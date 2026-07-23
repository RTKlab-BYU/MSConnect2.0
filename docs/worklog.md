# MSConnect Worklog

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
