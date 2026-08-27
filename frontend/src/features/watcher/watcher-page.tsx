import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileUp,
  FlaskConical,
  Monitor,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useRef, useState, type ComponentType } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  fetchCurrentUser,
  fetchDirectUploadSessions,
  fetchProcessingJobsOverview,
  fetchProjectResearcherStatus,
  fetchProjectSummary,
  fetchProjects,
  fetchSystemHealth,
  queryKeys,
} from "@/lib/api/queries";
import { csrfToken } from "@/lib/api/client";
import { completeDirectUploadSession, createDirectUploadSession } from "@/lib/api/uploads";
import { formatBytes, formatDate } from "@/lib/format";
import { useUploadStore, type UploadFileRecord } from "@/store/upload-store";

type DeliveryMode = "watcher" | "direct";

function uploadStatusToBadge(status: UploadFileRecord["state"]) {
  if (status === "complete") return "succeeded";
  if (status === "uploading" || status === "preparing") return "running";
  if (status === "failed" || status === "blocked") return "failed";
  if (status === "ready") return "ready";
  return "queued";
}

function sessionStatusToBadge(status: string) {
  if (status === "complete") return "succeeded";
  if (status === "failed") return "failed";
  if (status === "uploading") return "running";
  if (status === "created") return "ready";
  return "queued";
}

function progress(file: UploadFileRecord) {
  if (!file.size) return 0;
  return Math.round(((file.uploadedBytes || file.preparedBytes) / file.size) * 100);
}

async function sha256(file: File) {
  const buffer = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function deliveryModeLabel(mode: DeliveryMode) {
  return mode === "watcher" ? "Watcher inbox" : "Managed raw";
}

function sessionDeliveryMode(session: { metadata: Record<string, unknown> }) {
  const mode = String(session.metadata?.delivery_mode ?? "direct").toLowerCase();
  return mode === "watcher" ? "watcher" : "direct";
}

export default function WatcherPage() {
  const [searchParams] = useSearchParams();
  const initialProjectId = searchParams.get("project") ?? "";
  const initialRunId = searchParams.get("run") ?? "none";
  const initialDeliveryMode = searchParams.get("delivery") === "direct" ? "direct" : "watcher";
  const inputRef = useRef<HTMLInputElement>(null);
  const fileObjectsRef = useRef(new Map<string, File>());
  const [projectId, setProjectId] = useState(initialProjectId);
  const [selectedRunId, setSelectedRunId] = useState(initialRunId);
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>(initialDeliveryMode);
  const files = useUploadStore((state) => state.files);
  const stageFiles = useUploadStore((state) => state.stageFiles);
  const prepareFile = useUploadStore((state) => state.prepareFile);
  const attachDirectUploadSession = useUploadStore((state) => state.attachDirectUploadSession);
  const markUploading = useUploadStore((state) => state.markUploading);
  const updateChunk = useUploadStore((state) => state.updateChunk);
  const markComplete = useUploadStore((state) => state.markComplete);
  const markFailed = useUploadStore((state) => state.markFailed);
  const markBackendBlocked = useUploadStore((state) => state.markBackendBlocked);
  const retry = useUploadStore((state) => state.retry);
  const remove = useUploadStore((state) => state.remove);
  const projectsQuery = useQuery({
    queryKey: queryKeys.projects({ page: 1, page_size: 100 }),
    queryFn: () => fetchProjects({ page: 1, page_size: 100 }),
  });
  const selectedProjectId = Number(projectId);
  const selectedProject = projectsQuery.data?.results.find((project) => project.id === selectedProjectId);
  const projectStatusQuery = useQuery({
    queryKey: queryKeys.projectResearcherStatus(selectedProjectId),
    queryFn: () => fetchProjectResearcherStatus(selectedProjectId),
    enabled: Boolean(selectedProjectId),
  });
  const projectSummaryQuery = useQuery({
    queryKey: queryKeys.projectSummary(selectedProjectId),
    queryFn: () => fetchProjectSummary(selectedProjectId),
    enabled: Boolean(selectedProjectId),
  });
  const projectJobsQuery = useQuery({
    queryKey: queryKeys.processingJobsOverview({ project: selectedProjectId }),
    queryFn: () => fetchProcessingJobsOverview({ project: selectedProjectId }),
    enabled: Boolean(selectedProjectId),
  });
  const projectSessionsQuery = useQuery({
    queryKey: queryKeys.directUploadSessions({ project: selectedProjectId, page: 1, page_size: 8 }),
    queryFn: () => fetchDirectUploadSessions({ project: selectedProjectId, page: 1, page_size: 8 }),
    enabled: Boolean(selectedProjectId),
  });
  const systemHealthQuery = useQuery({
    queryKey: queryKeys.systemHealth(),
    queryFn: fetchSystemHealth,
  });
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const currentUser = currentUserQuery.data;
  const projectRuns = projectStatusQuery.data?.runs ?? [];
  const selectedRun = projectRuns.find((row) => String(row.run.id) === selectedRunId);
  const sessions = projectSessionsQuery.data?.results ?? [];

  async function startUpload(file: UploadFileRecord) {
    const project = Number(projectId);
    const fileObject = fileObjectsRef.current.get(file.id);
    if (!project) {
      markFailed(file.id, "Select a project before starting the upload.");
      return;
    }
    if (!fileObject) {
      markFailed(file.id, "The file object is no longer available in this browser session. Select it again to upload.");
      return;
    }

    try {
      const session = await createDirectUploadSession({
        project,
        run: selectedRun ? selectedRun.run.id : null,
        filename: file.name,
        expected_filename: selectedRun?.run.expected_filename || undefined,
        size_bytes: file.size,
        content_type: file.type || "application/octet-stream",
        chunk_size_bytes: file.chunkSize,
        file_role: selectedRun?.run.file_role,
        delivery_mode: deliveryMode,
        metadata: {
          intended_filename: selectedRun?.run.expected_filename || file.name,
          delivery_mode: deliveryMode,
        },
      });
      attachDirectUploadSession(file.id, session.id, session.storage_key);
      markUploading(file.id);

      for (const part of session.upload_urls) {
        const chunk = fileObject.slice(part.start, part.end);
        updateChunk(file.id, part.part_number - 1, "uploading");
        const response = await fetch(part.url, {
          method: part.method,
          credentials: "same-origin",
          headers: {
            ...part.headers,
            "X-CSRFToken": csrfToken(),
          },
          body: chunk,
        });
        if (!response.ok) {
          throw new Error(`Upload service rejected part ${part.part_number} with status ${response.status}`);
        }
        updateChunk(file.id, part.part_number - 1, "complete", part.end - part.start);
      }

      const checksum = await sha256(fileObject);
      await completeDirectUploadSession(session.id, checksum);
      markComplete(file.id);
    } catch (error) {
      markFailed(file.id, error instanceof Error ? error.message : "Upload failed");
    }
  }

  const summary = projectSummaryQuery.data;

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Watcher" }]} />

      <PageHero
        eyebrow="Real-time ingest"
        title="Watcher console"
        description="Stream files into the watcher inbox for immediate handoff, or switch to managed raw storage when you want the browser to finish the ingest path directly."
        actions={
          selectedProject ? (
            <>
              <Button asChild variant="secondary">
                <Link to={`/projects/${selectedProject.id}`}>
                  <FlaskConical className="h-4 w-4" />
                  Open project
                </Link>
              </Button>
              <Button asChild>
                <Link to="/monitoring">
                  <Monitor className="h-4 w-4" />
                  System health
                </Link>
              </Button>
            </>
          ) : (
            <Button asChild>
              <Link to="/projects">
                <ArrowRight className="h-4 w-4" />
                Choose a project
              </Link>
            </Button>
          )
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Proteins" value={summary?.reported_protein_count ?? 0} detail="reported in project summary" />
        <MetricCard label="Peptides" value={summary?.reported_peptide_count ?? 0} detail="reported in project summary" />
        <MetricCard label="MS1" value={summary?.ms1_feature_count ?? 0} detail="feature counts ready for downstream use" />
        <MetricCard label="MS2" value={summary?.ms2_spectra_count ?? 0} detail="spectra counted from the latest processing" />
      </section>

      <Card className="overflow-hidden">
        <CardHeader className="border-b bg-secondary/20">
          <CardTitle>Stream files</CardTitle>
          <CardDescription>Select a project, decide where the file lands, and push it through the watcher or raw-storage path.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 p-5">
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => {
              if (event.target.files) {
                const staged = stageFiles(event.target.files);
                Array.from(event.target.files).forEach((file, index) => {
                  const record = staged[index];
                  if (record) fileObjectsRef.current.set(record.id, file);
                });
              }
              event.currentTarget.value = "";
            }}
          />

          <div className="grid gap-3 md:grid-cols-[minmax(240px,1fr)_minmax(240px,1fr)_minmax(220px,1fr)_auto]">
            <Select
              value={projectId || "none"}
              onValueChange={(value) => {
                setProjectId(value === "none" ? "" : value);
                setSelectedRunId("none");
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder={projectsQuery.data?.results.length ? "Select a project" : "No projects loaded"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Choose a project</SelectItem>
                {(projectsQuery.data?.results ?? []).map((project) => (
                  <SelectItem key={project.id} value={String(project.id)}>
                    {project.code} · {project.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={selectedRunId} onValueChange={setSelectedRunId} disabled={!projectRuns.length}>
              <SelectTrigger>
                <SelectValue placeholder={projectRuns.length ? "Attach to planned run" : "No planned runs loaded"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Project only</SelectItem>
                {projectRuns.map((row) => (
                  <SelectItem key={row.run.id} value={String(row.run.id)}>
                    {row.run.worklist_position ? `${row.run.worklist_position}. ` : ""}
                    {row.run.run_name}
                    {row.run.expected_filename ? ` - ${row.run.expected_filename}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={deliveryMode} onValueChange={(value) => setDeliveryMode(value as DeliveryMode)}>
              <SelectTrigger>
                <SelectValue placeholder="Select a delivery mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="watcher">Watcher inbox</SelectItem>
                <SelectItem value="direct">Managed raw</SelectItem>
              </SelectContent>
            </Select>
            <Button onClick={() => inputRef.current?.click()}>
              <FileUp className="h-4 w-4" />
              Select files
            </Button>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-2xl border bg-background/60 p-4">
              <div className="text-[11px] font-black uppercase tracking-[0.16em] text-muted-foreground">Delivery mode</div>
              <div className="mt-2 text-sm font-semibold">{deliveryModeLabel(deliveryMode)}</div>
              <p className="mt-1 text-sm text-muted-foreground">
                {deliveryMode === "watcher"
                  ? "The assembled file will stop in the incoming watcher inbox so the watcher agent can import it later."
                  : "The browser completes the ingest path immediately and writes directly to managed raw storage."}
              </p>
            </div>
            <div className="rounded-2xl border bg-background/60 p-4">
              <div className="text-[11px] font-black uppercase tracking-[0.16em] text-muted-foreground">Project context</div>
              <div className="mt-2 text-sm font-semibold">
                {selectedProject ? `${selectedProject.code} · ${selectedProject.title}` : "No project selected"}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {selectedRun ? (
                  <>
                    Targeting <span className="font-semibold text-foreground">{selectedRun.run.run_name}</span> as{" "}
                    <span className="font-semibold text-foreground">{selectedRun.run.file_role}</span>
                  </>
                ) : (
                  "Choose a planned run when you want filename matching."
                )}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Signed in as {currentUser?.username ?? "loading user"}.
              </p>
            </div>
          </div>

          {selectedRun ? (
            <div className="rounded-lg border bg-secondary/25 px-3 py-2 text-sm text-muted-foreground">
              Files will attach to <span className="font-semibold text-foreground">{selectedRun.run.run_name}</span> as{" "}
              <span className="font-semibold text-foreground">{selectedRun.run.file_role}</span>.
            </div>
          ) : null}
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>Staged files</CardTitle>
            <CardDescription>Prepare manifests, upload chunks, and watch each file move through the staged pipeline.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {files.map((file) => (
              <div key={file.id} className="grid gap-3 rounded-2xl border bg-background/60 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">{file.name}</div>
                    <div className="text-sm text-muted-foreground">
                      {formatBytes(file.size)} · {file.chunks.length} chunks · staged {formatDate(file.createdAt)}
                    </div>
                  </div>
                  <StatusBadge status={uploadStatusToBadge(file.state)} />
                </div>

                <div className="h-2 overflow-hidden rounded-full bg-secondary">
                  <div className="h-full bg-primary" style={{ width: `${progress(file)}%` }} />
                </div>

                {file.error ? (
                  <div className="flex items-center gap-2 rounded-2xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    <AlertTriangle className="h-4 w-4" />
                    {file.error}
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={() => prepareFile(file.id)} disabled={file.state === "ready"}>
                    Prepare manifest
                  </Button>
                  <Button onClick={() => startUpload(file)} disabled={file.state !== "ready"}>
                    Start upload
                  </Button>
                  <Button variant="secondary" onClick={() => markBackendBlocked(file.id)} disabled={file.state !== "ready"}>
                    Mark adapter missing
                  </Button>
                  <Button variant="secondary" onClick={() => retry(file.id)} disabled={!["failed", "blocked"].includes(file.state)}>
                    <RotateCcw className="h-4 w-4" />
                    Retry
                  </Button>
                  <Button variant="ghost" onClick={() => remove(file.id)}>
                    <Trash2 className="h-4 w-4" />
                    Remove
                  </Button>
                </div>
              </div>
            ))}
            {!files.length ? (
              <div className="rounded-2xl border border-dashed p-6 text-sm text-muted-foreground">
                Select files above to stage them here. The queue stays local until you choose a project and start the upload.
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Live project summary</CardTitle>
              <CardDescription>Counts from the selected project, updated from the latest backend summary.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              <SummaryRow label="Raw files" value={summary?.raw_file_count ?? 0} />
              <SummaryRow label="Processing jobs" value={summary?.processing_job_count ?? 0} />
              <SummaryRow label="Protein IDs" value={summary?.protein_identification_count ?? 0} />
              <SummaryRow label="Peptide IDs" value={summary?.peptide_identification_count ?? 0} />
              <SummaryRow label="MS1 features" value={summary?.ms1_feature_count ?? 0} />
              <SummaryRow label="MS2 spectra" value={summary?.ms2_spectra_count ?? 0} />
              <SummaryRow label="Reported proteins" value={summary?.reported_protein_count ?? 0} />
              <SummaryRow label="Reported peptides" value={summary?.reported_peptide_count ?? 0} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent sessions</CardTitle>
              <CardDescription>Most recent direct-upload sessions for this project.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {sessions.map((session) => {
                const mode = sessionDeliveryMode(session);
                return (
                  <div key={session.id} className="rounded-2xl border bg-background/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold">{session.filename}</div>
                        <div className="text-sm text-muted-foreground">
                          {formatBytes(session.size_bytes)} · {deliveryModeLabel(mode === "watcher" ? "watcher" : "direct")} · updated {formatDate(session.updated_at)}
                        </div>
                      </div>
                      <StatusBadge status={sessionStatusToBadge(session.status)} />
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">
                      Run: {session.run ? session.run : "Project only"} · Storage key: {session.storage_key}
                    </div>
                  </div>
                );
              })}
              {!selectedProjectId ? (
                <div className="rounded-2xl border border-dashed p-6 text-sm text-muted-foreground">
                  Choose a project to see its direct-upload sessions.
                </div>
              ) : !sessions.length ? (
                <div className="rounded-2xl border border-dashed p-6 text-sm text-muted-foreground">
                  No sessions yet for this project.
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>System data</CardTitle>
              <CardDescription>Watcher and processor health, plus readiness details for the current workspace.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="rounded-2xl border bg-background/60 p-4">
                <div className="flex items-center gap-2 font-semibold">
                  {systemHealthQuery.data?.status === "green" ? <CheckCircle2 className="h-4 w-4 text-success" /> : <AlertTriangle className="h-4 w-4 text-warning" />}
                  {systemHealthQuery.data?.status ?? "unknown"} health
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {systemHealthQuery.data?.readiness.readyz.detail ?? "Health snapshot unavailable."}
                </p>
              </div>
              <HealthRow label="Database" ok={systemHealthQuery.data?.readiness.database.ok ?? false} />
              <HealthRow label="Incoming root" ok={systemHealthQuery.data?.readiness.incoming_raw_root.ok ?? false} />
              <HealthRow label="Raw storage" ok={systemHealthQuery.data?.readiness.raw_file_storage_root.ok ?? false} />
              <HealthRow label="Results root" ok={systemHealthQuery.data?.readiness.results_root.ok ?? false} />
              <HealthRow label="Connected nodes" ok={(systemHealthQuery.data?.nodes.connected ?? 0) > 0} />
              <div className="rounded-2xl border bg-secondary/20 p-4 text-sm text-muted-foreground">
                {projectJobsQuery.data ? (
                  <>
                    <span className="font-semibold text-foreground">{projectJobsQuery.data.active}</span> active jobs and{" "}
                    <span className="font-semibold text-foreground">{projectJobsQuery.data.failed}</span> failed jobs for this project.
                  </>
                ) : (
                  "Project queue counts will appear once a project is selected."
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Next modules</CardTitle>
              <CardDescription>Not active yet, but kept visible so downstream scope stays explicit.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2">
              <RoadmapItem icon={Sparkles} title="Findings-AI" detail="Automated interpretation, annotations, and project-level synthesis." />
              <RoadmapItem icon={ShieldAlert} title="mStats" detail="Lightweight QC and operational summaries after the ingest path stabilizes." />
              <RoadmapItem icon={FlaskConical} title="Experimental design" detail="Future acquisition planning and multi-experiment project layouts." />
            </CardContent>
          </Card>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Processing focus</CardTitle>
          <CardDescription>Keep this slice simple: per-sample DIA-NN, then protein and peptide counts with MS1, MS2, and system context.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border bg-background/60 p-4 text-sm">
            <div className="font-semibold">1. Stream</div>
            <p className="mt-1 text-muted-foreground">Files enter the watcher from the browser or a watched inbox.</p>
          </div>
          <div className="rounded-2xl border bg-background/60 p-4 text-sm">
            <div className="font-semibold">2. Process</div>
            <p className="mt-1 text-muted-foreground">Each sample gets DIA-NN, then counts and spectra are surfaced in the project view.</p>
          </div>
          <div className="rounded-2xl border bg-background/60 p-4 text-sm">
            <div className="font-semibold">3. Expand</div>
            <p className="mt-1 text-muted-foreground">QC stays later. Downstream modules remain visible but intentionally out of the critical path.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between rounded-xl border bg-background/60 px-3 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function HealthRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-xl border bg-background/60 px-3 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={ok ? "font-semibold text-success" : "font-semibold text-warning"}>{ok ? "OK" : "Attention"}</span>
    </div>
  );
}

function RoadmapItem({
  icon: Icon,
  title,
  detail,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  detail: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border bg-background/60 p-4 text-sm">
      <Icon className="mt-0.5 h-4 w-4 text-primary" />
      <div>
        <div className="font-semibold">{title}</div>
        <div className="mt-1 text-muted-foreground">{detail}</div>
      </div>
    </div>
  );
}
