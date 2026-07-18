# Frontend Phase 2 Notes

Phase 1 intentionally keeps the React app pointed at the main Django server with Django session auth and CSRF.

Deferred items:

- Token/JWT auth for browser-to-node or browser-to-service communication. Revisit only if React needs to call uploader, instrument, or processing nodes outside the main Django origin.
- High-throughput LC-MS and single-cell visualization. Current charts are small Recharts wrappers and should be replaceable with canvas/WebGL renderers.
- Real-time event streams. Phase 1 models uploads and processing as status states and uses TanStack Query polling.
- Distributed uploader and processing node architecture. API access is centralized in `frontend/src/lib/api/` so resource routing can later move behind one adapter layer.
- Server-side table scale work beyond additive DRF filters. Raw files and processing jobs now support opt-in pagination/search/filtering, but very large deployments may need specialized read models.

## Phase 2 Current Backend Contract

- Streaming transport: none currently detected. The monitoring UI uses a centralized polling fallback with jittered intervals.
- Processing nodes: `ProcessingNode` records exist and expose `name`, `node_type`, `status`, `endpoint_url`, `last_heartbeat_at`, `settings`, and `metadata`.
- Processing jobs: `ProcessingJob` exposes `queued`, `assigned`, `running`, `complete`, `failed`, and `retrying`, plus nullable `node` and read-only `node_name`.
- QC aggregates: `/api/qc/overview/` and `/api/qc/details/` expose HYE pair-level QC metrics today and a stable empty scaffold for `program=prtc`.
- Uploads: `/api/direct-uploads/` creates a direct-upload session with signed per-chunk object-storage URLs. Browser uploads go directly to storage, then `/api/direct-uploads/<id>/complete/` records the completed `RawFile`.
- Scientific arrays: dense chromatogram, spectrum, UMAP, and heatmap data are not exposed by models or API endpoints yet. Production chromatogram/spectrum APIs should return metadata plus signed object-storage URLs for compact binary payloads, not inline JSON arrays. The current chromatogram view uses isolated synthetic trace data derived from scalar raw-file telemetry so renderer performance and selection behavior can be validated without locking in a data contract.

## Open Questions Before Production Viz

- Expected chromatogram and spectrum point counts per run and number of overlaid traces per view. As a practical starting estimate, a 45-minute LC-MS XIC trace at 1-5 Hz MS1 sampling is roughly 2,700-13,500 points, but profile spectra or extracted high-frequency traces can be 100k-1M+ points.
- Expected expression matrix dimensions for single-cell heatmaps.
- Expected dimensionality-reduction point counts and whether lasso/brush selection must round-trip to backend immediately.
- Signed storage URL provider and compact trace payload format: Arrow, Parquet, flat binary arrays, or a small custom binary envelope.
