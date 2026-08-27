import { useMutation, useQuery } from "@tanstack/react-query";
import { BarChart3, BrainCircuit, CheckCircle2, Copy, FileUp, FolderKanban, RefreshCw, Save, Settings2 } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  fetchCurrentUser,
  fetchExperiment,
  fetchExperiments,
  fetchProjectResearcherStatus,
  fetchProjectDiannPreflight,
  fetchFindingsWorkspace,
  fetchProcessingJobs,
  indexFindingsWorkspace,
  importProjectWorklist,
  prepareFindingsWorkspace,
  queueProjectRuns,
  queueProjectReadyRuns,
  rerunLatestDiannBatch,
  queryKeys,
  updateRun,
  updateWorklistEntry,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import { formatBytes, formatDate } from "@/lib/format";
import type { FindingsWorkspace, ProcessingJob, ProjectResearcherRun, WorklistImportRow } from "@/lib/api/types";
import { isOperatorRole } from "@/lib/ui-surface";

const roleOptions = ["sample", "qc", "hye", "prtc", "library", "blank", "true_blank", "wash", "calibration"] as const;
const runStatusOptions = ["planned", "acquired", "imported", "processed", "failed"] as const;

type EditDraft = {
  runId: number;
  worklistEntryId: number | null;
  runName: string;
  position: string;
  expectedFilename: string;
  fileRole: string;
  status: string;
  hyePairLabel: string;
  notes: string;
};

type DiannProcessStep = {
  key: string;
  label: string;
  detail: string;
  status: string;
};

export default function ProjectWorkspacePage() {
  const projectId = Number(useParams().projectId);
  const experimentId = Number(useParams().experimentId);
  const isExperimentRoute = Number.isFinite(experimentId);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [worklistOpen, setWorklistOpen] = useState(false);
  const [worklistName, setWorklistName] = useState("Imported LC-MS worklist");
  const [worklistRows, setWorklistRows] = useState<WorklistImportRow[]>([]);
  const [worklistError, setWorklistError] = useState("");
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>([]);
  const [workspaceMode, setWorkspaceMode] = useState<"personal" | "shared">("personal");
  const [dataStrategy, setDataStrategy] = useState<"manifest" | "symlink">("manifest");
  const [rerunNotice, setRerunNotice] = useState("");
  const statusParams = isExperimentRoute ? { experiment: experimentId } : undefined;
  const statusQueryKey = queryKeys.projectResearcherStatus(projectId, statusParams);
  const preflightQueryKey = queryKeys.projectDiannPreflight(projectId, statusParams);

  const statusQuery = useQuery({
    queryKey: statusQueryKey,
    queryFn: () => fetchProjectResearcherStatus(projectId, statusParams),
    enabled: Number.isFinite(projectId),
    refetchInterval: 30_000,
  });
  const preflightQuery = useQuery({
    queryKey: preflightQueryKey,
    queryFn: () => fetchProjectDiannPreflight(projectId, statusParams),
    enabled: Number.isFinite(projectId),
    refetchInterval: 60_000,
  });
  const experimentsQuery = useQuery({
    queryKey: queryKeys.projectExperiments(projectId),
    queryFn: () => fetchExperiments({ project: projectId, page: 1, page_size: 100 }),
    enabled: Number.isFinite(projectId),
  });
  const experimentQuery = useQuery({
    queryKey: queryKeys.experiment(experimentId),
    queryFn: () => fetchExperiment(experimentId),
    enabled: isExperimentRoute,
  });
  const processingJobsQuery = useQuery({
    queryKey: queryKeys.projectProcessingJobs(projectId),
    queryFn: () => fetchProcessingJobs({ project: projectId, page: 1, page_size: 50 }),
    enabled: Number.isFinite(projectId),
    refetchInterval: 10_000,
  });
  const findingsQuery = useQuery({
    queryKey: queryKeys.findingsWorkspace(projectId),
    queryFn: () => fetchFindingsWorkspace(projectId),
    enabled: Number.isFinite(projectId),
  });
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const data = statusQuery.data;
  const project = data?.project;
  const isOperator = isOperatorRole(currentUserQuery.data?.global_role);
  const experiment = experimentQuery.data ?? data?.experiment ?? null;
  const experiments = experimentsQuery.data?.results ?? [];
  const runs = data?.runs ?? [];
  const selectedRun = runs.find((row) => row.run.id === selectedRunId) ?? runs[0];
  const readyToProcess = runs.filter((row) => row.raw_file && !row.processing_job);
  const failedRows = runs.filter((row) => row.processing_job?.status === "failed" || row.run.status === "failed");
  const selectedRows = runs.filter((row) => selectedRunIds.includes(row.run.id));
  const selectedReadyRows = selectedRows.filter((row) => row.raw_file && !row.processing_job);
  const allSelected = Boolean(runs.length) && selectedRunIds.length === runs.length;
  const latestDiannJob = useMemo(
    () =>
      (processingJobsQuery.data?.results ?? []).find(
        (job) => job.required_engine.toLowerCase().includes("diann") || job.pipeline_name.toLowerCase().includes("diann"),
      ) ??
      (processingJobsQuery.data?.results ?? [])[0] ??
      null,
    [processingJobsQuery.data?.results],
  );
  const diannProcess = useMemo<DiannProcessStep[]>(
    () => buildDiannProcessSteps(preflightQuery.data?.is_valid ?? false, readyToProcess.length, latestDiannJob),
    [latestDiannJob, preflightQuery.data?.is_valid, readyToProcess.length],
  );
  const pageEyebrow = isExperimentRoute ? "Experiment workspace" : "Project workspace";
  const pageTitle = experiment?.name ?? project?.code ?? "Loading project";
  const pageDescription = isExperimentRoute
    ? experiment
      ? `${project?.code ?? "Project"} · ${experiment.hypothesis || "Single acquisition series"}`
      : "Loading experiment."
    : project?.title ?? "Retrieving project status.";

  const importMutation = useMutation({
    mutationFn: () =>
      importProjectWorklist(projectId, {
        worklist_name: worklistName,
        experiment_name: experiment?.name ?? undefined,
        rows: worklistRows,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: statusQueryKey });
      await queryClient.invalidateQueries({ queryKey: preflightQueryKey });
      await queryClient.invalidateQueries({ queryKey: queryKeys.projectExperiments(projectId) });
      setWorklistOpen(false);
      setWorklistRows([]);
      setWorklistError("");
    },
    onError: (error) => setWorklistError(error instanceof Error ? error.message : "Could not import worklist."),
  });
  const queueMutation = useMutation({
    mutationFn: () => queueProjectReadyRuns(projectId, isExperimentRoute ? experimentId : undefined),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: statusQueryKey });
    },
  });
  const queueSelectedMutation = useMutation({
    mutationFn: () => queueProjectRuns(projectId, selectedReadyRows.map((row) => row.run.id), isExperimentRoute ? experimentId : undefined),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: statusQueryKey });
      setSelectedRunIds([]);
    },
  });
  const rerunBatchMutation = useMutation({
    mutationFn: () => rerunLatestDiannBatch(projectId),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: statusQueryKey });
      await queryClient.invalidateQueries({ queryKey: queryKeys.projectSummary(projectId) });
      setRerunNotice(
        `Converted ${result.converted} file${result.converted === 1 ? "" : "s"} and requeued ${result.rerun} DIA-NN job${result.rerun === 1 ? "" : "s"}.`,
      );
    },
  });
  const editMutation = useMutation({
    mutationFn: async (draft: EditDraft) => {
      await updateRun(draft.runId, {
        run_name: draft.runName,
        status: draft.status as ProjectResearcherRun["run"]["status"],
      });
      if (draft.worklistEntryId) {
        await updateWorklistEntry(draft.worklistEntryId, {
          position: Number(draft.position),
          expected_filename: draft.expectedFilename,
          file_role: draft.fileRole,
          hye_pair_label: draft.hyePairLabel,
          notes: draft.notes,
        });
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: statusQueryKey });
      setEditDraft(null);
    },
  });
  const prepareWorkspaceMutation = useMutation({
    mutationFn: () => prepareFindingsWorkspace(projectId, { mode: workspaceMode, data_strategy: dataStrategy }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.findingsWorkspace(projectId) });
    },
  });
  const indexWorkspaceMutation = useMutation({
    mutationFn: (workspaceId: number) => indexFindingsWorkspace(workspaceId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.findingsWorkspace(projectId) });
    },
  });

  const health = data?.system_health.status ?? "yellow";
  const healthLabel = health === "green" ? "System green" : health === "red" ? "System red" : "System yellow";
  const healthClass = health === "green" ? "border-emerald-300 bg-emerald-50 text-emerald-900" : health === "red" ? "border-rose-300 bg-rose-50 text-rose-900" : "border-amber-300 bg-amber-50 text-amber-950";

  function onWorklistFile(file: File | undefined) {
    if (!file) return;
    setWorklistError("");
    file
      .text()
      .then((text) => setWorklistRows(parseWorklistText(text)))
      .catch((error) => setWorklistError(error instanceof Error ? error.message : "Could not read worklist file."));
  }

  function submitWorklist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!worklistRows.length) {
      setWorklistError("Choose a CSV or TSV worklist before importing.");
      return;
    }
    importMutation.mutate();
  }

  function startEdit(row: ProjectResearcherRun) {
    setEditDraft({
      runId: row.run.id,
      worklistEntryId: row.worklist_entry_id,
      runName: row.run.run_name,
      position: String(row.run.worklist_position ?? ""),
      expectedFilename: row.run.expected_filename,
      fileRole: row.run.file_role,
      status: row.run.status,
      hyePairLabel: row.run.hye_pair_label,
      notes: "",
    });
    setSelectedRunId(row.run.id);
  }

  function toggleRunSelected(runId: number) {
    setSelectedRunIds((current) => (current.includes(runId) ? current.filter((id) => id !== runId) : [...current, runId]));
  }

  function toggleAllSelected() {
    setSelectedRunIds(allSelected ? [] : runs.map((row) => row.run.id));
  }

  return (
    <div className="grid gap-4">
      <Breadcrumbs
        items={[
          { label: "Projects", href: "/projects" },
          { label: project?.code ?? "Project", href: project ? `/projects/${projectId}` : "/projects" },
          ...(isExperimentRoute ? [{ label: experiment?.name ?? "Experiment" }] : []),
        ]}
      />

      <PageHero
        eyebrow={pageEyebrow}
        title={pageTitle}
        description={pageDescription}
        actions={
          <>
            {project ? <StatusBadge status={project.status} /> : null}
            {experiment ? (
              <span className="inline-flex h-9 items-center rounded-md border bg-secondary/40 px-3 text-sm font-bold text-foreground">
                Experiment selected
              </span>
            ) : null}
            <span className={`inline-flex h-9 items-center rounded-md border px-3 text-sm font-bold ${healthClass}`}>{healthLabel}</span>
            {!isExperimentRoute && experiments.length ? (
              <Button asChild variant="secondary">
                <Link to={`/projects/${projectId}/experiments/${experiments[0].id}`}>Open latest experiment</Link>
              </Button>
            ) : null}
            {isExperimentRoute ? (
              <Button asChild variant="secondary">
                <Link to={`/projects/${projectId}`}>Project overview</Link>
              </Button>
            ) : null}
            <Dialog open={worklistOpen} onOpenChange={setWorklistOpen}>
              <DialogTrigger asChild>
                <Button>
                  <FileUp className="h-4 w-4" />
                  Import worklist
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[90vh] max-w-4xl overflow-auto">
                <DialogHeader>
                  <DialogTitle>Import LC-MS worklist</DialogTitle>
                  <DialogDescription>
                    Upload a CSV or TSV worklist to create or update the run ground truth.
                    {isExperimentRoute ? " The import will attach to the selected experiment." : " The import will attach to the default experiment for this project."}
                  </DialogDescription>
                </DialogHeader>
                <form className="grid gap-4" onSubmit={submitWorklist}>
                  <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                    <Input value={worklistName} onChange={(event) => setWorklistName(event.target.value)} />
                    <Input type="file" accept=".csv,.tsv,.txt" onChange={(event) => onWorklistFile(event.target.files?.[0])} />
                  </div>
                  <WorklistPreview rows={worklistRows} />
                  {worklistError ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{worklistError}</div> : null}
                  <div className="flex justify-end gap-2 border-t pt-3">
                    <Button type="button" variant="secondary" onClick={() => setWorklistOpen(false)}>
                      Cancel
                    </Button>
                    <Button type="submit" disabled={importMutation.isPending || !worklistRows.length || (isExperimentRoute && !experiment)}>
                      {importMutation.isPending ? "Importing..." : "Import worklist"}
                    </Button>
                  </div>
                </form>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label={isExperimentRoute ? "Experiment" : "Project Status"} value={isExperimentRoute ? experiment?.name ?? "-" : project?.status ?? "-"} detail={isExperimentRoute ? "single acquisition series" : "research workflow"} />
        <MetricCard label="Runs" value={data?.summary.run_count ?? "-"} detail={isExperimentRoute ? "in this experiment" : "planned/acquired"} />
        <MetricCard label="Raw Files" value={data?.summary.raw_file_count ?? "-"} detail={`${data?.summary.missing_raw_file_count ?? 0} missing`} />
        <MetricCard label="Queue" value={data?.system_health.active_jobs ?? "-"} detail="active jobs" />
        <MetricCard label="Failed" value={failedRows.length} detail="runs needing review" />
        <MetricCard label="Ready" value={readyToProcess.length} detail="uploaded, not queued" />
      </section>
      {experiments.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Experiments</CardTitle>
            <CardDescription>Projects can hold multiple experiments. Each experiment is a single acquisition and upload series.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {experiments.map((item) => (
              <Link
                key={item.id}
                to={`/projects/${projectId}/experiments/${item.id}`}
                className={`rounded-2xl border p-4 transition-colors hover:bg-secondary/45 ${
                  isExperimentRoute && experiment?.id === item.id ? "border-primary bg-primary/5" : "bg-background/70"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold">{item.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{item.hypothesis || "No hypothesis recorded"}</div>
                  </div>
                  <span className="rounded-full border bg-background px-2 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-muted-foreground">
                    Experiment
                  </span>
                </div>
                <div className="mt-3 text-xs text-muted-foreground">
                  Updated {formatDate(item.updated_at)} · {item.started_on || "No start date"}
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      ) : null}
      {rerunNotice ? <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-950">{rerunNotice}</div> : null}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>DIA-NN preflight</CardTitle>
              <CardDescription>Resolved settings and command options that will be used for this project before upload or queueing.</CardDescription>
            </div>
            <Button variant="secondary" onClick={() => preflightQuery.refetch()} disabled={preflightQuery.isFetching}>
              <RefreshCw className="h-4 w-4" />
              {preflightQuery.isFetching ? "Refreshing..." : "Refresh preflight"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="grid gap-3">
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-lg border bg-background/60 p-3">
                <div className="text-xs font-bold uppercase text-muted-foreground">Source</div>
                <div className="mt-1 font-semibold">{preflightQuery.data?.source_label ?? "Loading preflight..."}</div>
                <div className="mt-1 text-sm text-muted-foreground">{preflightQuery.data?.source_detail ?? "Resolve the pipeline snapshot used for upload."}</div>
              </div>
              <div className="rounded-lg border bg-background/60 p-3">
                <div className="text-xs font-bold uppercase text-muted-foreground">Preset / version</div>
                <div className="mt-1 font-semibold">{preflightQuery.data?.processing_preset || "-"}</div>
                <div className="mt-1 text-sm text-muted-foreground">DIA-NN {preflightQuery.data?.diann_version || "-"}</div>
              </div>
              <div className="rounded-lg border bg-background/60 p-3">
                <div className="text-xs font-bold uppercase text-muted-foreground">Speclib mode</div>
                <div className="mt-1 font-semibold">{speclibModeLabel(preflightQuery.data?.speclib_mode)}</div>
                <div className="mt-1 text-sm text-muted-foreground">{speclibModeDetail(preflightQuery.data?.speclib_mode)}</div>
              </div>
            </div>
            <div className="rounded-lg border bg-background/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-bold uppercase text-muted-foreground">Resolved settings</div>
                  <div className="text-sm text-muted-foreground">This is the effective pipeline snapshot after site performance tags are applied.</div>
                </div>
                <StatusBadge status={preflightQuery.data?.is_valid ? "complete" : "warning"} />
              </div>
              <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-100">
                <code>{JSON.stringify(preflightQuery.data?.settings ?? {}, null, 2)}</code>
              </pre>
            </div>
          </div>
          <div className="grid gap-3">
            <div className="rounded-lg border bg-background/60 p-3">
              <div className="text-xs font-bold uppercase text-muted-foreground">Performance tags</div>
              <pre className="mt-2 overflow-auto rounded-lg bg-background p-3 text-xs">
                <code>{JSON.stringify(preflightQuery.data?.performance_tags ?? {}, null, 2)}</code>
              </pre>
            </div>
            <div className="rounded-lg border bg-background/60 p-3">
              <div className="text-xs font-bold uppercase text-muted-foreground">Experimental tags</div>
              <pre className="mt-2 overflow-auto rounded-lg bg-background p-3 text-xs">
                <code>{JSON.stringify(preflightQuery.data?.experimental_tags ?? {}, null, 2)}</code>
              </pre>
            </div>
            <div className="rounded-lg border bg-background/60 p-3">
              <div className="text-xs font-bold uppercase text-muted-foreground">Validation</div>
              {preflightQuery.data?.validation_errors?.length ? (
                <ul className="mt-2 grid gap-2 text-sm text-destructive">
                  {preflightQuery.data.validation_errors.map((error) => (
                    <li key={error} className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2">
                      {error}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="mt-2 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-950">
                  No validation errors. The preflight snapshot is ready for upload or processing.
                </div>
              )}
            </div>
            <div className="rounded-lg border bg-background/60 p-3">
              <div className="text-xs font-bold uppercase text-muted-foreground">Command options</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {(preflightQuery.data?.options ?? []).length ? (
                  preflightQuery.data?.options.map((option) => (
                    <span key={option} className="rounded-full border bg-background px-3 py-1 font-mono text-xs">
                      {option}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">No explicit DIA-NN options resolved.</span>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>DIA-NN process</CardTitle>
              <CardDescription>Live project execution status, from preflight through queueing to the current DIA-NN job state.</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={latestDiannJob ? latestDiannJob.status : readyToProcess.length ? "queued" : "planned"} />
              {isOperator ? (
                <Button asChild variant="secondary">
                  <Link to={`/processing?project=${projectId}&pipeline=all&status=all&active=true`}>
                    <BarChart3 className="h-4 w-4" />
                    Open queue
                  </Link>
                </Button>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="grid gap-3">
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
              {diannProcess.map((step: DiannProcessStep) => {
                const { key, ...rest } = step;
                return <ProcessStepCard key={key} {...rest} />;
              })}
            </div>
          </div>
          <div className="grid gap-3">
            <div className="rounded-2xl border bg-background/80 p-4">
              <div className="text-xs font-bold uppercase text-muted-foreground">Latest DIA-NN job</div>
              {latestDiannJob ? (
                <div className="mt-3 grid gap-2 text-sm">
                  <div className="rounded-lg border bg-background px-3 py-2">
                    <div className="text-xs font-bold uppercase text-muted-foreground">Status</div>
                    <div className="mt-1 font-semibold">{latestDiannJob.status}</div>
                  </div>
                  <div className="rounded-lg border bg-background px-3 py-2">
                    <div className="text-xs font-bold uppercase text-muted-foreground">Pipeline</div>
                    <div className="mt-1 font-semibold">{latestDiannJob.pipeline_name} {latestDiannJob.pipeline_version}</div>
                  </div>
                  <div className="rounded-lg border bg-background px-3 py-2">
                    <div className="text-xs font-bold uppercase text-muted-foreground">Raw file</div>
                    <div className="mt-1 break-all font-mono text-xs">{latestDiannJob.raw_file_filename}</div>
                  </div>
                  <div className="rounded-lg border bg-background px-3 py-2">
                    <div className="text-xs font-bold uppercase text-muted-foreground">Node</div>
                    <div className="mt-1 font-semibold">{latestDiannJob.node_name || "Unassigned"}</div>
                  </div>
                  <div className="rounded-lg border bg-background px-3 py-2">
                    <div className="text-xs font-bold uppercase text-muted-foreground">Started / finished</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatDate(latestDiannJob.started_at)} · {formatDate(latestDiannJob.finished_at)}
                    </div>
                  </div>
                  {latestDiannJob.error_message ? (
                    <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {latestDiannJob.error_message}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="mt-3 rounded-lg border border-dashed px-3 py-4 text-sm text-muted-foreground">
                  No DIA-NN job is running yet. Queue ready runs or refresh after files have been ingested to watch status change here.
                </div>
              )}
            </div>
            <div className="rounded-2xl border bg-background/80 p-4 text-sm text-muted-foreground">
              Polling every 10 seconds while the workspace is open. The process view updates automatically as jobs move through queue, assignment, running, and completion.
            </div>
          </div>
        </CardContent>
      </Card>

      <FindingsWorkflowPanel
        workspace={findingsQuery.data?.workspace ?? null}
        defaultRoot={findingsQuery.data?.default_root_path ?? ""}
        mode={workspaceMode}
        dataStrategy={dataStrategy}
        onModeChange={setWorkspaceMode}
        onDataStrategyChange={setDataStrategy}
        onPrepare={() => prepareWorkspaceMutation.mutate()}
        preparePending={prepareWorkspaceMutation.isPending}
        prepareError={prepareWorkspaceMutation.error instanceof Error ? prepareWorkspaceMutation.error.message : ""}
        onIndex={(workspaceId) => indexWorkspaceMutation.mutate(workspaceId)}
        indexPending={indexWorkspaceMutation.isPending}
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Runs</CardTitle>
              <CardDescription>
                Each row is a planned LC-MS injection with raw-file, queue, and result status.
                {isExperimentRoute ? " This view is scoped to the selected experiment." : ""}
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              {isOperator ? (
                <>
                  <Button variant="secondary" disabled={!readyToProcess.length || queueMutation.isPending} onClick={() => queueMutation.mutate()}>
                    <CheckCircle2 className="h-4 w-4" />
                    {queueMutation.isPending ? "Queueing..." : "Queue ready runs"}
                  </Button>
                  {!isExperimentRoute ? (
                    <Button variant="secondary" disabled={!project || rerunBatchMutation.isPending} onClick={() => rerunBatchMutation.mutate()}>
                      <RefreshCw className="h-4 w-4" />
                      {rerunBatchMutation.isPending ? "Requeueing..." : "Rerun latest batch"}
                    </Button>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <SelectedRunsPanel
            projectId={projectId}
            rows={selectedRows}
            readyCount={selectedReadyRows.length}
            onClear={() => setSelectedRunIds([])}
            onQueue={() => queueSelectedMutation.mutate()}
            queuePending={queueSelectedMutation.isPending}
            isOperator={isOperator}
          />
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full min-w-[1120px] text-sm">
              <thead className="bg-secondary/65 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                <tr>
                  <th className="px-3 py-3">
                    <input
                      aria-label="Select all runs"
                      checked={allSelected}
                      className="h-4 w-4"
                      type="checkbox"
                      onChange={toggleAllSelected}
                    />
                  </th>
                  <th className="px-3 py-3">Order</th>
                  <th className="px-3 py-3">Run</th>
                  <th className="px-3 py-3">Sample</th>
                  <th className="px-3 py-3">Raw File</th>
                  <th className="px-3 py-3">Run</th>
                  <th className="px-3 py-3">Queue</th>
                  <th className="px-3 py-3">Proteins</th>
                  <th className="px-3 py-3">Peptides</th>
                  <th className="px-3 py-3">MS1</th>
                  <th className="px-3 py-3">MS2</th>
                  <th className="px-3 py-3">Updated</th>
                  <th className="px-3 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((row) => (
                  <tr
                    key={row.run.id}
                    className={`border-t hover:bg-secondary/35 ${selectedRun?.run.id === row.run.id ? "bg-secondary/45" : ""}`}
                    onClick={() => setSelectedRunId(row.run.id)}
                  >
                    <td className="px-3 py-3">
                      <input
                        aria-label={`Select ${row.run.run_name}`}
                        checked={selectedRunIds.includes(row.run.id)}
                        className="h-4 w-4"
                        type="checkbox"
                        onChange={(event) => {
                          event.stopPropagation();
                          toggleRunSelected(row.run.id);
                        }}
                        onClick={(event) => event.stopPropagation()}
                      />
                    </td>
                    <td className="px-3 py-3 font-mono">{row.run.worklist_position ?? "-"}</td>
                    <td className="px-3 py-3">
                      <div className="font-semibold">{row.run.run_name}</div>
                      <div className="max-w-[220px] truncate text-xs text-muted-foreground">{row.run.expected_filename || "No expected filename"}</div>
                    </td>
                    <td className="px-3 py-3">
                      <Link className="font-semibold" to={`/projects/${projectId}/samples/${row.sample.id}`} onClick={(event) => event.stopPropagation()}>
                        {row.sample.name}
                      </Link>
                    </td>
                    <td className="px-3 py-3">{row.raw_file ? <StatusBadge status={row.raw_file.status} /> : <span className="text-muted-foreground">Missing</span>}</td>
                    <td className="px-3 py-3"><StatusBadge status={row.run.status} /></td>
                    <td className="px-3 py-3">{row.processing_job ? <StatusBadge status={row.processing_job.status} /> : <span className="text-muted-foreground">Not queued</span>}</td>
                    <td className="px-3 py-3">{row.stats.reported_protein_count || row.stats.protein_quant_count || "-"}</td>
                    <td className="px-3 py-3">{row.stats.reported_peptide_count || row.stats.peptide_quant_count || "-"}</td>
                    <td className="px-3 py-3">{row.stats.ms1_feature_count || row.stats.indexed_ms1_spectra_count || "-"}</td>
                    <td className="px-3 py-3">{row.stats.ms2_spectra_count || row.stats.indexed_ms2_spectra_count || "-"}</td>
                    <td className="px-3 py-3">{formatDate(row.run.updated_at)}</td>
                    <td className="px-3 py-3">
                      <Button size="sm" variant="secondary" onClick={(event) => { event.stopPropagation(); startEdit(row); }}>
                        <Settings2 className="h-3.5 w-3.5" />
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
                {!runs.length ? (
                  <tr>
                    <td className="px-3 py-8 text-center text-muted-foreground" colSpan={13}>
                      Import a worklist to establish the planned LC-MS runs for this project.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {selectedRun ? <RunDetail projectId={projectId} row={selectedRun} onEdit={() => startEdit(selectedRun)} isOperator={isOperator} /> : null}

      <Dialog open={Boolean(editDraft)} onOpenChange={(open) => !open && setEditDraft(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit run</DialogTitle>
            <DialogDescription>Update the worklist ground truth for this injection.</DialogDescription>
          </DialogHeader>
          {editDraft ? (
            <form
              className="grid gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                editMutation.mutate(editDraft);
              }}
            >
              <TextField label="Run name" value={editDraft.runName} onChange={(runName) => setEditDraft((current) => current && { ...current, runName })} />
              <TextField label="Order" type="number" value={editDraft.position} onChange={(position) => setEditDraft((current) => current && { ...current, position })} />
              <TextField label="Expected filename" value={editDraft.expectedFilename} onChange={(expectedFilename) => setEditDraft((current) => current && { ...current, expectedFilename })} />
              <label className="grid gap-1 text-sm font-bold">
                Role
                <Select value={editDraft.fileRole} onValueChange={(fileRole) => setEditDraft((current) => current && { ...current, fileRole })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{roleOptions.map((role) => <SelectItem key={role} value={role}>{role}</SelectItem>)}</SelectContent>
                </Select>
              </label>
              <label className="grid gap-1 text-sm font-bold">
                Status
                <Select value={editDraft.status} onValueChange={(status) => setEditDraft((current) => current && { ...current, status })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{runStatusOptions.map((status) => <SelectItem key={status} value={status}>{status}</SelectItem>)}</SelectContent>
                </Select>
              </label>
              <TextField label="HYE pair" value={editDraft.hyePairLabel} onChange={(hyePairLabel) => setEditDraft((current) => current && { ...current, hyePairLabel })} />
              <TextField label="Notes" value={editDraft.notes} onChange={(notes) => setEditDraft((current) => current && { ...current, notes })} />
              <div className="flex justify-end gap-2 border-t pt-3">
                <Button type="button" variant="secondary" onClick={() => setEditDraft(null)}>Cancel</Button>
                <Button type="submit" disabled={editMutation.isPending}>
                  <Save className="h-4 w-4" />
                  {editMutation.isPending ? "Saving..." : "Save"}
                </Button>
              </div>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SelectedRunsPanel({
  projectId,
  rows,
  readyCount,
  onClear,
  onQueue,
  queuePending,
  isOperator,
}: {
  projectId: number;
  rows: ProjectResearcherRun[];
  readyCount: number;
  onClear: () => void;
  onQueue: () => void;
  queuePending: boolean;
  isOperator: boolean;
}) {
  if (!rows.length) return null;
  const rawFileCount = rows.filter((row) => row.raw_file).length;
  const failedCount = rows.filter((row) => row.run.status === "failed" || row.processing_job?.status === "failed").length;
  const firstSample = rows[0]?.sample;

  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-secondary/55 p-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <div className="font-black">{rows.length} selected</div>
        <div className="text-muted-foreground">{rawFileCount} with raw files</div>
        <div className="text-muted-foreground">{readyCount} ready to queue</div>
        <div className={failedCount ? "font-bold text-warning" : "text-muted-foreground"}>{failedCount} failed</div>
      </div>
      <div className="flex flex-wrap gap-2">
        {firstSample ? (
          <Button asChild size="sm" variant="secondary">
            <Link to={`/projects/${projectId}/samples/${firstSample.id}`}>
              Open first sample
            </Link>
          </Button>
        ) : null}
        {isOperator ? (
          <Button size="sm" variant="secondary" disabled={!readyCount || queuePending} onClick={onQueue}>
            <CheckCircle2 className="h-3.5 w-3.5" />
            {queuePending ? "Queueing..." : "Queue selected"}
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear
        </Button>
      </div>
    </div>
  );
}

function RunDetail({
  projectId,
  row,
  onEdit,
  isOperator,
}: {
  projectId: number;
  row: ProjectResearcherRun;
  onEdit: () => void;
  isOperator: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{row.run.run_name}</CardTitle>
            <CardDescription>{row.worklist_name || "No worklist"} · {row.run.expected_filename || "No expected filename"}</CardDescription>
          </div>
          <Button variant="secondary" onClick={onEdit}>
            <Settings2 className="h-4 w-4" />
            Edit run
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-lg border p-3">
          <div className="text-xs font-bold uppercase text-muted-foreground">Raw file</div>
          <div className="mt-2 font-semibold">{row.raw_file?.filename ?? "Missing"}</div>
          <div className="mt-1 text-sm text-muted-foreground">
            {row.raw_file ? (
              formatBytes(row.raw_file.size_bytes)
            ) : (
              isOperator ? (
                <Link className="font-medium text-primary" to={`/watcher?project=${projectId}&run=${row.run.id}`}>
                  Stream for this run
                </Link>
              ) : (
                "Stream queued through the lab workflow"
              )
            )}
          </div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-xs font-bold uppercase text-muted-foreground">Processing</div>
          <div className="mt-2">{row.processing_job ? <StatusBadge status={row.processing_job.status} /> : <span className="text-sm text-muted-foreground">Not queued</span>}</div>
          <div className="mt-1 text-sm text-muted-foreground">{row.processing_job?.pipeline_name ?? "Queue when raw file is ready"}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-xs font-bold uppercase text-muted-foreground">Spectra</div>
          <div className="mt-2 font-semibold">{row.stats.indexed_spectra_count || row.stats.ms2_spectra_count || "-"}</div>
          <div className="mt-1 text-sm text-muted-foreground">
            {row.raw_file ? <Link className="font-medium text-primary" to={`/spectra?rawFile=${row.raw_file.id}`}>Open spectra viewer</Link> : "No raw file yet"}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function FindingsWorkflowPanel({
  workspace,
  defaultRoot,
  mode,
  dataStrategy,
  onModeChange,
  onDataStrategyChange,
  onPrepare,
  preparePending,
  prepareError,
  onIndex,
  indexPending,
}: {
  workspace: FindingsWorkspace | null;
  defaultRoot: string;
  mode: "personal" | "shared";
  dataStrategy: "manifest" | "symlink";
  onModeChange: (mode: "personal" | "shared") => void;
  onDataStrategyChange: (strategy: "manifest" | "symlink") => void;
  onPrepare: () => void;
  preparePending: boolean;
  prepareError: string;
  onIndex: (workspaceId: number) => void;
  indexPending: boolean;
}) {
  const commands = workspace?.claude_commands ?? [
    "/plugin marketplace add mriffle/findings-ai-collab-workflow",
    "/plugin install findings-workflow@findings-workflow",
    "/findings-workflow:init",
  ];

  function copyCommands() {
    void navigator.clipboard?.writeText(commands.join("\n"));
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Claude Findings Workflow</CardTitle>
            <CardDescription>Prepare an analysis workspace for experimental design, QC, validated findings, figures, and reports.</CardDescription>
          </div>
          {workspace ? <StatusBadge status={workspace.status} /> : null}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <div className="grid gap-3">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1 text-sm font-bold">
              Workspace mode
              <Select value={mode} onValueChange={(value) => onModeChange(value as "personal" | "shared")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="personal">Personal</SelectItem>
                  <SelectItem value="shared">Shared</SelectItem>
                </SelectContent>
              </Select>
            </label>
            <label className="grid gap-1 text-sm font-bold">
              Data access
              <Select value={dataStrategy} onValueChange={(value) => onDataStrategyChange(value as "manifest" | "symlink")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="manifest">Path manifest</SelectItem>
                  <SelectItem value="symlink">Read-only symlinks</SelectItem>
                </SelectContent>
              </Select>
            </label>
          </div>

          <div className="rounded-lg border bg-background/50 p-3">
            <div className="flex items-center gap-2 text-sm font-bold">
              <FolderKanban className="h-4 w-4" />
              Workspace
            </div>
            <div className="mt-2 break-all font-mono text-xs text-muted-foreground">
              {workspace?.workspace_path ?? defaultRoot ?? "Prepare the workspace to create project files."}
            </div>
            {workspace ? (
              <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                <span>Walkthrough: {workspace.walkthrough_path}</span>
                <span>Findings: {workspace.findings_count} · Reports: {workspace.reports_count}</span>
                {workspace.latest_report_path ? <span>Latest report: {workspace.latest_report_path}</span> : null}
              </div>
            ) : null}
          </div>

          {prepareError ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{prepareError}</div> : null}

          <div className="flex flex-wrap gap-2">
            <Button onClick={onPrepare} disabled={preparePending}>
              <BrainCircuit className="h-4 w-4" />
              {preparePending ? "Preparing..." : workspace ? "Refresh workspace export" : "Prepare workspace"}
            </Button>
            {workspace ? (
              <Button variant="secondary" onClick={() => onIndex(workspace.id)} disabled={indexPending}>
                <RefreshCw className="h-4 w-4" />
                {indexPending ? "Indexing..." : "Index outputs"}
              </Button>
            ) : null}
          </div>
        </div>

        <div className="rounded-lg border bg-secondary/45 p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-black">Claude walkthrough</div>
            <Button size="sm" variant="secondary" onClick={copyCommands}>
              <Copy className="h-3.5 w-3.5" />
              Copy
            </Button>
          </div>
          <ol className="mt-3 grid gap-2 text-sm text-muted-foreground">
            <li><span className="font-bold text-foreground">1.</span> Install the plugin in Claude Code and restart Claude.</li>
            <li><span className="font-bold text-foreground">2.</span> Open Claude Code in the workspace path.</li>
            <li><span className="font-bold text-foreground">3.</span> Run init, setup-env, then Stage 0 through reporting.</li>
          </ol>
          <pre className="mt-3 max-h-52 overflow-auto rounded-lg bg-background p-3 text-xs"><code>{commands.join("\n")}</code></pre>
        </div>
      </CardContent>
    </Card>
  );
}

function WorklistPreview({ rows }: { rows: WorklistImportRow[] }) {
  if (!rows.length) {
    return <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">No rows parsed yet. Expected columns include sample, run, filename, role, condition, well, and position.</div>;
  }
  return (
    <div className="max-h-72 overflow-auto rounded-lg border">
      <table className="w-full min-w-[760px] text-sm">
        <thead className="bg-secondary/65 text-left text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2">Order</th>
            <th className="px-3 py-2">Run</th>
            <th className="px-3 py-2">Sample</th>
            <th className="px-3 py-2">Filename</th>
            <th className="px-3 py-2">Role</th>
            <th className="px-3 py-2">Well</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((row) => (
            <tr key={`${row.position}-${row.expected_filename}`} className="border-t">
              <td className="px-3 py-2">{row.position}</td>
              <td className="px-3 py-2">{row.run_name || "-"}</td>
              <td className="px-3 py-2">{row.sample_name}</td>
              <td className="px-3 py-2">{row.expected_filename}</td>
              <td className="px-3 py-2">{row.file_role}</td>
              <td className="px-3 py-2">{row.well || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 20 ? <div className="border-t px-3 py-2 text-xs text-muted-foreground">{rows.length - 20} more rows will be imported.</div> : null}
    </div>
  );
}

function speclibModeLabel(mode?: string) {
  if (mode === "reuse") return "Reuse speclib";
  if (mode === "smoke") return "Smoke only";
  if (mode === "build") return "Build speclib";
  return "-";
}

function speclibModeDetail(mode?: string) {
  if (mode === "reuse") return "Use the generated project speclib for report runs.";
  if (mode === "smoke") return "Launcher check only. Not the production search path.";
  if (mode === "build") return "Generate a project speclib on the first pass.";
  return "Resolve the project preflight to see the DIA-NN speclib mode.";
}

function buildDiannProcessSteps(preflightValid: boolean, readyCount: number, latestJob: ProcessingJob | null) {
  const latestStatus = latestJob?.status ?? "";
  const queued = latestStatus === "queued" || latestStatus === "assigned" || latestStatus === "running" || latestStatus === "retrying";
  const running = latestStatus === "running";
  const done = latestStatus === "complete";
  const failed = latestStatus === "failed";
  return [
    {
      key: "preflight",
      label: "Preflight",
      detail: preflightValid ? "Resolved settings are ready." : "Resolve settings before queueing.",
      status: preflightValid ? "complete" : "warning",
    },
    {
      key: "ready",
      label: "Ready runs",
      detail: `${readyCount} run${readyCount === 1 ? "" : "s"} can be queued.`,
      status: readyCount ? "complete" : "warning",
    },
    {
      key: "queued",
      label: "Queued",
      detail: queued ? `Latest job is ${latestStatus}.` : "Waiting for queue submission.",
      status: queued ? "complete" : "warning",
    },
    {
      key: "running",
      label: "Running",
      detail: running ? "DIA-NN is executing now." : "Node has not started execution yet.",
      status: running ? "running" : done ? "complete" : failed ? "failed" : "warning",
    },
    {
      key: "complete",
      label: "Complete",
      detail: done ? "Latest job finished successfully." : failed ? "Latest job failed and needs review." : "Completion will appear here after execution.",
      status: done ? "complete" : failed ? "failed" : "warning",
    },
  ] as Array<{
    key: string;
    label: string;
    detail: string;
    status: string;
  }>;
}

function ProcessStepCard({
  label,
  detail,
  status,
}: {
  label: string;
  detail: string;
  status: string;
}) {
  return (
    <div className="rounded-2xl border bg-background/70 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-black">{label}</div>
        <StatusBadge status={status} />
      </div>
      <div className="mt-2 text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}

function TextField(props: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <label className="grid gap-1 text-sm font-bold">
      {props.label}
      <Input type={props.type ?? "text"} value={props.value} onChange={(event) => props.onChange(event.target.value)} required />
    </label>
  );
}

function parseWorklistText(text: string): WorklistImportRow[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) return [];
  const delimiter = lines[0].includes("\t") ? "\t" : ",";
  const headers = parseDelimitedLine(lines[0], delimiter).map((header) => header.trim().toLowerCase());
  return lines.slice(1).flatMap((line, index) => {
    const values = parseDelimitedLine(line, delimiter).map((value) => value.trim());
    const value = (candidates: string[]) => {
      const headerIndex = headers.findIndex((header) => candidates.includes(header));
      return headerIndex >= 0 ? values[headerIndex] ?? "" : "";
    };
    const sampleName = value(["sample_name", "sample", "sample id", "sample_id", "name"]) || `Sample-${String(index + 1).padStart(3, "0")}`;
    const expectedFilename = value(["expected_filename", "expected file", "filename", "file", "raw file", "raw_file"]);
    if (!expectedFilename) return [];
    const positionValue = Number(value(["position", "order", "injection", "index", "pos"]));
    const roleValue = value(["file_role", "role", "type"]).toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    const fileRole = roleOptions.includes(roleValue as WorklistImportRow["file_role"]) ? roleValue as WorklistImportRow["file_role"] : "sample";
    const qcProgramValue = value(["qc_program", "qc program", "qc", "program"]).toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
    const qcProgram = qcProgramValue === "hye" || fileRole === "hye" ? "hye" : qcProgramValue === "prtc" || fileRole === "prtc" ? "prtc" : "";
    return {
      position: Number.isFinite(positionValue) && positionValue > 0 ? positionValue : index + 1,
      sample_name: sampleName,
      run_name: value(["run_name", "run", "injection_name"]) || sampleName,
      expected_filename: expectedFilename,
      file_role: fileRole,
      qc_program: qcProgram,
      condition: value(["condition", "group"]),
      well: value(["well", "vial", "autosampler_vial"]),
      plate: value(["plate", "plate_id"]),
      hye_pair_label: value(["hye_pair_label", "hye pair", "qc_pair"]),
      metadata: Object.fromEntries(headers.map((header, headerIndex) => [header, values[headerIndex] ?? ""])),
    };
  });
}

function parseDelimitedLine(line: string, delimiter: string) {
  const values: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === "\"" && quoted && next === "\"") {
      current += "\"";
      index += 1;
    } else if (char === "\"") {
      quoted = !quoted;
    } else if (char === delimiter && !quoted) {
      values.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  values.push(current);
  return values;
}
