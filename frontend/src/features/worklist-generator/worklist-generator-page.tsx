import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, FileSpreadsheet, Upload, WandSparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createWorklistMetadataTemplate,
  createWorklistPlateTemplate,
  downloadGeneratedWorklist,
  fetchAcquisitions,
  fetchExperiments,
  fetchInstrumentConfigurations,
  fetchLab,
  fetchProjects,
  generateProjectWorklist,
  queryKeys,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import type { Project, WorklistGeneratorResponse, WorklistImportResponse } from "@/lib/api/types";

const stages = [
  { label: "Metadata", description: "Describe this acquisition and its sample conditions." },
  { label: "Plate layout", description: "Complete the generated User and Manager workbook." },
  { label: "Worklists", description: "Generate instrument files and store the acquisition." },
];

function fileError(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function TemplateDownload({ file }: { file: WorklistGeneratorResponse["files"][number] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function download() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(file.url, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`Download failed (${response.status}).`);
      saveBlob(await response.blob(), file.name);
    } catch (downloadError) {
      setError(fileError(downloadError, "The workbook could not be downloaded."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-1">
      <Button type="button" variant="secondary" onClick={download} disabled={busy}>
        <Download className="h-4 w-4" />{busy ? "Downloading…" : file.name}
      </Button>
      {error ? <span className="text-xs text-destructive">{error}</span> : null}
    </div>
  );
}

export default function WorklistGeneratorPage() {
  const [searchParams] = useSearchParams();
  const requestedProjectId = Number(searchParams.get("project"));
  const requestedExperimentId = Number(searchParams.get("experiment"));
  const [selectedProjectId, setSelectedProjectId] = useState(Number.isFinite(requestedProjectId) ? String(requestedProjectId) : "");
  const [selectedExperimentId, setSelectedExperimentId] = useState("");
  const [newExperimentName, setNewExperimentName] = useState("Acquisition series 1");
  const [worklistName, setWorklistName] = useState("Acquisition 1");
  const [worklistNameTouched, setWorklistNameTouched] = useState(false);
  const [configurationId, setConfigurationId] = useState("");
  const [description, setDescription] = useState("");
  const [groupsText, setGroupsText] = useState("");
  const [metadataFile, setMetadataFile] = useState<File | null>(null);
  const [plateFile, setPlateFile] = useState<File | null>(null);
  const [stage, setStage] = useState(0);
  const [metadataResult, setMetadataResult] = useState<WorklistGeneratorResponse | null>(null);
  const [plateResult, setPlateResult] = useState<WorklistGeneratorResponse | null>(null);
  const [savedResult, setSavedResult] = useState<WorklistImportResponse | null>(null);
  const [error, setError] = useState("");
  const [downloadBusy, setDownloadBusy] = useState<"ms" | "lc" | "">("");

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects({ page: 1, page_size: 500 }),
    queryFn: () => fetchProjects({ page: 1, page_size: 500 }),
  });
  const projects = useMemo(() => projectsQuery.data?.results ?? [], [projectsQuery.data?.results]);
  const selectedProject = projects.find((project) => project.id === Number(selectedProjectId));
  const experimentsQuery = useQuery({
    queryKey: queryKeys.projectExperiments(Number(selectedProjectId)),
    queryFn: () => fetchExperiments({ project: Number(selectedProjectId), page: 1, page_size: 200 }),
    enabled: Boolean(selectedProjectId),
  });
  const experiments = useMemo(() => experimentsQuery.data?.results ?? [], [experimentsQuery.data?.results]);
  const selectedExperiment = experiments.find((experiment) => experiment.id === Number(selectedExperimentId));
  const isNewExperiment = selectedExperimentId === "new";
  const activeExperimentName = isNewExperiment ? newExperimentName.trim() : selectedExperiment?.name ?? "";
  const existingWorklistsQuery = useQuery({
    queryKey: queryKeys.acquisitions({ experiment: selectedExperiment?.id, page: 1, page_size: 500 }),
    queryFn: () => fetchAcquisitions({ experiment: selectedExperiment!.id, page: 1, page_size: 500 }),
    enabled: Boolean(selectedExperiment),
  });
  const labQuery = useQuery({
    queryKey: queryKeys.lab(selectedProject?.lab ?? 0),
    queryFn: () => fetchLab(selectedProject!.lab),
    enabled: Boolean(selectedProject?.lab),
  });
  const configurationsQuery = useQuery({
    queryKey: queryKeys.instrumentConfigurations({ page: 1, page_size: 500 }),
    queryFn: () => fetchInstrumentConfigurations({ page: 1, page_size: 500 }),
    enabled: Boolean(selectedProject),
  });
  const configurations = useMemo(
    () => (configurationsQuery.data?.results ?? []).filter(
      (configuration) => configuration.active && configuration.facility === labQuery.data?.facility && configuration.lc_instrument && configuration.ms_instrument,
    ),
    [configurationsQuery.data?.results, labQuery.data?.facility],
  );
  const groups = useMemo(() => groupsText.split(/[\n,]/).map((group) => group.trim()).filter(Boolean), [groupsText]);
  const contextReady = Boolean(selectedProject && activeExperimentName && worklistName.trim() && configurationId);

  useEffect(() => {
    if (!projects.length) return;
    if (selectedProjectId && projects.some((project) => String(project.id) === selectedProjectId)) return;
    const requested = projects.find((project) => project.id === requestedProjectId);
    setSelectedProjectId(String(requested?.id ?? projects[0].id));
  }, [projects, requestedProjectId, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || experimentsQuery.isLoading) return;
    const requestedExperiment = Number(selectedProjectId) === requestedProjectId
      ? experiments.find((experiment) => experiment.id === requestedExperimentId)
      : undefined;
    if (requestedExperiment) {
      setSelectedExperimentId(String(requestedExperiment.id));
      return;
    }
    if (experiments.length && !experiments.some((experiment) => String(experiment.id) === selectedExperimentId)) {
      setSelectedExperimentId(String(experiments[0].id));
    } else if (!experiments.length && selectedExperimentId !== "new") {
      setSelectedExperimentId("new");
    }
  }, [experiments, experimentsQuery.isLoading, requestedExperimentId, requestedProjectId, selectedExperimentId, selectedProjectId]);

  useEffect(() => {
    if (!selectedExperiment || worklistNameTouched || existingWorklistsQuery.isLoading) return;
    const numbers = (existingWorklistsQuery.data?.results ?? []).flatMap((worklist) => {
      const match = worklist.name.match(/^Acquisition\s+(\d+)$/i);
      return match ? [Number(match[1])] : [];
    });
    setWorklistName(`Acquisition ${numbers.length ? Math.max(...numbers) + 1 : 1}`);
  }, [existingWorklistsQuery.data?.results, existingWorklistsQuery.isLoading, selectedExperiment, worklistNameTouched]);

  useEffect(() => {
    if (configurations.length && !configurations.some((configuration) => String(configuration.id) === configurationId)) {
      setConfigurationId(String(configurations[0].id));
    } else if (!configurations.length && configurationId) {
      setConfigurationId("");
    }
  }, [configurationId, configurations]);

  const metadataMutation = useMutation({
    mutationFn: () => createWorklistMetadataTemplate({
      name: selectedProject?.title ?? "",
      description,
      groups,
    }),
    onSuccess: (result) => {
      setMetadataResult(result);
      setStage(1);
      setError("");
    },
    onError: (mutationError) => setError(fileError(mutationError, "The metadata workbook could not be created.")),
  });
  const plateMutation = useMutation({
    mutationFn: () => createWorklistPlateTemplate(metadataFile!),
    onSuccess: (result) => {
      setPlateResult(result);
      setStage(2);
      setError("");
    },
    onError: (mutationError) => setError(fileError(mutationError, "The plate-layout workbook could not be created.")),
  });
  const generateMutation = useMutation({
    mutationFn: () => generateProjectWorklist(Number(selectedProjectId), plateFile!, {
      worklistName: worklistName.trim(),
      experimentName: activeExperimentName,
      instrumentConfigurationId: Number(configurationId),
      generatorMetadata: {
        source: "worklist_generator",
        description,
        conditions: groups,
        project_id: Number(selectedProjectId),
        experiment_selection: isNewExperiment ? "new" : "existing",
      },
    }),
    onSuccess: async (result) => {
      setSavedResult(result);
      setWorklistNameTouched(true);
      setError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.projectExperiments(Number(selectedProjectId)) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.experiment(result.worklist.experiment) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.projectResearcherStatus(Number(selectedProjectId)) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.acquisitions({ experiment: result.worklist.experiment, page: 1, page_size: 500 }) }),
      ]);
    },
    onError: (mutationError) => setError(fileError(mutationError, "The worklist could not be generated and stored.")),
  });

  async function downloadCsv(kind: "ms" | "lc") {
    if (!savedResult) return;
    setDownloadBusy(kind);
    setError("");
    try {
      const blob = await downloadGeneratedWorklist(savedResult.worklist.id, kind);
      saveBlob(blob, savedResult.generator?.[kind === "ms" ? "ms_csv" : "lc_csv"] ?? `${worklistName}_${kind.toUpperCase()}.csv`);
    } catch (downloadError) {
      setError(fileError(downloadError, "The generated CSV could not be downloaded."));
    } finally {
      setDownloadBusy("");
    }
  }

  function resetForTargetChange() {
    setStage(0);
    setMetadataResult(null);
    setPlateResult(null);
    setSavedResult(null);
    setWorklistNameTouched(false);
    setMetadataFile(null);
    setPlateFile(null);
    setError("");
  }

  function startAnotherWorklist() {
    const current = worklistName.trim();
    const match = current.match(/^(.*?)(?:\s+(\d+))?$/);
    const base = match?.[1]?.trim() || "Acquisition";
    const next = match?.[2] ? Number(match[2]) + 1 : 2;
    setWorklistName(`${base} ${next}`);
    setDescription("");
    setGroupsText("");
    setMetadataFile(null);
    setPlateFile(null);
    setStage(0);
    setMetadataResult(null);
    setPlateResult(null);
    setSavedResult(null);
    setWorklistNameTouched(true);
    setError("");
  }

  return (
    <div className="grid min-w-0 gap-4">
      <Breadcrumbs items={[{ label: "Projects", href: "/projects" }, { label: "Full setup" }, { label: "Worklist Generator" }]} />
      <PageHero
        eyebrow="Project acquisition setup"
        title="Worklist Generator"
        description="Build an acquisition with the worklist generator. Each saved worklist belongs to one experiment, keeping separate acquisition series available for later QC and analysis."
      />

      <Card>
        <CardHeader>
          <CardTitle>Project and acquisition</CardTitle>
          <CardDescription>Choose the project, the experiment that groups acquisitions for analysis, and the managed LC-MS setup used for this worklist.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <label className="grid min-w-0 gap-1 text-sm font-semibold">
            Project
            <Select value={selectedProjectId} onValueChange={(value) => {
              resetForTargetChange();
              setSelectedProjectId(value);
              setSelectedExperimentId("");
              setWorklistNameTouched(false);
            }}>
              <SelectTrigger><SelectValue placeholder={projectsQuery.isLoading ? "Loading projects…" : "Select a project"} /></SelectTrigger>
              <SelectContent>{projects.map((project: Project) => <SelectItem key={project.id} value={String(project.id)}>{project.code} · {project.title}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <label className="grid min-w-0 gap-1 text-sm font-semibold">
            Experiment
            <Select value={selectedExperimentId} onValueChange={(value) => {
              resetForTargetChange();
              setSelectedExperimentId(value);
              setWorklistNameTouched(false);
            }} disabled={!selectedProjectId || experimentsQuery.isLoading}>
              <SelectTrigger><SelectValue placeholder="Select an experiment" /></SelectTrigger>
              <SelectContent>
                {experiments.map((experiment) => <SelectItem key={experiment.id} value={String(experiment.id)}>{experiment.name}</SelectItem>)}
                <SelectItem value="new">Create experiment for this acquisition</SelectItem>
              </SelectContent>
            </Select>
          </label>
          <label className="grid min-w-0 gap-1 text-sm font-semibold">
            Worklist name
            <Input value={worklistName} onChange={(event) => { setWorklistNameTouched(true); setWorklistName(event.target.value); }} placeholder="e.g. Acquisition 2" />
          </label>
          {isNewExperiment ? (
            <label className="grid min-w-0 gap-1 text-sm font-semibold">
              New experiment name
              <Input value={newExperimentName} onChange={(event) => setNewExperimentName(event.target.value)} placeholder="e.g. Follow-up acquisition" />
            </label>
          ) : null}
          <label className="grid min-w-0 gap-1 text-sm font-semibold md:col-span-2 xl:col-span-2">
            LC-MS setup
            <Select value={configurationId} onValueChange={setConfigurationId} disabled={!configurations.length}>
              <SelectTrigger><SelectValue placeholder="No active LC-MS setup available" /></SelectTrigger>
              <SelectContent>{configurations.map((configuration) => <SelectItem key={configuration.id} value={String(configuration.id)}>{configuration.name}{configuration.method_name ? ` · ${configuration.method_name}` : ""}</SelectItem>)}</SelectContent>
            </Select>
            {!configurations.length ? <span className="text-xs font-normal text-muted-foreground">Ask a facility manager to add an active LC-MS setup for this project’s facility.</span> : null}
          </label>
        </CardContent>
      </Card>

      <div className="grid gap-2 md:grid-cols-3">
        {stages.map((item, index) => (
          <button
            key={item.label}
            type="button"
            onClick={() => setStage(index)}
            disabled={index === 1 && !metadataResult || index === 2 && !plateResult}
            aria-current={index === stage ? "step" : undefined}
            className={`min-w-0 rounded-md border p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60 ${index === stage ? "border-primary bg-primary/10 text-foreground" : index < stage ? "border-success/40 bg-success/5 text-foreground" : "bg-card text-muted-foreground"}`}
          >
            <div className="text-xs font-semibold uppercase tracking-wide">Step {index + 1}</div>
            <div className="mt-1 font-semibold">{item.label}</div>
            <div className="mt-1 text-xs font-normal text-muted-foreground">{item.description}</div>
          </button>
        ))}
      </div>

      {metadataResult && stage !== 0 ? (
        <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm" role="status">
          Metadata workbook available:
          <div className="mt-2 flex flex-wrap gap-2">{metadataResult.files.map((file) => <TemplateDownload key={file.name} file={file} />)}</div>
        </div>
      ) : null}
      {plateResult && stage === 2 ? (
        <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm" role="status">
          Plate-layout workbook available:
          <div className="mt-2 flex flex-wrap gap-2">{plateResult.files.map((file) => <TemplateDownload key={file.name} file={file} />)}</div>
        </div>
      ) : null}

      {stage === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><WandSparkles className="h-5 w-5 text-accent" /> Generate metadata workbook</CardTitle>
            <CardDescription>The project name is already registered above. Add acquisition notes and condition names, then complete the generated workbook before continuing.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-1 text-sm font-semibold">
              Acquisition description
              <Textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Describe this acquisition and what distinguishes it from other worklists in the experiment." />
            </label>
            <label className="grid gap-1 text-sm font-semibold">
              Sample conditions
              <Textarea value={groupsText} onChange={(event) => setGroupsText(event.target.value)} placeholder={"e.g., Control\nTreatment"} />
              <span className="text-xs font-normal text-muted-foreground">{groups.length} condition{groups.length === 1 ? "" : "s"} detected.</span>
            </label>
            {metadataResult ? <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm">Metadata workbook ready. Download it, complete it, then continue to Step 2.<div className="mt-3 flex flex-wrap gap-2">{metadataResult.files.map((file) => <TemplateDownload key={file.name} file={file} />)}</div></div> : null}
            <div className="flex justify-end">
              <Button type="button" onClick={() => metadataMutation.mutate()} disabled={!contextReady || groups.length === 0 || metadataMutation.isPending}>
                {metadataMutation.isPending ? "Generating…" : "Generate metadata workbook"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {stage === 1 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Upload className="h-5 w-5 text-accent" /> Generate plate-layout workbook</CardTitle>
            <CardDescription>Upload the completed metadata workbook. The generated User and Manager sheets will carry this acquisition’s condition labels into the sequence worklist.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-2 text-sm font-semibold">
              Completed metadata workbook
              <span className="flex flex-wrap items-center gap-3 rounded-md border border-dashed p-3 font-normal">
                <FileSpreadsheet className="h-5 w-5 shrink-0 text-accent" />
                <input type="file" accept=".xlsx,.xlsm" onChange={(event) => setMetadataFile(event.target.files?.[0] ?? null)} className="min-w-0 text-sm" />
              </span>
            </label>
            {plateResult ? <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm">Plate-layout workbook ready. Download it, complete the User and Manager sheets, then continue to Step 3.<div className="mt-3 flex flex-wrap gap-2">{plateResult.files.map((file) => <TemplateDownload key={file.name} file={file} />)}</div></div> : null}
            <div className="flex justify-between gap-2">
              <Button type="button" variant="secondary" onClick={() => setStage(0)}>Back</Button>
              <Button type="button" onClick={() => plateMutation.mutate()} disabled={!metadataFile || plateMutation.isPending}>{plateMutation.isPending ? "Generating…" : "Generate plate-layout workbook"}</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {stage === 2 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><FileSpreadsheet className="h-5 w-5 text-accent" /> Generate and store acquisition worklist</CardTitle>
            <CardDescription>Upload the completed User and Manager workbook. MSConnect gives instrument filenames an acquisition-specific tag so repeated samples remain uniquely matchable, then stores the files, sample roles, metadata, configuration, and worklist under the selected project and experiment.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-2 text-sm font-semibold">
              Completed User and Manager workbook
              <span className="flex flex-wrap items-center gap-3 rounded-md border border-dashed p-3 font-normal">
                <FileSpreadsheet className="h-5 w-5 shrink-0 text-accent" />
                <input type="file" accept=".xlsx,.xlsm" onChange={(event) => setPlateFile(event.target.files?.[0] ?? null)} className="min-w-0 text-sm" />
              </span>
            </label>
            {error ? <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{error}</div> : null}
            {savedResult ? (
              <div className="grid gap-3 rounded-md border border-success/40 bg-success/5 p-4" role="status">
                <div className="flex items-center gap-2 font-semibold text-success"><CheckCircle2 className="h-5 w-5" /> Worklist saved to {selectedProject?.code} · {activeExperimentName}</div>
                <p className="text-sm text-muted-foreground">{savedResult.runs_imported} runs and {savedResult.samples_imported} tagged samples are stored with “{savedResult.worklist.name}”. This experiment keeps its acquisitions together for QC and analysis.</p>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" onClick={() => downloadCsv("ms")} disabled={Boolean(downloadBusy)}>{downloadBusy === "ms" ? "Downloading…" : "Download MS CSV"}</Button>
                  <Button type="button" variant="secondary" onClick={() => downloadCsv("lc")} disabled={Boolean(downloadBusy)}>{downloadBusy === "lc" ? "Downloading…" : "Download LC CSV"}</Button>
                  <Button type="button" variant="secondary" onClick={startAnotherWorklist}>Create another worklist</Button>
                  <Button asChild><Link to={`/projects/${selectedProjectId}/experiments/${savedResult.worklist.experiment}/worklists`}>Open experiment worklists</Link></Button>
                </div>
              </div>
            ) : null}
            <div className="flex justify-between gap-2">
              <Button type="button" variant="secondary" onClick={() => setStage(1)}>Back</Button>
              <Button type="button" onClick={() => generateMutation.mutate()} disabled={!plateFile || !contextReady || generateMutation.isPending || Boolean(savedResult)}>
                {generateMutation.isPending ? "Generating and saving…" : "Generate and save worklists"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {projectsQuery.isError ? <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{fileError(projectsQuery.error, "Projects could not be loaded.")}</div> : null}
      {projectsQuery.isSuccess && projects.length === 0 ? <Card><CardContent className="flex flex-wrap items-center justify-between gap-3 p-5"><p className="text-sm text-muted-foreground">Create a project before setting up an acquisition worklist.</p><Button asChild><Link to="/projects">Open projects</Link></Button></CardContent></Card> : null}
      {selectedProject && configurationsQuery.isError ? <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">LC-MS configurations could not be loaded.</div> : null}
    </div>
  );
}
