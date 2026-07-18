# MSConnect Worklog

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
- `/ui/*` still remains available and is not yet retired.

### Deferred / next session

- Replace the legacy root redirect and remove the `Legacy UI` link only after `/app` signoff.
- Decide whether intake/review/promotion should move into `/app` before `/ui/*` is shut off.
- Add real PRTC data contracts and acceptance thresholds.
- Replace placeholder signed upload targets with the real object-storage signing implementation in the target environment.
