# MSConnect `/app/` Review Guide

Use this guide to review the React MSConnect application before we retire the legacy Django-template UI under `/ui/*`.

The React app is intentionally mounted at `/app/*` for now so it can coexist with the existing `/ui/*` pages while we validate the workflows with real lab users.

## Current Review Scope

Review these React routes:

- `/app/projects` - top-level project list and project search.
- `/app/qc` - scientist-facing QC workspace where HYE A/B injections form a derived pseudo-project for system suitability and longitudinal trend review, with PRTC scaffolded as the next QC program.
- `/app/projects/<project_id>` - primary project workspace. This is the main SDMS/LIMS view for raw files, processing jobs, analysis visualization, samples, runs, and acquisitions.
- `/app/monitoring` - run, job, node, and raw-file operations dashboard.
- `/app/processing` - detailed node, queue, retry, and pipeline processing console.
- `/app/uploads` - direct-to-object-storage upload manager using Django-issued signed upload URLs.
- `/app/settings` - administrative/settings placeholder for users, instruments, protocols, and pipelines.

The current root URL still redirects to `/ui/projects`, and the React shell still exposes a "Legacy UI" link. Keep those during review. Remove or redirect them only after the `/app/` experience is accepted.

## Local Review Setup

From the repo root:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo_showcase
```

Build the React app into Django static files:

```sh
cd frontend
npm install
npm run build
cd ..
```

Start Django:

```sh
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Log in through Django session auth:

```text
http://127.0.0.1:8000/accounts/login/
```

Demo reviewer account:

```text
Username: demo-pi
Password: DemoPass-2026!
```

Then open:

```text
http://127.0.0.1:8000/app/projects
```

## Review Flow

1. Start at `/app/projects`.
   - Confirm projects are the top-level navigation layer.
   - Search by project code/title.
   - Open the demo project workspace.

2. Review `/app/projects/<project_id>`.
   - Confirm the project header, summary counters, and status charts make the project state clear.
   - Review the `Raw Files` tab first. This is the highest-growth SDMS table and should feel fast, searchable, and readable.
   - Review the `Processing Jobs` tab. Confirm the state model is visible: `queued`, `assigned`, `running`, `complete`, `failed`, and `retrying`.
   - Confirm jobs show the assigned node when available.
   - Review `Samples`, `Runs`, and `Acquisitions` as nested project records, not top-level navigation.
   - Review `Analysis Viz` as a Phase 2 prototype. The current chromatogram is demo-backed; production trace data should come from signed object-storage URLs.

3. Review `/app/qc`.
   - Confirm HYE A/B pair health is readable as a derived QC pseudo-project without making HYE a standalone project.
   - Confirm project and worklist filters narrow the QC results correctly.
   - Confirm PRTC is visibly planned but does not imply production readiness yet.

4. Review `/app/monitoring`.
   - Confirm active jobs, failed jobs, node health, raw-file counts, and backlog trend are understandable at a glance.
   - Confirm nodeless queued jobs and node-assigned jobs are visually distinct enough for troubleshooting throughput.

5. Review `/app/processing`.
   - Confirm node inventory, queue state, retries, and failed jobs are understandable without falling back to `/ui/*`.
   - Confirm project-scoped drill-down from `/app/projects/<project_id>` lands in the right filtered processing view.

6. Review `/app/uploads`.
   - Confirm the flow asks Django for signed upload URLs, then uploads chunks directly to object storage.
   - Local development may show upload errors until `OBJECT_STORAGE_UPLOAD_BASE_URL` points at a real signed storage target.
   - Confirm failure/retry/progress states are understandable without relying on backend logs.

7. Review shell behavior.
   - Use the left navigation at workstation widths.
   - Use `Cmd-K` or `Ctrl-K` for fast project/navigation search.
   - Toggle light/dark mode and confirm status badges, tables, and charts remain legible.

## Acceptance Criteria Before Retiring `/ui/*`

The `/app/` interface can become the only user-facing UI when these are true:

- Project workspace covers the daily lab workflow: raw files, processing jobs, samples, runs, and acquisitions.
- Raw-file and processing-job tables remain responsive with realistic record counts.
- Intake, review, and promotion workflows either exist in `/app/` or have an approved replacement path.
- Direct upload behavior is validated against the real object-storage provider.
- Job/node state is validated with realistic assigned, retrying, failed, and completed jobs.
- Lab users can complete common tasks without needing the "Legacy UI" link.
- Admin-only work remains available through Django admin or a dedicated `/app/settings` screen.

## Planned Migration Away From `/ui/*`

After signoff, migrate in small, reversible steps:

1. Change the root redirect in `msconnect/urls.py` from `/ui/projects` to `/app/projects`.
2. Remove the "Legacy UI" link from `frontend/src/components/shell/app-shell.tsx`.
3. Add redirects from old `/ui/*` routes to their `/app/*` equivalents where a direct equivalent exists.
4. Keep `/admin/`, `/api/`, `/accounts/`, and `/api-auth/` available.
5. Remove obsolete templates and static files under `ui/templates/ui/**` and `ui/static/ui/**` only after the redirected routes are verified.
6. Update internal docs, bookmarks, and lab workstation shortcuts to use `/app/projects`.

## Notes For Phase 2 Data Work

- Chromatogram and spectrum APIs should return metadata plus signed object-storage URLs, not large inline JSON arrays.
- Under roughly 50k points per trace with only a handful of overlays, uPlot is expected to be enough.
- For 100k-1M+ points per trace or many overlays, add server-side or worker-side min/max downsampling before rendering.
- UMAP and heatmap views should remain dynamically sized because matrix and cell counts will vary by experiment.
