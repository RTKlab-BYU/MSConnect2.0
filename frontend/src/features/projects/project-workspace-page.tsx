import { useMutation, useQuery } from "@tanstack/react-query";
import { BarChart3, BrainCircuit, CheckCircle2, Copy, FileUp, FolderKanban, RefreshCw, Save, Settings2, UsersRound } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { ProjectAssistantPanel } from "@/features/projects/project-assistant-panel";
import { parseWorklistText, roleOptions, type InstrumentWorklistKind } from "@/features/projects/worklist-import";
import {
  fetchCurrentUser,
  fetchFileMatchExceptions,
  fetchExperiment,
  fetchExperiments,
  fetchProjectResearcherStatus,
  fetchProjectMembers,
  shareProjectWithUser,
  removeProjectMember,
  fetchAcquisitionRoutes,
  fetchProjectDiannPreflight,
  fetchFindingsWorkspace,
  fetchProcessingJobs,
  fetchRawFiles,
  indexFindingsWorkspace,
  importProjectWorklist,
  prepareFindingsWorkspace,
  queueProjectRuns,
  queueProjectReadyRuns,
  rerunLatestDiannBatch,
  reanalyzeProject,
  fetchAnalysisBatches,
  resolveFileMatchException,
  queryKeys,
  updateRun,
  updateWorklistEntry,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import { formatBytes, formatDate } from "@/lib/format";
import type { AnalysisBatch, FileMatchException, FindingsWorkspace, ProjectResearcherRun, RawFile, WorklistImportRow } from "@/lib/api/types";
import { isOperatorRole } from "@/lib/ui-surface";

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

const lifecycleSections = [
  ["overview", "Overview"],
  ["worklists", "Worklists"],
  ["acquisition", "Acquisition"],
  ["processing", "Processing"],
  ["qc", "QC"],
  ["analysis", "Analysis"],
  ["assistant", "Assistant"],
] as const;

export default function ProjectWorkspacePage() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const projectId = Number(params.projectId);
  const experimentId = Number(params.experimentId);
  const activeSection = lifecycleSections.some(([section]) => section === params.section) ? params.section! : "overview";
  const quickStartImportError = (location.state as { quickStartImportError?: string } | null)?.quickStartImportError;
  const isExperimentRoute = Number.isFinite(experimentId);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [runPage, setRunPage] = useState(1);
  const [worklistOpen, setWorklistOpen] = useState(false);
  const [worklistName, setWorklistName] = useState("Imported LC-MS worklist");
  const [msWorklistFile, setMsWorklistFile] = useState<File | null>(null);
  const [msWorklistRows, setMsWorklistRows] = useState<WorklistImportRow[]>([]);
  const [lcWorklistFile, setLcWorklistFile] = useState<File | null>(null);
  const [lcWorklistRows, setLcWorklistRows] = useState<WorklistImportRow[]>([]);
  const [worklistError, setWorklistError] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>([]);
  const [workspaceMode, setWorkspaceMode] = useState<"personal" | "shared">("personal");
  const [dataStrategy, setDataStrategy] = useState<"manifest" | "symlink">("manifest");
  const [rerunNotice, setRerunNotice] = useState("");
  const [analysisExecutor, setAnalysisExecutor] = useState<"local" | "slurm">("slurm");
  const statusParams = isExperimentRoute ? { experiment: experimentId } : undefined;
  const statusQueryKey = queryKeys.projectResearcherStatus(projectId, statusParams);
  const preflightQueryKey = queryKeys.projectDiannPreflight(projectId, statusParams);

  const statusQuery = useQuery({
    queryKey: statusQueryKey,
    queryFn: () => fetchProjectResearcherStatus(projectId, statusParams),
    enabled: Number.isFinite(projectId),
    refetchInterval: activeSection === "qc" ? 5_000 : 30_000,
  });
  const preflightQuery = useQuery({
    queryKey: preflightQueryKey,
    queryFn: () => fetchProjectDiannPreflight(projectId, statusParams),
    enabled: Number.isFinite(projectId) && (activeSection === "acquisition" || activeSection === "worklists"),
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
  const watcherRoutesQuery = useQuery({
    queryKey: queryKeys.acquisitionRoutes({ project: projectId, page: 1, page_size: 100 }),
    queryFn: () => fetchAcquisitionRoutes({ project: projectId, page: 1, page_size: 100 }),
    enabled: Number.isFinite(projectId) && activeSection === "acquisition",
    refetchInterval: 5_000,
  });
  const processingJobsQuery = useQuery({
    queryKey: queryKeys.projectProcessingJobs(projectId),
    queryFn: () => fetchProcessingJobs({ project: projectId, page: 1, page_size: 50 }),
    enabled: Number.isFinite(projectId) && (activeSection === "processing" || activeSection === "acquisition"),
    refetchInterval: 10_000,
  });
  const analysisBatchesQuery = useQuery({
    queryKey: queryKeys.analysisBatches(projectId),
    queryFn: () => fetchAnalysisBatches(projectId),
    enabled: Number.isFinite(projectId) && activeSection === "analysis",
    refetchInterval: 10_000,
  });
  const findingsQuery = useQuery({
    queryKey: queryKeys.findingsWorkspace(projectId),
    queryFn: () => fetchFindingsWorkspace(projectId),
    enabled: Number.isFinite(projectId) && activeSection === "analysis",
  });
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const data = statusQuery.data;
  const project = data?.project;
  const isOperator = isOperatorRole(currentUserQuery.data?.global_role);
  const canManageSharing = Boolean(project && (project.owner === currentUserQuery.data?.id || currentUserQuery.data?.global_role === "admin"));
  const experiment = experimentQuery.data ?? data?.experiment ?? null;
  const experiments = experimentsQuery.data?.results ?? [];
  const runs = useMemo(() => data?.runs ?? [], [data?.runs]);
  const visibleRuns = runs.slice((runPage - 1) * 50, runPage * 50);
  const hyePairs = useMemo(() => buildHyePairs(runs), [runs]);
  const selectedRun = runs.find((row) => row.run.id === selectedRunId) ?? runs[0];
  const readyToProcess = runs.filter((row) => row.raw_file && !row.processing_job);
  const failedRows = runs.filter((row) => row.processing_job?.status === "failed" || row.run.status === "failed");
  const selectedRows = runs.filter((row) => selectedRunIds.includes(row.run.id));
  const selectedReadyRows = selectedRows.filter((row) => row.raw_file && !row.processing_job);
  const allSelected = Boolean(runs.length) && selectedRunIds.length === runs.length;

  useEffect(() => {
    setRunPage(1);
    setSelectedRunIds([]);
    setSelectedRunId(null);
  }, [projectId, experimentId]);
  const latestDiannJob = useMemo(
    () =>
      (processingJobsQuery.data?.results ?? []).find(
        (job) => job.required_engine.toLowerCase().includes("diann") || job.pipeline_name.toLowerCase().includes("diann"),
      ) ??
      (processingJobsQuery.data?.results ?? [])[0] ??
      null,
    [processingJobsQuery.data?.results],
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
        rows: msWorklistRows,
        ms_filename: msWorklistFile?.name,
        lc_filename: lcWorklistFile?.name,
        lc_rows: lcWorklistRows,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: statusQueryKey });
      await queryClient.invalidateQueries({ queryKey: preflightQueryKey });
      await queryClient.invalidateQueries({ queryKey: queryKeys.projectExperiments(projectId) });
      setWorklistOpen(false);
      setMsWorklistFile(null);
      setMsWorklistRows([]);
      setLcWorklistFile(null);
      setLcWorklistRows([]);
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
  const reanalyzeMutation = useMutation({
    mutationFn: () => reanalyzeProject(projectId, {
      executor: analysisExecutor,
      ...(isExperimentRoute ? { experiment: experimentId } : {}),
    }),
    onSuccess: async (batches: AnalysisBatch[]) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: statusQueryKey }),
        queryClient.invalidateQueries({ queryKey: queryKeys.projectProcessingJobs(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.analysisBatches(projectId) }),
      ]);
      setRerunNotice(`Queued ${batches.length} experiment analysis batch${batches.length === 1 ? "" : "es"} on ${analysisExecutor === "slurm" ? "BYU Slurm" : "local processors"}.`);
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
  const healthClass = health === "green" ? "bg-success/10 text-success" : health === "red" ? "bg-destructive/10 text-destructive" : "bg-warning/15 text-warning";

  function onWorklistFile(file: File | undefined, kind: InstrumentWorklistKind) {
    if (kind === "ms") {
      setMsWorklistFile(file ?? null);
      setMsWorklistRows([]);
    } else {
      setLcWorklistFile(file ?? null);
      setLcWorklistRows([]);
    }
    setWorklistError("");
    if (!file) return;
    file
      .text()
      .then((text) => {
        const parsedRows = parseWorklistText(text, kind);
        if (kind === "ms") setMsWorklistRows(parsedRows);
        else setLcWorklistRows(parsedRows);
      })
      .catch((error) => setWorklistError(error instanceof Error ? error.message : "Could not read worklist file."));
  }

  function submitWorklist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!msWorklistRows.length) {
      setWorklistError("Choose a valid MS CSV or TSV worklist. The MS file defines the planned runs.");
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
        actions={canManageSharing ? <Button type="button" variant="secondary" onClick={() => setShareOpen(true)}><UsersRound className="h-4 w-4" />Share project</Button> : undefined}
      />
      {project ? <ProjectSharingDialog projectId={project.id} open={shareOpen} onOpenChange={setShareOpen} /> : null}
      {quickStartImportError ? <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">Project created, but its worklist could not be imported: {quickStartImportError} Use Import worklist below to retry.</div> : null}
      <div className="flex flex-wrap items-center gap-2">
            {project ? <StatusBadge status={project.status} /> : null}
            {experiment ? (
              <span className="inline-flex h-9 items-center rounded-md bg-muted px-3 text-sm font-semibold text-foreground">
                Experiment selected
              </span>
            ) : null}
            <span className={`inline-flex h-9 items-center rounded-sm px-3 text-sm font-semibold ${healthClass}`}>{healthLabel}</span>
            {experiments.length > 1 ? (
              <Select
                value={isExperimentRoute ? String(experimentId) : "project"}
                onValueChange={(value) => navigate(value === "project" ? `/projects/${projectId}/overview` : `/projects/${projectId}/experiments/${value}/overview`)}
              >
                <SelectTrigger className="h-9 w-[190px] bg-background"><SelectValue placeholder="Select experiment" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="project">All project runs</SelectItem>
                  {experiments.map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.name}</SelectItem>)}
                </SelectContent>
              </Select>
            ) : null}
            {experiments.length === 1 && !isExperimentRoute ? (
              <Button asChild variant="ghost">
                <Link to={`/projects/${projectId}/experiments/${experiments[0].id}/overview`}>
                  Experiment: {experiments[0].name}
                </Link>
              </Button>
            ) : null}
            {isExperimentRoute ? (
              <Button asChild variant="secondary">
                <Link to={`/projects/${projectId}/overview`}>Project overview</Link>
              </Button>
            ) : null}
            {activeSection === "worklists" ? <>
            {canManageSharing ? <Dialog open={worklistOpen} onOpenChange={setWorklistOpen}>
              <DialogTrigger asChild>
                <Button>
                  <FileUp className="h-4 w-4" />
                  Import worklist
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[90vh] max-w-4xl overflow-auto">
                <DialogHeader>
                  <DialogTitle>Import an instrument worklist</DialogTitle>
                  <DialogDescription>
                    Upload the MS worklist, plus its matching LC worklist when available. MS rows define planned runs; LC rows are attached to the worklist for reference.
                    {isExperimentRoute ? " The import will attach to the selected experiment." : " The import will attach to the default experiment for this project."}
                  </DialogDescription>
                </DialogHeader>
                <form className="grid gap-4" onSubmit={submitWorklist}>
                  <label className="grid gap-1 text-sm font-semibold">
                    Worklist name
                    <Input aria-label="Worklist name" value={worklistName} onChange={(event) => setWorklistName(event.target.value)} />
                  </label>
                  <div className="grid gap-3 md:grid-cols-2">
                    <WorklistFilePicker kind="ms" file={msWorklistFile} count={msWorklistRows.length} required onFile={(file) => onWorklistFile(file, "ms")} />
                    <WorklistFilePicker kind="lc" file={lcWorklistFile} count={lcWorklistRows.length} onFile={(file) => onWorklistFile(file, "lc")} />
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                    <a className="underline underline-offset-2" href="/worklist-examples/example-ms-worklist.csv" download>Example MS worklist</a>
                    <a className="underline underline-offset-2" href="/worklist-examples/example-lc-worklist-format.csv" download>Example LC worklist</a>
                    <a className="underline underline-offset-2" href="/worklist-examples/msconnect-import-example.csv" download>Standard MSConnect format</a>
                  </div>
                  <WorklistPreview rows={msWorklistRows} />
                  {worklistError ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{worklistError}</div> : null}
                  <div className="flex justify-end gap-2 border-t pt-3">
                    <Button type="button" variant="secondary" onClick={() => setWorklistOpen(false)}>
                      Cancel
                    </Button>
                    <Button type="submit" disabled={importMutation.isPending || !msWorklistRows.length || (isExperimentRoute && !experiment)}>
                      {importMutation.isPending ? "Importing..." : "Import worklist"}
                    </Button>
                  </div>
                </form>
              </DialogContent>
            </Dialog> : null}
            </> : null}
      </div>

      <nav aria-label="Project lifecycle" className="flex flex-wrap gap-1 rounded-lg bg-muted p-1">
        {lifecycleSections.map(([id, label]) => (
          <Link
            key={id}
            to={workspaceSectionPath(projectId, isExperimentRoute ? experimentId : null, id)}
            aria-current={activeSection === id ? "page" : undefined}
            className={`rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${activeSection === id ? "bg-card font-semibold text-foreground shadow-sm" : "text-muted-foreground hover:bg-card/70 hover:text-foreground"}`}
          >{label}</Link>
        ))}
      </nav>

      {activeSection === "overview" ? <>
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label={isExperimentRoute ? "Experiment" : "Project Status"} value={isExperimentRoute ? experiment?.name ?? "-" : project?.status ?? "-"} detail={isExperimentRoute ? "single acquisition series" : "research workflow"} />
        <MetricCard label="Runs" value={data?.summary.run_count ?? "-"} detail={isExperimentRoute ? "in this experiment" : "planned/acquired"} />
        <MetricCard label="Raw Files" value={data?.summary.raw_file_count ?? "-"} detail={`${data?.summary.missing_raw_file_count ?? 0} missing`} />
        <MetricCard label="Queue" value={data?.system_health.active_jobs ?? "-"} detail="active jobs" />
        <MetricCard label="Failed" value={failedRows.length} detail="runs needing review" />
        <MetricCard label="Ready" value={readyToProcess.length} detail="uploaded, not queued" />
      </section>
      </> : null}

      {activeSection === "acquisition" ? <>
      <Card>
        <CardHeader><CardTitle>Live project watchers</CardTitle><CardDescription>Only acquisition routes attached to this project are shown. Updates every five seconds.</CardDescription></CardHeader>
        <CardContent className="grid gap-2">
          {(watcherRoutesQuery.data?.results ?? []).map((route) => <div key={route.id} className="grid min-w-0 gap-2 rounded-md bg-muted p-3 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center">
            <div className="min-w-0"><div className="break-words font-semibold">{route.agent_name} · {route.name}</div><div className="mt-1 break-all text-xs text-muted-foreground">{route.source_prefix || "Project root"} → {route.spool_folder || "Spool root"} · {route.mode}</div><div className="mt-1 text-xs text-muted-foreground">Last agent check-in: {route.agent_last_seen_at ? formatDate(route.agent_last_seen_at) : "Never"}</div></div>
            <StatusBadge status={route.agent_status === "online" ? "complete" : route.agent_status === "stale" ? "warning" : "failed"} />
            <StatusBadge status={route.status} />
          </div>)}
          {!watcherRoutesQuery.data?.results.length ? <div className="border border-dashed p-4 text-sm text-muted-foreground">{watcherRoutesQuery.isLoading ? "Loading project watcher routes…" : "No watcher routes are assigned to this project yet."}</div> : null}
          {watcherRoutesQuery.isError ? <div role="alert" className="text-sm text-destructive">Could not load project watcher routes: {watcherRoutesQuery.error.message}</div> : null}
        </CardContent>
      </Card>
      <Card id="acquisition" className="scroll-mt-36">
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
        <CardContent className="grid gap-3">
          <div className="grid gap-2 md:grid-cols-4">
            <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">DIA-NN settings</div><div className="mt-1 font-semibold">{preflightQuery.data?.is_valid ? "Appropriate" : preflightQuery.isLoading ? "Checking…" : "Needs review"}</div></div>
            <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Preset</div><div className="mt-1 truncate font-semibold">{preflightQuery.data?.processing_preset || "Not configured"}</div></div>
            <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Engine</div><div className="mt-1 font-semibold">DIA-NN {preflightQuery.data?.diann_version || "—"}</div></div>
            <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Current acquisition</div><div className="mt-1 font-semibold">{latestDiannJob?.status === "running" ? "Processing live" : `${readyToProcess.length} runs ready`}</div></div>
          </div>
          <details className="rounded-md border px-3 py-2">
            <summary className="cursor-pointer text-sm font-semibold">DIA-NN configuration and validation details</summary>
            <div className="mt-3 grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="grid gap-3">
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-md bg-muted p-3">
                <div className="text-xs font-bold uppercase text-muted-foreground">Source</div>
                <div className="mt-1 font-semibold">{preflightQuery.data?.source_label ?? "Loading preflight..."}</div>
                <div className="mt-1 text-sm text-muted-foreground">{preflightQuery.data?.source_detail ?? "Resolve the pipeline snapshot used for upload."}</div>
              </div>
              <div className="rounded-md bg-muted p-3">
                <div className="text-xs font-bold uppercase text-muted-foreground">Preset / version</div>
                <div className="mt-1 font-semibold">{preflightQuery.data?.processing_preset || "-"}</div>
                <div className="mt-1 text-sm text-muted-foreground">DIA-NN {preflightQuery.data?.diann_version || "-"}</div>
              </div>
              <div className="rounded-md bg-muted p-3">
                <div className="text-xs font-bold uppercase text-muted-foreground">Speclib mode</div>
                <div className="mt-1 font-semibold">{speclibModeLabel(preflightQuery.data?.speclib_mode)}</div>
                <div className="mt-1 text-sm text-muted-foreground">{speclibModeDetail(preflightQuery.data?.speclib_mode)}</div>
              </div>
            </div>
            <div className="rounded-md bg-muted p-3">
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
            <div className="rounded-md bg-muted p-3">
              <div className="text-xs font-bold uppercase text-muted-foreground">Performance tags</div>
              <pre className="mt-2 overflow-auto rounded-lg bg-background p-3 text-xs">
                <code>{JSON.stringify(preflightQuery.data?.performance_tags ?? {}, null, 2)}</code>
              </pre>
            </div>
            <div className="rounded-md bg-muted p-3">
              <div className="text-xs font-bold uppercase text-muted-foreground">Experimental tags</div>
              <pre className="mt-2 overflow-auto rounded-lg bg-background p-3 text-xs">
                <code>{JSON.stringify(preflightQuery.data?.experimental_tags ?? {}, null, 2)}</code>
              </pre>
            </div>
            <div className="rounded-md bg-muted p-3">
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
                <div className="mt-2 rounded-md bg-success/10 px-3 py-2 text-sm text-success">
                  No validation errors. The preflight snapshot is ready for upload or processing.
                </div>
              )}
            </div>
            <div className="rounded-md bg-muted p-3">
              <div className="text-xs font-bold uppercase text-muted-foreground">Command options</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {(preflightQuery.data?.options ?? []).length ? (
                  preflightQuery.data?.options.map((option) => (
                    <span key={option} className="rounded-sm bg-background px-2 py-1 font-mono text-xs">
                      {option}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">No explicit DIA-NN options resolved.</span>
                )}
              </div>
            </div>
          </div>
            </div>
          </details>
        </CardContent>
      </Card>
      <ProjectRawFileInbox projectId={projectId} experimentId={isExperimentRoute ? experimentId : null} runs={runs} canResolve={isOperator} />
      </> : null}

      {activeSection === "processing" ? <>
      <Card id="processing" className="scroll-mt-36">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Processing jobs</CardTitle>
              <CardDescription>Recent jobs for this project, with current node and run state.</CardDescription>
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
        <CardContent className="grid gap-2">
          {(processingJobsQuery.data?.results ?? []).map((job) => (
            <div key={job.id} className="grid gap-2 rounded-md border p-3 md:grid-cols-[minmax(0,1fr)_130px_160px_150px] md:items-center">
              <div className="min-w-0"><div className="truncate font-medium">{job.run_name || job.raw_file_filename}</div><div className="truncate text-xs text-muted-foreground">{job.pipeline_name} {job.pipeline_version} · {job.raw_file_filename}</div></div>
              <StatusBadge status={job.status} />
              <div className="truncate text-sm text-muted-foreground">{job.node_name || "Awaiting processor"}</div>
              <div className="text-xs text-muted-foreground">{formatDate(job.started_at || job.created_at)}</div>
            </div>
          ))}
          {!processingJobsQuery.data?.results.length ? <div className="rounded-md border border-dashed p-5 text-sm text-muted-foreground">No processing jobs have been created for this project yet.</div> : null}
          <div className="text-xs text-muted-foreground">Refreshes every 10 seconds. Detailed queue controls remain on the processing page.</div>
        </CardContent>
      </Card>
      </> : null}

      {activeSection === "qc" ? <>
      <section id="qc" className="scroll-mt-36">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><CardTitle>{isExperimentRoute ? "Experiment QC" : "Project QC"}</CardTitle><CardDescription>All planned HYE A/B pairs for this {isExperimentRoute ? "experiment" : "project"}, refreshed every five seconds while this page is open.</CardDescription></div>
              <span className="text-xs text-muted-foreground">Updated {statusQuery.dataUpdatedAt ? formatDate(new Date(statusQuery.dataUpdatedAt).toISOString()) : "—"}</span>
            </div>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3 md:items-center">
            <MetricCard label="Tagged HYE injections" value={runs.filter((row) => row.run.file_role === "hye" || row.run.qc_program === "hye").length} detail="A/B control runs" />
            <MetricCard label="HYE pairs" value={hyePairs.length} detail="from worklist labels" />
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="secondary"><Link to={`/qc/hye?project=${projectId}${isExperimentRoute ? `&experiment=${experimentId}` : ""}`}>Open HYE analysis</Link></Button>
              <Button asChild variant="secondary"><Link to={`/qc/prtc?project=${projectId}${isExperimentRoute ? `&experiment=${experimentId}` : ""}`}>Open PRTC QC</Link></Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>HYE A/B pairs</CardTitle><CardDescription>Pair integrity and acquisition, file, and processor state are shown separately so planned controls are visible before analysis completes.</CardDescription></CardHeader>
          <CardContent className="grid gap-2">
            {hyePairs.map((pair) => (
              <div key={pair.key} className="grid gap-3 rounded-md border p-3 lg:grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-center">
                <div><div className="font-semibold">{pair.label}</div><div className="text-xs text-muted-foreground">{pair.worklistName || "Worklist"}</div></div>
                <HyeRunSummary label="A" row={pair.a[0]} duplicates={Math.max(0, pair.a.length - 1)} />
                <HyeRunSummary label="B" row={pair.b[0]} duplicates={Math.max(0, pair.b.length - 1)} />
                <div className="flex flex-wrap gap-1">
                  {pair.issues.length ? <span className="text-xs font-semibold text-warning">Needs attention</span> : <span className="text-xs font-semibold text-success">Pair structure valid</span>}
                </div>
                {pair.issues.length ? <div className="text-xs text-warning lg:col-start-2 lg:col-span-3">{pair.issues.join(" · ")}</div> : null}
              </div>
            ))}
            {!hyePairs.length ? <div className="rounded-md border border-dashed p-5 text-sm text-muted-foreground">No HYE controls are tagged for this experiment yet. HYE A/B rows will appear here as soon as they are included in a worklist.</div> : null}
          </CardContent>
        </Card>
      </section>
      </> : null}

      {activeSection === "analysis" ? <>
      <Card>
        <CardHeader>
          <CardTitle>Reanalyze {isExperimentRoute ? "experiment" : "project"}</CardTitle>
          <CardDescription>
            Reprocess each sample raw file with its saved DIA-NN settings, then run one experiment-wide DIA-NN analysis with individual reports and matrices. Each batch snapshots settings and reference checksums when queued.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <Select value={analysisExecutor} onValueChange={(value) => setAnalysisExecutor(value as "local" | "slurm")}>
              <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="slurm">BYU Slurm</SelectItem>
                <SelectItem value="local">Local processors</SelectItem>
              </SelectContent>
            </Select>
            <Button
              disabled={!isOperator || reanalyzeMutation.isPending}
              onClick={() => reanalyzeMutation.mutate()}
            >
              <RefreshCw className="h-4 w-4" />
              {reanalyzeMutation.isPending ? "Queueing analysis…" : "Queue reanalysis"}
            </Button>
          </div>
          {rerunNotice ? <div role="status" className="rounded-md bg-success/10 px-4 py-3 text-sm text-success">{rerunNotice}</div> : null}
          {reanalyzeMutation.error instanceof Error ? <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{reanalyzeMutation.error.message}</div> : null}
          <div className="divide-y rounded-md border">
            {(analysisBatchesQuery.data?.results ?? []).slice(0, 5).map((batch) => (
              <div key={batch.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="font-medium">{batch.experiment_name} · batch {batch.id}</span>
                <span className="text-muted-foreground">{batch.executor === "slurm" ? "BYU Slurm" : "Local"} · {batch.status} · {batch.job_ids.length} jobs</span>
              </div>
            ))}
            {!analysisBatchesQuery.isLoading && !analysisBatchesQuery.data?.results.length ? (
              <div className="px-3 py-3 text-sm text-muted-foreground">No analysis batches have been queued.</div>
            ) : null}
          </div>
        </CardContent>
      </Card>
      <section id="analysis" className="scroll-mt-36 grid gap-4">
        <Card>
          <CardHeader><CardTitle>Existing analysis outputs</CardTitle><CardDescription>Project-level output counts from completed runs. This view exposes existing results; statistical testing remains in the configured analysis workflow.</CardDescription></CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Reported proteins" value={data?.summary.reported_protein_count ?? 0} detail="existing quantification" />
            <MetricCard label="Reported peptides" value={data?.summary.reported_peptide_count ?? 0} detail="existing quantification" />
            <MetricCard label="Reported precursors" value={data?.summary.reported_precursor_count ?? 0} detail="existing quantification" />
            <Button asChild variant="secondary" className="h-auto min-h-16"><Link to={`/spectra?project=${projectId}`}><BarChart3 className="h-4 w-4" />Explore spectra and results</Link></Button>
          </CardContent>
        </Card>
      </section>

      <section className="scroll-mt-36">
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
      </section>
      </> : null}

      {activeSection === "assistant" ? <>
      <section id="assistant" className="scroll-mt-36">
        <ProjectAssistantPanel projectId={projectId} />
      </section>
      </> : null}

      {activeSection === "worklists" ? <>
      {rerunNotice ? <div className="rounded-md bg-success/10 px-4 py-3 text-sm text-success">{rerunNotice}</div> : null}
      <Card id="worklists" className="scroll-mt-36">
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
          <div className="flex justify-end py-2"><Pager page={runPage} count={runs.length} onPage={setRunPage} pageSize={50} /></div>
          <div className="table-scroll rounded-md border">
            <table className="w-full min-w-[720px] text-xs">
              <thead className="bg-secondary/65 text-left text-[11px] uppercase tracking-[0.06em] text-muted-foreground">
                <tr>
                  <th className="whitespace-nowrap px-2 py-2">
                    <input
                      aria-label="Select all runs"
                      checked={allSelected}
                      className="h-4 w-4"
                      type="checkbox"
                      onChange={toggleAllSelected}
                    />
                  </th>
                  <th className="whitespace-nowrap px-2 py-2">Order</th>
                  <th className="whitespace-nowrap px-2 py-2">Run</th>
                  <th className="whitespace-nowrap px-2 py-2">Sample</th>
                  <th className="whitespace-nowrap px-2 py-2">Raw File</th>
                  <th className="whitespace-nowrap px-2 py-2">Run</th>
                  <th className="whitespace-nowrap px-2 py-2">Queue</th>
                  <th className="whitespace-nowrap px-2 py-2">Protein groups</th>
                  <th className="hidden whitespace-nowrap px-2 py-2 lg:table-cell">Peptides</th>
                  <th className="hidden whitespace-nowrap px-2 py-2 xl:table-cell">MS1 / MS2</th>
                  <th className="hidden whitespace-nowrap px-2 py-2 xl:table-cell">Updated</th>
                  <th className="whitespace-nowrap px-2 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleRuns.map((row, index) => (
                  <tr
                    key={row.run.id}
                    className={selectedRun?.run.id === row.run.id ? "border-t bg-secondary/45" : "border-t"}
                  >
                    <td className="px-2 py-2">
                      <input
                        aria-label={`Select ${row.run.run_name}`}
                        checked={selectedRunIds.includes(row.run.id)}
                        className="h-4 w-4"
                        type="checkbox"
                        onChange={() => toggleRunSelected(row.run.id)}
                      />
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 font-mono">{(runPage - 1) * 50 + index + 1}</td>
                    <td className="max-w-[250px] px-2 py-2">
                      <Button type="button" variant="ghost" className="h-auto max-w-full justify-start truncate p-0 text-left text-sm font-semibold" onClick={() => setSelectedRunId(row.run.id)}>{row.run.run_name}</Button>
                      <div className="truncate text-xs text-muted-foreground" title={row.run.expected_filename}>{row.run.expected_filename || "No expected filename"}</div>
                    </td>
                    <td className="max-w-[130px] truncate px-2 py-2">
                      <Link className="font-semibold" title={row.sample.name} to={`/projects/${projectId}/samples/${row.sample.id}`} onClick={(event) => event.stopPropagation()}>
                        {row.sample.name}
                      </Link>
                    </td>
                    <td className="px-2 py-2">{row.raw_file ? <StatusBadge status={row.raw_file.status} /> : <span className="text-muted-foreground">Missing</span>}</td>
                    <td className="px-2 py-2"><StatusBadge status={row.run.status} /></td>
                    <td className="px-2 py-2">{row.processing_job ? <StatusBadge status={row.processing_job.status} /> : <span className="text-muted-foreground">Not queued</span>}</td>
                    <td className="px-2 py-2">{row.stats.reported_protein_count || row.stats.protein_quant_count || "-"}</td>
                    <td className="hidden px-2 py-2 lg:table-cell">{row.stats.reported_peptide_count || row.stats.peptide_quant_count || "-"}</td>
                    <td className="hidden px-2 py-2 xl:table-cell">{row.stats.ms1_feature_count || row.stats.indexed_ms1_spectra_count || 0} / {row.stats.ms2_spectra_count || row.stats.indexed_ms2_spectra_count || 0}</td>
                    <td className="hidden whitespace-nowrap px-2 py-2 xl:table-cell">{formatDate(row.run.updated_at)}</td>
                    <td className="px-2 py-2">
                      <Button size="sm" variant="secondary" onClick={(event) => { event.stopPropagation(); startEdit(row); }}>
                        <Settings2 className="h-3.5 w-3.5" />
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
                {!runs.length ? (
                  <tr>
                    <td className="px-3 py-8 text-center text-muted-foreground" colSpan={12}>
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
      </> : null}
    </div>
  );
}

function ProjectRawFileInbox({
  projectId,
  experimentId,
  runs,
  canResolve,
}: {
  projectId: number;
  experimentId: number | null;
  runs: ProjectResearcherRun[];
  canResolve: boolean;
}) {
  const [search, setSearch] = useState("");
  const [rawPage, setRawPage] = useState(1);
  const [matchPage, setMatchPage] = useState(1);
  const [targets, setTargets] = useState<Record<number, string>>({});
  const rawParams = { project: projectId, ...(experimentId ? { experiment: experimentId } : {}), page: rawPage, page_size: 25, search };
  const matchParams = { project: projectId, ...(experimentId ? { experiment: experimentId } : {}), status: "open", page: matchPage, page_size: 25, search };
  const rawFilesQuery = useQuery({
    queryKey: queryKeys.rawFiles(rawParams),
    queryFn: () => fetchRawFiles(rawParams),
  });
  const matchExceptionsQuery = useQuery({
    queryKey: queryKeys.fileMatchExceptions(matchParams),
    queryFn: () => fetchFileMatchExceptions(matchParams),
  });
  const resolveMutation = useMutation({
    mutationFn: (value: { exceptionId: number; runId: number }) => resolveFileMatchException(value.exceptionId, value.runId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["raw-files"] });
      await queryClient.invalidateQueries({ queryKey: ["file-match-exceptions"] });
      await queryClient.invalidateQueries({ queryKey: ["project", projectId, "researcher-status"] });
    },
  });
  const rawFiles = rawFilesQuery.data?.results ?? [];
  const exceptions = matchExceptionsQuery.data?.results ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><CardTitle>Raw files</CardTitle><CardDescription>Search project files and review files that still need a run match.</CardDescription></div>
          <Input className="h-9 w-full sm:w-64" type="search" aria-label="Search raw files" placeholder="Search files…" value={search} onChange={(event) => { setSearch(event.target.value); setRawPage(1); setMatchPage(1); }} />
        </div>
      </CardHeader>
      <CardContent className="grid gap-5">
        <section className="grid gap-2">
          <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">Files in this project <span className="font-normal text-muted-foreground">({rawFilesQuery.data?.count ?? 0})</span></h3><Pager page={rawPage} count={rawFilesQuery.data?.count ?? 0} onPage={setRawPage} /></div>
          {rawFiles.map((file) => <RawFileRow key={file.id} file={file} />)}
          {!rawFiles.length ? <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">No matched files found for this search.</div> : null}
        </section>
        <section className="grid gap-2 border-t pt-4">
          <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">Files needing a match <span className="font-normal text-muted-foreground">({matchExceptionsQuery.data?.count ?? 0})</span></h3><Pager page={matchPage} count={matchExceptionsQuery.data?.count ?? 0} onPage={setMatchPage} /></div>
          {exceptions.map((exception) => (
            <MatchExceptionRow
              key={exception.id}
              exception={exception}
              runs={runs}
              canResolve={canResolve}
              selectedRun={targets[exception.id] ?? ""}
              pending={resolveMutation.isPending}
              onSelect={(runId) => setTargets((current) => ({ ...current, [exception.id]: runId }))}
              onResolve={() => {
                const runId = Number(targets[exception.id]);
                if (runId) resolveMutation.mutate({ exceptionId: exception.id, runId });
              }}
            />
          ))}
          {!exceptions.length ? <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">No unmatched files are waiting for review.</div> : null}
          {resolveMutation.error instanceof Error ? <div role="alert" className="text-sm text-destructive">{resolveMutation.error.message}</div> : null}
        </section>
      </CardContent>
    </Card>
  );
}

function RawFileRow({ file }: { file: RawFile }) {
  return (
    <div className="grid min-w-0 gap-2 rounded-md border px-3 py-2 sm:grid-cols-[minmax(0,1fr)_120px_100px] sm:items-center">
      <div className="min-w-0"><div className="truncate text-sm font-medium" title={file.filename}>{file.filename}</div><div className="truncate text-xs text-muted-foreground" title={file.source_path}>{file.source_path}</div></div>
      <StatusBadge status={file.status} />
      <span className="text-xs text-muted-foreground">{formatBytes(file.size_bytes)}</span>
    </div>
  );
}

function MatchExceptionRow({
  exception,
  runs,
  canResolve,
  selectedRun,
  pending,
  onSelect,
  onResolve,
}: {
  exception: FileMatchException;
  runs: ProjectResearcherRun[];
  canResolve: boolean;
  selectedRun: string;
  pending: boolean;
  onSelect: (runId: string) => void;
  onResolve: () => void;
}) {
  return (
    <div className="grid min-w-0 gap-2 rounded-md border px-3 py-2 md:grid-cols-[minmax(0,1fr)_minmax(200px,280px)_auto] md:items-center">
      <div className="min-w-0"><div className="truncate text-sm font-medium" title={exception.filename}>{exception.filename}</div><div className="text-xs text-muted-foreground">{exception.reason}</div></div>
      {canResolve ? <label className="grid gap-1 text-xs text-muted-foreground">Attach to run
        <Select value={selectedRun} onValueChange={onSelect}>
          <SelectTrigger className="h-9 bg-background"><SelectValue placeholder="Choose a run" /></SelectTrigger>
          <SelectContent>{runs.map((row) => <SelectItem key={row.run.id} value={String(row.run.id)}>{row.run.run_name} · {row.sample.name}</SelectItem>)}</SelectContent>
        </Select>
      </label> : <span className="text-xs text-muted-foreground">Ask a project operator to match this file.</span>}
      {canResolve ? <Button size="sm" disabled={!selectedRun || pending} onClick={onResolve}>{pending ? "Matching…" : "Attach"}</Button> : null}
    </div>
  );
}

function Pager({ page, count, onPage, pageSize = 25 }: { page: number; count: number; onPage: (page: number) => void; pageSize?: number }) {
  const lastPage = Math.max(1, Math.ceil(count / pageSize));
  if (lastPage < 2) return null;
  return <div className="flex items-center gap-1 text-xs text-muted-foreground"><Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button><span>{page} / {lastPage}</span><Button size="sm" variant="ghost" disabled={page >= lastPage} onClick={() => onPage(page + 1)}>Next</Button></div>;
}

type HyePairGroup = {
  key: string;
  label: string;
  worklistName: string;
  a: ProjectResearcherRun[];
  b: ProjectResearcherRun[];
  other: ProjectResearcherRun[];
  issues: string[];
};

function buildHyePairs(rows: ProjectResearcherRun[]): HyePairGroup[] {
  const groups = new Map<string, HyePairGroup>();
  rows.filter((row) => row.run.file_role === "hye" || row.run.qc_program === "hye" || row.run.hye_pair_label.trim()).forEach((row) => {
    const label = row.run.hye_pair_label.trim() || ("Unlabeled - " + row.run.run_name);
    const key = row.worklist_name + "::" + label;
    const pair = groups.get(key) ?? { key, label, worklistName: row.worklist_name, a: [], b: [], other: [], issues: [] };
    const sampleName = row.sample.name.toUpperCase();
    const mix = String(row.sample.metadata?.mix ?? "").toUpperCase();
    if (mix === "A" || /HYE[-_ ]?A/.test(sampleName)) pair.a.push(row);
    else if (mix === "B" || /HYE[-_ ]?B/.test(sampleName)) pair.b.push(row);
    else pair.other.push(row);
    groups.set(key, pair);
  });
  return [...groups.values()].map((pair) => {
    if (!pair.a.length) pair.issues.push("Missing HYE-A");
    if (!pair.b.length) pair.issues.push("Missing HYE-B");
    if (pair.a.length > 1) pair.issues.push("Duplicate HYE-A (" + pair.a.length + ")");
    if (pair.b.length > 1) pair.issues.push("Duplicate HYE-B (" + pair.b.length + ")");
    if (pair.other.length) pair.issues.push(pair.other.length + " invalid member" + (pair.other.length === 1 ? "" : "s"));
    if (pair.label.startsWith("Unlabeled - ")) pair.issues.push("Pair label missing");
    return pair;
  }).sort((left, right) => left.label.localeCompare(right.label, undefined, { numeric: true }));
}

function HyeRunSummary({ label, row, duplicates }: { label: "A" | "B"; row?: ProjectResearcherRun; duplicates: number }) {
  if (!row) return <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">HYE-{label} is not in this worklist</div>;
  const fileState = row.raw_file ? "File " + row.raw_file.status : "Waiting for raw file";
  const processorState = row.processing_job?.node_name || (row.processing_job ? "Processor assigned" : "Not queued");
  return (
    <div className="min-w-0 rounded-md bg-muted px-3 py-2">
      <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-semibold text-muted-foreground">HYE-{label}</span><StatusBadge status={row.run.status} />{row.processing_job ? <StatusBadge status={row.processing_job.status} /> : null}</div>
      <div className="mt-1 truncate text-sm font-medium" title={row.raw_file?.filename || row.run.expected_filename}>{row.raw_file?.filename || row.run.expected_filename || row.run.run_name}</div>
      <div className="mt-1 text-xs text-muted-foreground">{fileState} / {processorState}{duplicates > 0 ? " / " + (duplicates + 1) + " entries" : ""}</div>
    </div>
  );
}

function workspaceSectionPath(projectId: number, experimentId: number | null, section: string) {
  return experimentId
    ? `/projects/${projectId}/experiments/${experimentId}/${section}`
    : `/projects/${projectId}/${section}`;
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

          <div className="rounded-md bg-muted p-3">
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

        <div className="rounded-md bg-secondary p-3">
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
    return <div className="rounded-md bg-muted p-4 text-sm text-muted-foreground">No rows parsed yet. Expected columns include sample, run, filename, role, condition, well, and position.</div>;
  }
  return (
    <div className="table-scroll max-h-72 rounded-lg border">
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

function WorklistFilePicker({
  kind,
  file,
  count,
  required = false,
  onFile,
}: {
  kind: InstrumentWorklistKind;
  file: File | null;
  count: number;
  required?: boolean;
  onFile: (file?: File) => void;
}) {
  const instrument = kind.toUpperCase();
  return (
    <div className="min-w-0 rounded-md bg-muted p-3">
      <label className="grid cursor-pointer gap-3 focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
        <span className="flex items-start justify-between gap-2">
          <span className="min-w-0">
            <span className="block text-sm font-semibold">{instrument} worklist{required ? " · required" : " · optional"}</span>
            <span className="mt-1 block text-xs font-normal text-muted-foreground">{kind === "ms" ? "Creates the planned run sequence." : "Saved alongside MS rows as LC method/injection reference."}</span>
          </span>
          <span className="shrink-0 rounded-sm bg-background px-2.5 py-1.5 text-xs font-semibold shadow-sm">Choose file</span>
        </span>
        <input
          className="sr-only"
          type="file"
          accept=".csv,.tsv,.txt"
          aria-label={`Choose ${instrument} CSV or TSV worklist${required ? " (required)" : " (optional)"}`}
          onChange={(event) => onFile(event.target.files?.[0])}
        />
      </label>
      <div className="mt-2 flex min-w-0 items-center justify-between gap-2 border-t border-border/50 pt-2 text-xs" aria-live="polite">
        <span className="min-w-0 truncate text-muted-foreground" title={file?.name}>{file ? `${file.name} · ${count} rows parsed` : "No file selected"}</span>
        {file ? <button type="button" className="shrink-0 font-semibold text-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onFile(undefined)}>Remove</button> : null}
      </div>
      {!file && required ? <div className="mt-1 text-[11px] text-muted-foreground">MS is required. LC can be added later.</div> : null}
    </div>
  );
}

function ProjectSharingDialog({ projectId, open, onOpenChange }: { projectId: number; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [selectedUser, setSelectedUser] = useState("");
  const [error, setError] = useState("");
  const membersQuery = useQuery({
    queryKey: queryKeys.projectMembers(projectId),
    queryFn: () => fetchProjectMembers(projectId),
    enabled: open,
  });
  const addMutation = useMutation({
    mutationFn: () => shareProjectWithUser(projectId, Number(selectedUser)),
    onSuccess: async () => {
      setSelectedUser("");
      setError("");
      await queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(projectId) });
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "Could not share the project."),
  });
  const removeMutation = useMutation({
    mutationFn: (userId: number) => removeProjectMember(projectId, userId),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(projectId) }); },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "Could not remove project access."),
  });
  const directory = membersQuery.data;

  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-xl">
      <DialogHeader><DialogTitle>Project access</DialogTitle><DialogDescription>Shared users can view project data and live project watchers. They cannot edit worklists, runs, or project settings. Only active members of this project’s lab are eligible.</DialogDescription></DialogHeader>
      <div className="grid gap-3">
        <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
          <label className="grid gap-1 text-sm font-semibold" htmlFor="project-share-user">Add a lab member
            <select id="project-share-user" className="h-10 min-w-0 border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)}>
              <option value="">Select user…</option>
              {(directory?.available_users ?? []).map((user) => <option key={user.id} value={user.id}>{user.display_name} (@{user.username})</option>)}
            </select>
          </label>
          <Button type="button" disabled={!selectedUser || addMutation.isPending} onClick={() => addMutation.mutate()}>{addMutation.isPending ? "Sharing…" : "Add viewer"}</Button>
        </div>
        <div className="border-t pt-3">
          <h3 className="mb-2 text-sm font-semibold">Current viewers</h3>
          <div className="grid gap-1">
            {(directory?.members ?? []).map((member) => <div key={member.id} className="flex min-w-0 flex-wrap items-center justify-between gap-2 border border-border px-3 py-2">
              <div className="min-w-0"><div className="truncate text-sm font-medium">{member.display_name}</div><div className="text-xs text-muted-foreground">@{member.username} · read only</div></div>
              <Button type="button" size="sm" variant="ghost" aria-label={`Remove ${member.username} from this project`} disabled={removeMutation.isPending} onClick={() => { if (window.confirm(`Remove ${member.username}'s access to this project?`)) removeMutation.mutate(member.user); }}>Remove</Button>
            </div>)}
            {!directory?.members.length ? <p className="text-sm text-muted-foreground">No additional viewers have been added.</p> : null}
          </div>
        </div>
        {membersQuery.isLoading ? <p className="text-sm text-muted-foreground">Loading lab members…</p> : null}
        {error || membersQuery.isError ? <p role="alert" className="break-words text-sm text-destructive">{error || (membersQuery.error instanceof Error ? membersQuery.error.message : "Could not load project members.")}</p> : null}
      </div>
    </DialogContent>
  </Dialog>;
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

function TextField(props: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <label className="grid gap-1 text-sm font-bold">
      {props.label}
      <Input type={props.type ?? "text"} value={props.value} onChange={(event) => props.onChange(event.target.value)} required />
    </label>
  );
}
