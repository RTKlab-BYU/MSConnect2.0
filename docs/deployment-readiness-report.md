# MSConnect deployment-readiness report

**Review date:** 2026-09-03  
**Repository:** `main` at `4b96ffd`

## Executive assessment

MSConnect is a functional MVP/scaffold for a lightweight proteomics LIMS/SDMS. The web application, queue lifecycle, watcher, generic processor, shared-storage contract, archive metadata, QC/project data model, and operational preflight tooling are implemented and covered by automated tests. It is not yet a fully production-operational multi-instrument facility system: deployment still requires site-specific infrastructure, credentials, approved vendor runtimes, operational procedures, and several real-data integrations.

## Functional today

- Django web/API application with projects, experiments, samples, runs, raw files, processing jobs, artifacts, derivatives, protein/peptide IDs and quantification records.
- React `/app/*` surface for projects, runs, processing, monitoring, QC and settings, plus the existing Django/admin routes.
- Three-role topology: server, watcher/uploader and processor, with Compose profiles for DIA-NN, FragPipe and ProteoWizard conversion.
- Filename-first worklist matching, run-name fallback, stable-file observation, idempotent imports and raw-file checksums.
- API-authenticated watcher and processor agents with heartbeats, preflight checks, renewable processing leases, recovery of abandoned jobs, pause/drain/stop controls and restart policies.
- Generic processor execution with logs, result-table import, artifacts, derivatives and reproducibility `runtime-manifest.json` files.
- Shared storage roots for incoming, immutable raw, results, archive, backup and processor references/libraries.
- Archive/backup records, verification and restore-test commands; storage capacity reporting and stale-node email notification commands.
- DIA-NN engine profile/pipeline configuration, pinned Linux archive support for 1.8.1/1.9.2/2.0, FASTA/spectral-library metadata and build/reuse policy scaffolding.
- Headless ProteoWizard/Wine conversion image based on the approved vendor container, including Xvfb/X11 runtime support.
- Email backend/settings and notification plumbing are present; production SMTP values remain deployment-specific.
- Git hooks and GitHub CI gates for lint, Django checks, migration drift, tests and web-image build.

## Tested and validated

- Pre-push validation on commit `4b96ffd`: Ruff passed, frontend ESLint passed, Django checks passed, migration check passed, and **115 tests passed with 1 skipped**.
- Tests cover watcher ingestion, worklist matching, processing claims/leasing/recovery, archive behavior, storage reports, engine registry, settings, QC fixtures, tagged operations and complete/incomplete end-to-end fixtures.
- Compose configuration renders successfully.
- DIA-NN image launch/version checks passed for 1.8.1, 1.9.2 and 2.0.
- DIA-NN 1.9.2 generated a bounded spectral library from a 1,000-sequence human FASTA subset and wrote a report-library artifact.
- Upstream ProteoWizard vendor image converted a real Thermo RAW to mzML successfully.
- The rebuilt `processor-pwiz` image converted the same real Thermo RAW and produced a 14 MB mzML artifact.
- The real Thermo RAW was not successfully consumed directly by DIA-NN in this environment; the documented production path is vendor conversion to mzML before DIA-NN.

## Required before a fully deployed system

### Deployment and infrastructure

- Choose and provision the production shared filesystem/NAS mount, with capacity, quotas, permissions, snapshots and tested restore procedures.
- Deploy the server with durable Postgres for multi-host concurrency; SQLite is suitable only for the lightweight single-server mode.
- Build and push approved immutable images to a private registry: web, DIA-NN versions, ProteoWizard, and any FragPipe/Skyline/enterprise workers.
- Configure real secrets: Django secret key, agent tokens, SMTP credentials, database credentials, allowed hosts and CSRF origins. Do not use example/default tokens.
- Install the server, watcher and processor supervisors (systemd/Compose on Linux; Scheduled Task or service on Windows) and verify boot/reboot recovery.
- Configure TLS/reverse proxy, DNS, firewall rules, identity provider or SSO, least-privilege service accounts and audit-log retention.
- Define backup frequency, off-host replication, archive retention, disaster recovery RPO/RTO and periodic restore drills.

### Acquisition and processing

- Validate the watcher against every instrument computer and vendor directory type actually used by the facility, including partial files, network disconnects, duplicate names and power interruption recovery.
- Run a full two-experiment/20-file lifecycle with real files: worklist creation, ingest, conversion, DIA-NN search, result import, QC, archive and restore.
- Make the RAW conversion handoff explicit in production orchestration; DIA-NN direct vendor-RAW support is not validated here.
- Approve and mirror site-specific DIA-NN binaries/licenses and test memory, CPU, disk and runtime limits on the beefy processor host.
- Implement/validate automatic UniProt FASTA retrieval, naming/version pinning, checksum capture and offline fallback.
- Implement/validate first-run spectral-library generation, reuse across runs/projects, invalidation/rebuild rules and concurrency locking.
- Add real HYE, PRTC and standards imports with instrument/configuration-aware QC baselines and alert thresholds.
- Configure additional engines (targeted/Skyline, DDA/FragPipe, multiplex and enterprise Windows tools) only after their licensed runtimes and result schemas are approved.

### Operations and product gaps

- Finish the settings UI for all site controls: nodes, engines, pipelines, storage, notifications, FASTA/library policies, retention and upgrade hooks, with role-based authorization and audit history.
- Add production observability: centralized logs, metrics, dashboards, alert routing, queue-depth alerts, disk/CPU/RAM thresholds and incident runbooks.
- Exercise failure tests: server outage, worker crash, host reboot, shared filesystem outage, duplicate delivery, corrupt file, disk-full and interrupted archive.
- Complete email authentication/account recovery and verify SMTP delivery, notification templates, cooldowns and bounce handling in a real mail environment.
- Define the AI sidebar/MCP integration boundary, permissions, data redaction, provider configuration, auditability and offline/failure behavior; this is not yet a production chatbot.
- Establish release/versioning policy, signed images or digests, migration rollback strategy, CI deployment workflow and node upgrade hooks.
- Perform security, privacy, validation and regulatory review appropriate to the lab; automated tests are not a substitute for site acceptance testing.

## Recommended acceptance sequence

1. Deploy a staging server with Postgres and the production-like shared filesystem.
2. Configure SMTP, tokens, TLS and supervisors; verify reboot and outage recovery.
3. Build/register approved DIA-NN and ProteoWizard images by immutable digest.
4. Execute the real 20-file lifecycle across at least two instruments/configurations.
5. Validate FASTA/library policies, HYE/PRTC QC and archive restore.
6. Run failure-injection and security acceptance tests.
7. Promote to production only after sign-off on the runbook, backups, monitoring and recovery objectives.
