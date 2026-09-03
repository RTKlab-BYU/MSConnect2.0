import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus, Search, Wand2 } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  createPreAcquisitionSetup,
  fetchInstrumentConfigurations,
  fetchProjects,
  previewPreAcquisitionSetup,
  quickStartProject,
  queryKeys,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import { projectColumns } from "@/features/projects/table-columns";
import type { PreAcquisitionSetupPreflightResponse } from "@/lib/api/types";

type SampleDraft = {
  sample_id: string;
  condition: string;
  well: string;
  plate: string;
  metadata: Record<string, string>;
};

const wizardSteps = ["Project", "Samples", "Plate", "Acquisition", "Review"];
const conditionStyles: Record<string, string> = {
  healthy: "border-emerald-300 bg-emerald-100 text-emerald-950",
  diseased: "border-rose-300 bg-rose-100 text-rose-950",
  hye: "border-sky-300 bg-sky-100 text-sky-950",
};
const DIANN_PRESET_SPECLIB_BUILD = "DIA-NN speclib build";
const DIANN_PRESET_SPECLIB_REUSE = "DIA-NN speclib reuse";
const DIANN_PRESET_SMOKE = "DIA-NN smoke test";
const shieldHumanFastaPath = "/Volumes/T7_Shield/msconnect/shared/reference/human.fasta";
const shieldHumanSpeclibPath = "/Volumes/T7_Shield/msconnect/shared/reference/human.speclib";
const shieldHumanDemoRows = [
  "EN1033_TB500_NanoAG_rep1_ch2_GC13_DIA100win2uL_run42",
  "EN1033_GLP_NanoAG_rep1_ch2_GC2_DIA100win2uL_run34",
  "EN1033_TB500_UFBW_rep1_ch2_GD12_DIA100win2uL_run26",
  "EN1033_GLP_BacStat_rep1_ch1_GB3_DIA100win2uL_run9",
];

function parseDiannSettings(text: string) {
  try {
    const parsed = JSON.parse(text);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      return { error: "DIA-NN settings must be a JSON object." };
    }
    return { value: parsed as Record<string, unknown> };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "DIA-NN settings must be valid JSON." };
  }
}

function tagEntries(value: Record<string, unknown> | null | undefined) {
  return Object.entries(value ?? {})
    .filter(([, tagValue]) => tagValue !== undefined && tagValue !== null && `${tagValue}`.trim() !== "")
    .map(([key, tagValue]) => ({ key, value: tagValue }));
}

function formatTagValue(value: unknown) {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return "-";
}

function buildShieldHumanSampleText() {
  return ["sample_id,condition,subject_id,timepoint", ...shieldHumanDemoRows.map((sampleId, index) => `${sampleId},healthy,SHIELD-${String(index + 1).padStart(3, "0")},baseline`)].join("\n");
}

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [quickStartOpen, setQuickStartOpen] = useState(false);
  const [quickStartError, setQuickStartError] = useState("");
  const [quickStartForm, setQuickStartForm] = useState({
    title: "Untitled DIA Project",
    code: "",
  });
  const [step, setStep] = useState(0);
  const [setupError, setSetupError] = useState("");
  const [projectForm, setProjectForm] = useState({
    title: "Healthy vs Diseased Plasma Proteome Cohort",
    code: `DIA-${new Date().toISOString().slice(2, 10).replaceAll("-", "")}`,
    experimentName: "Discovery DIA",
    worklistName: "Plate 1 DIA acquisition order",
  });
  const [sampleText, setSampleText] = useState(buildDemoSampleText(12));
  const [plateType, setPlateType] = useState<"96" | "384">("96");
  const [hyeInterval, setHyeInterval] = useState("10");
  const [instrumentConfiguration, setInstrumentConfiguration] = useState("none");
  const [organisms, setOrganisms] = useState(["human", "yeast", "ecoli"]);
  const [processingPreset, setProcessingPreset] = useState(DIANN_PRESET_SPECLIB_BUILD);
  const [fastaPath, setFastaPath] = useState("/data/shared/reference/human.fasta");
  const [speclibPath, setSpeclibPath] = useState("/data/shared/reference/human.speclib");
  const [fastaUploadName, setFastaUploadName] = useState("");
  const [speclibUploadName, setSpeclibUploadName] = useState("");
  const [speclibScope, setSpeclibScope] = useState<"experiment" | "project">("experiment");
  const [speclibBuildRuns, setSpeclibBuildRuns] = useState("3");
  const [diannVersion, setDiannVersion] = useState("2.0");
  const [diannSettingsText, setDiannSettingsText] = useState(() => JSON.stringify(settingsForPreset(DIANN_PRESET_SPECLIB_BUILD), null, 2));
  const [preflightPreview, setPreflightPreview] = useState<PreAcquisitionSetupPreflightResponse | null>(null);
  const [preflightError, setPreflightError] = useState("");

  const params = useMemo(
    () => ({
      page: 1,
      page_size: 100,
      search,
      status: status === "all" ? "" : status,
    }),
    [search, status],
  );
  const projectQuery = useQuery({
    queryKey: queryKeys.projects(params),
    queryFn: () => fetchProjects(params),
  });
  const configurationQuery = useQuery({
    queryKey: queryKeys.instrumentConfigurations({ page: 1, page_size: 100 }),
    queryFn: () => fetchInstrumentConfigurations({ page: 1, page_size: 100 }),
  });

  const samples = useMemo(() => assignWells(parseSampleText(sampleText), plateType), [sampleText, plateType]);
  const conditionCounts = useMemo(() => countConditions(samples), [samples]);
  const hyePairCount = Number(hyeInterval) > 0 ? Math.floor(samples.length / Number(hyeInterval)) : 0;
  const plannedRunCount = samples.length + hyePairCount * 2;
  const diannSettings = useMemo(() => parseDiannSettings(diannSettingsText), [diannSettingsText]);
  const preflightTone = {
    card: "border-sky-300 bg-sky-50/80",
    banner: "border-sky-300 bg-sky-100 text-sky-950",
    chip: "border-sky-300 bg-sky-100 text-sky-950",
  };
  const setupPayload = useMemo(
    () => ({
      title: projectForm.title,
      code: projectForm.code,
      sample_rows: samples.map((sample) => ({
        sample_id: sample.sample_id,
        condition: sample.condition,
        well: sample.well,
        plate: sample.plate,
        ...sample.metadata,
      })),
      plate_type: plateType,
      hye_interval: Number(hyeInterval),
      experiment_name: projectForm.experimentName,
      worklist_name: projectForm.worklistName,
      instrument_configuration: instrumentConfiguration === "none" ? null : Number(instrumentConfiguration),
      organisms,
      processing_preset: processingPreset,
      fasta_path: fastaPath,
      speclib_path: speclibPath,
      fasta_upload_name: fastaUploadName,
      speclib_upload_name: speclibUploadName,
      speclib_scope: speclibScope,
      speclib_build_runs: Number(speclibBuildRuns),
      diann_version: diannVersion,
      diann_settings: diannSettings.value ?? {},
    }),
    [
      diannSettings.value,
      diannVersion,
      fastaPath,
      fastaUploadName,
      hyeInterval,
      instrumentConfiguration,
      organisms,
      plateType,
      processingPreset,
      projectForm.code,
      projectForm.experimentName,
      projectForm.title,
      projectForm.worklistName,
      samples,
      speclibPath,
      speclibUploadName,
      speclibScope,
      speclibBuildRuns,
    ],
  );
  const setupMutation = useMutation({
    mutationFn: createPreAcquisitionSetup,
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects(params) });
      setDialogOpen(false);
      setStep(0);
      navigate(response.experiment?.id ? `/projects/${response.project.id}/experiments/${response.experiment.id}` : `/projects/${response.project.id}`);
    },
    onError: (error) => {
      setSetupError(error instanceof Error ? error.message : "Could not create pre-acquisition project.");
    },
  });
  const previewMutation = useMutation({
    mutationFn: previewPreAcquisitionSetup,
    onSuccess: (response) => {
      setPreflightPreview(response);
      setPreflightError("");
    },
    onError: (error) => {
      setPreflightError(error instanceof Error ? error.message : "Could not preview pre-acquisition setup.");
      setPreflightPreview(null);
    },
  });
  const quickStartMutation = useMutation({
    mutationFn: quickStartProject,
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects(params) });
      setQuickStartOpen(false);
      navigate(response.experiment?.id ? `/projects/${response.project.id}/experiments/${response.experiment.id}` : `/projects/${response.project.id}`);
    },
    onError: (error) => {
      setQuickStartError(error instanceof Error ? error.message : "Could not create quick-start project.");
    },
  });

  function submitSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSetupError("");
    if (!samples.length) {
      setSetupError("Add at least one sample row with sample_id and condition.");
      setStep(1);
      return;
    }

    if (diannSettings.error) {
      setSetupError(diannSettings.error);
      setStep(3);
      return;
    }

    setupMutation.mutate(setupPayload);
  }

  function submitQuickStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuickStartError("");
    quickStartMutation.mutate({
      title: quickStartForm.title,
      code: quickStartForm.code || undefined,
    });
  }

  function seedShieldHumanPreview() {
    setProjectForm((current) => ({
      ...current,
      title: "T7 Shield Human DIA Preview",
      experimentName: "Shield human preview",
      worklistName: "Shield human preview worklist",
    }));
    setSampleText(buildShieldHumanSampleText());
    setPlateType("96");
    setHyeInterval("0");
    setInstrumentConfiguration("none");
    setOrganisms(["human"]);
    setProcessingPreset(DIANN_PRESET_SPECLIB_BUILD);
    setFastaPath(shieldHumanFastaPath);
    setSpeclibPath(shieldHumanSpeclibPath);
    setFastaUploadName("");
    setSpeclibUploadName("");
    setDiannVersion("2.0");
    setDiannSettingsText(JSON.stringify(settingsForPreset(DIANN_PRESET_SPECLIB_BUILD), null, 2));
    setPreflightPreview(null);
    setPreflightError("");
    setStep(4);
  }

  useEffect(() => {
    if (!dialogOpen || step !== 4) return;
    if (diannSettings.error) {
      setPreflightError(diannSettings.error);
      setPreflightPreview(null);
      return;
    }
    const handle = window.setTimeout(() => {
      previewMutation.mutate(setupPayload);
    }, 250);
    return () => window.clearTimeout(handle);
  }, [diannSettings.error, dialogOpen, previewMutation, setupPayload, step]);

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Projects" }]} />
      <PageHero
        eyebrow="Project operations"
        title="Projects"
        description="Start pre-acquisition projects, register samples, generate worklists, and give watcher agents expected filenames before LC-MS acquisition."
        actions={
          <>
            <StatusBadge status="active" />
            <Dialog open={quickStartOpen} onOpenChange={setQuickStartOpen}>
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4" />
                  Quick start
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Quick start project</DialogTitle>
                  <DialogDescription>Create the project now, then import or edit the LC-MS worklist from the project page.</DialogDescription>
                </DialogHeader>
                <form className="grid gap-3" onSubmit={submitQuickStart}>
                  <TextField label="Project title" value={quickStartForm.title} onChange={(title) => setQuickStartForm((current) => ({ ...current, title }))} />
                  <label className="grid gap-1 text-sm font-bold">
                    Project code
                    <Input value={quickStartForm.code} placeholder="Auto-generated if blank" onChange={(event) => setQuickStartForm((current) => ({ ...current, code: event.target.value }))} />
                  </label>
                  {quickStartError ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{quickStartError}</div> : null}
                  <div className="flex justify-end gap-2 border-t pt-3">
                    <Button type="button" variant="secondary" onClick={() => setQuickStartOpen(false)}>
                      Cancel
                    </Button>
                    <Button type="submit" disabled={quickStartMutation.isPending}>
                      {quickStartMutation.isPending ? "Creating..." : "Create project"}
                    </Button>
                  </div>
                </form>
              </DialogContent>
            </Dialog>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="secondary">
                  Advanced setup
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[92vh] max-w-5xl overflow-auto rounded-3xl p-6">
                <DialogHeader>
                  <DialogTitle className="text-2xl font-black tracking-tight">Pre-acquisition setup</DialogTitle>
                  <DialogDescription>
                    Capture only what is needed to create samples, plate positions, planned runs, expected filenames, and the DIA-NN processing plan.
                  </DialogDescription>
                </DialogHeader>
                <form className="grid gap-5" onSubmit={submitSetup}>
                  <WizardProgress step={step} />

                  {step === 0 ? (
                    <section className="grid gap-3 md:grid-cols-2">
                      <TextField label="Project title" value={projectForm.title} onChange={(title) => setProjectForm((current) => ({ ...current, title }))} />
                      <TextField label="Project code" value={projectForm.code} onChange={(code) => setProjectForm((current) => ({ ...current, code }))} />
                      <TextField label="Experiment name" value={projectForm.experimentName} onChange={(experimentName) => setProjectForm((current) => ({ ...current, experimentName }))} />
                      <TextField label="Worklist name" value={projectForm.worklistName} onChange={(worklistName) => setProjectForm((current) => ({ ...current, worklistName }))} />
                    </section>
                  ) : null}

                  {step === 1 ? (
                    <section className="grid gap-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <h3 className="text-lg font-black">Sample metadata</h3>
                          <p className="text-sm text-muted-foreground">
                            Required columns are sample_id and condition. Optional columns are stored with each sample.
                          </p>
                        </div>
                        <Button type="button" variant="secondary" onClick={() => setSampleText(buildDemoSampleText(100))}>
                          <Wand2 className="h-4 w-4" />
                          Fill 100-sample demo
                        </Button>
                      </div>
                      <textarea
                        className="min-h-64 rounded-2xl border border-input bg-background/80 px-3 py-2 font-mono text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={sampleText}
                        onChange={(event) => setSampleText(event.target.value)}
                      />
                      <div className="grid gap-3 md:grid-cols-4">
                        <Metric label="Samples" value={samples.length} />
                        <Metric label="Healthy" value={conditionCounts.healthy ?? 0} />
                        <Metric label="Diseased" value={conditionCounts.diseased ?? 0} />
                        <Metric label="Other" value={samples.length - (conditionCounts.healthy ?? 0) - (conditionCounts.diseased ?? 0)} />
                      </div>
                    </section>
                  ) : null}

                  {step === 2 ? (
                    <section className="grid gap-4">
                      <div className="grid gap-3 md:grid-cols-[180px_180px_1fr]">
                        <label className="grid gap-1 text-sm font-bold">
                          Plate type
                          <Select value={plateType} onValueChange={(value) => setPlateType(value as "96" | "384")}>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="96">96 well</SelectItem>
                              <SelectItem value="384">384 well</SelectItem>
                            </SelectContent>
                          </Select>
                        </label>
                        <TextField label="HYE interval" type="number" min={0} value={hyeInterval} onChange={setHyeInterval} />
                        <div className="rounded-2xl border bg-card p-3 text-sm">
                          <div className="font-black">{plannedRunCount} planned injections</div>
                          <div className="text-muted-foreground">
                            {samples.length} samples + {hyePairCount * 2} HYE QC injections
                          </div>
                        </div>
                      </div>
                      <PlateMap samples={samples} plateType={plateType} />
                    </section>
                  ) : null}

                  {step === 3 ? (
                    <section className="grid gap-4">
                      <div className="grid gap-3 md:grid-cols-2">
                        <label className="grid gap-1 text-sm font-bold">
                          LC-MS configuration
                          <Select value={instrumentConfiguration} onValueChange={setInstrumentConfiguration}>
                            <SelectTrigger>
                              <SelectValue placeholder="Select configuration" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="none">No saved configuration yet</SelectItem>
                              {(configurationQuery.data?.results ?? []).map((configuration) => (
                                <SelectItem key={configuration.id} value={String(configuration.id)}>
                                  {configuration.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </label>
                        <label className="grid gap-1 text-sm font-bold">
                          DIA-NN preset
                          <Select
                            value={processingPreset}
                            onValueChange={(value) => {
                              setProcessingPreset(value);
                              setDiannSettingsText(JSON.stringify(settingsForPreset(value), null, 2));
                            }}
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={DIANN_PRESET_SPECLIB_BUILD}>{DIANN_PRESET_SPECLIB_BUILD}</SelectItem>
                              <SelectItem value={DIANN_PRESET_SPECLIB_REUSE}>{DIANN_PRESET_SPECLIB_REUSE}</SelectItem>
                              <SelectItem value={DIANN_PRESET_SMOKE}>{DIANN_PRESET_SMOKE}</SelectItem>
                            </SelectContent>
                          </Select>
                          <p className="text-xs font-normal text-muted-foreground">
                            Build creates a new speclib from the shared FASTA. Reuse runs against the project speclib from an earlier pass. Smoke is a fast launcher check, not the production search path.
                          </p>
                        </label>
                      </div>
                      <div className="grid gap-3 rounded-2xl border bg-background/60 p-4 md:grid-cols-[1fr_180px]">
                        <label className="grid gap-1 text-sm font-bold">
                          Spectral-library scope
                          <Select value={speclibScope} onValueChange={(value) => setSpeclibScope(value as "experiment" | "project")}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="experiment">This experiment only</SelectItem>
                              <SelectItem value="project">Share across this project</SelectItem>
                            </SelectContent>
                          </Select>
                          <span className="text-xs font-normal text-muted-foreground">Build once, then reuse the generated library for later runs.</span>
                        </label>
                        <TextField label="Runs used to build" type="number" min={1} value={speclibBuildRuns} onChange={setSpeclibBuildRuns} />
                      </div>
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-background/60 px-4 py-3">
                        <div className="grid gap-1">
                          <div className="text-sm font-black">Shield human preview</div>
                          <div className="text-xs text-muted-foreground">
                            Prefill the review path with the T7_Shield human FASTA and a small set of real raw-file sample ids.
                          </div>
                        </div>
                        <Button type="button" variant="secondary" onClick={seedShieldHumanPreview}>
                          Seed T7_Shield human preview
                        </Button>
                      </div>
                      <div className="grid gap-3 md:grid-cols-3">
                        {[
                          ["human", "Human"],
                          ["yeast", "Yeast"],
                          ["ecoli", "E. coli"],
                        ].map(([value, label]) => (
                          <button
                            key={value}
                            type="button"
                            className={`rounded-2xl border p-4 text-left text-sm font-bold transition ${
                              organisms.includes(value) ? "border-primary bg-primary/10 text-primary" : "bg-card hover:bg-muted"
                            }`}
                            onClick={() => toggleOrganism(value, setOrganisms)}
                          >
                            {label}
                            <span className="block pt-1 text-xs font-medium text-muted-foreground">
                              Managed FASTA/SPECLIB, quarterly refresh
                            </span>
                          </button>
                        ))}
                      </div>
                      <div className="grid gap-3 md:grid-cols-3">
                        <TextField label="FASTA path" value={fastaPath} onChange={setFastaPath} />
                        <TextField label="Spectral library path" value={speclibPath} onChange={setSpeclibPath} />
                        <TextField label="DIA-NN version" value={diannVersion} onChange={setDiannVersion} />
                      </div>
                      <div className="grid gap-3 md:grid-cols-2">
                        <label className="grid gap-1 text-sm font-bold">
                          Optional FASTA upload
                          <Input type="file" accept=".fasta,.fa" onChange={(event) => setFastaUploadName(event.target.files?.[0]?.name ?? "")} />
                          {fastaUploadName ? <span className="text-xs text-muted-foreground">{fastaUploadName}</span> : null}
                        </label>
                        <label className="grid gap-1 text-sm font-bold">
                          Optional SPECLIB upload
                          <Input type="file" accept=".speclib,.tsv,.parquet" onChange={(event) => setSpeclibUploadName(event.target.files?.[0]?.name ?? "")} />
                          {speclibUploadName ? <span className="text-xs text-muted-foreground">{speclibUploadName}</span> : null}
                        </label>
                      </div>
                        <div className="grid gap-1 text-sm font-bold">
                        DIA-NN experimental settings JSON
                        <textarea
                          className="min-h-56 rounded-2xl border border-input bg-background/80 px-3 py-2 font-mono text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          value={diannSettingsText}
                          onChange={(event) => setDiannSettingsText(event.target.value)}
                        />
                        <p className="text-xs font-normal text-muted-foreground">
                          Put researcher-controlled DIA-NN options under `tags.experimental`. Performance limits such as threads and temp are controlled by the site.
                        </p>
                      </div>
                    </section>
                  ) : null}

                  {step === 4 ? (
                    <section className="grid gap-4">
                      <div className="grid gap-3 md:grid-cols-2">
                        <Metric label="Project" value={projectForm.code || "-"} detail={projectForm.title} />
                        <Metric label="Samples" value={samples.length} detail={`${conditionCounts.healthy ?? 0} healthy, ${conditionCounts.diseased ?? 0} diseased`} />
                        <Metric label="Plate" value={`${plateType} well`} detail={`HYE every ${hyeInterval || 0} samples`} />
                        <Metric label="Runs" value={plannedRunCount} detail={`${hyePairCount} HYE pairs`} />
                        <Metric label="Processing" value={processingPreset} detail={`${organisms.join(", ")} on DIA-NN ${diannVersion}`} />
                        <Metric
                          label="Speclib"
                          value={speclibModeLabel(preflightPreview?.speclib_mode ?? diannSpeclibModeForPreset(processingPreset))}
                          detail={speclibModeDetail(preflightPreview?.speclib_mode ?? diannSpeclibModeForPreset(processingPreset))}
                        />
                        <Metric
                          label="Configuration"
                          value={configurationName(configurationQuery.data?.results ?? [], instrumentConfiguration)}
                          detail="Saved lab LC-MS setup"
                        />
                      </div>
                      <Card className={`border-primary/25 ${preflightTone.card}`}>
                        <CardHeader className="pb-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <CardTitle>Resolved DIA-NN preflight</CardTitle>
                              <CardDescription>Preview the exact settings that will be created for this project before you submit it.</CardDescription>
                            </div>
                            <Button
                              type="button"
                              variant="secondary"
                              onClick={() => previewMutation.mutate(setupPayload)}
                              disabled={previewMutation.isPending || Boolean(diannSettings.error)}
                            >
                              {previewMutation.isPending ? "Refreshing..." : "Refresh preview"}
                            </Button>
                          </div>
                        </CardHeader>
                        <CardContent className="grid gap-4 xl:grid-cols-[1fr_360px]">
                          <div className="grid gap-3">
                            <div className={`rounded-2xl border px-4 py-3 ${preflightTone.banner}`}>
                              <div className="text-xs font-bold uppercase tracking-[0.16em] opacity-80">Draft setup preview</div>
                              <div className="mt-1 text-lg font-black">
                                {preflightPreview?.source_label ?? "Draft setup preview"}
                              </div>
                              <div className="mt-1 text-sm">
                                {preflightPreview?.source_detail ?? "The preview is using the draft setup and site-controlled defaults."}
                              </div>
                              <div className="mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.14em]">
                                {speclibModeLabel(preflightPreview?.speclib_mode ?? diannSpeclibModeForPreset(processingPreset))}
                              </div>
                              <div className="mt-3 inline-flex rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.14em]">
                                Draft preview
                              </div>
                            </div>
                            <div className="rounded-2xl border bg-background/80 p-3">
                              <div className="text-xs font-bold uppercase text-muted-foreground">Status</div>
                              {diannSettings.error ? (
                                <div className="mt-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">{diannSettings.error}</div>
                              ) : preflightError ? (
                                <div className="mt-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">{preflightError}</div>
                              ) : preflightPreview ? (
                                <div className="mt-2 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-950">
                                  Ready to submit. The preflight snapshot is valid and uses the site-controlled DIA-NN performance tags.
                                </div>
                              ) : (
                                <div className="mt-2 rounded-lg border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                                  Preview will appear automatically on this step.
                                </div>
                              )}
                            </div>
                            <div className="rounded-2xl border bg-background/80 p-3">
                              <div className="text-xs font-bold uppercase text-muted-foreground">Resolved settings</div>
                              <div className="mt-2 grid gap-2 text-sm">
                                <div className="rounded-lg border bg-background/70 p-3">
                                  <div className="text-xs font-bold uppercase text-muted-foreground">Preset</div>
                                  <div className="mt-1 font-semibold">{preflightPreview?.processing_preset ?? processingPreset}</div>
                                </div>
                                <div className="rounded-lg border bg-background/70 p-3">
                                  <div className="text-xs font-bold uppercase text-muted-foreground">Version</div>
                                  <div className="mt-1 font-semibold">DIA-NN {preflightPreview?.diann_version ?? diannVersion}</div>
                                </div>
                                <div className="rounded-lg border bg-background/70 p-3">
                                  <div className="text-xs font-bold uppercase text-muted-foreground">Speclib mode</div>
                                  <div className="mt-1 font-semibold">{speclibModeLabel(preflightPreview?.speclib_mode ?? diannSpeclibModeForPreset(processingPreset))}</div>
                                  <div className="mt-1 text-xs text-muted-foreground">
                                    {speclibModeDetail(preflightPreview?.speclib_mode ?? diannSpeclibModeForPreset(processingPreset))}
                                  </div>
                                </div>
                                <div className="rounded-lg border bg-background/70 p-3">
                                  <div className="text-xs font-bold uppercase text-muted-foreground">Reference assets</div>
                                  <div className="mt-1 break-all text-xs text-muted-foreground">
                                    <div>FASTA: {String(preflightPreview?.reference_assets?.fasta_path ?? fastaPath)}</div>
                                    <div>SPECLIB: {String(preflightPreview?.reference_assets?.speclib_path ?? speclibPath)}</div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="grid gap-3">
                            <div className="rounded-2xl border bg-background/80 p-3">
                              <div className="text-xs font-bold uppercase text-muted-foreground">Performance tags</div>
                              <div className="mt-2 grid gap-2">
                                {tagEntries(preflightPreview?.performance_tags).length ? (
                                  tagEntries(preflightPreview?.performance_tags).map((entry) => (
                                    <div key={entry.key} className={`rounded-lg border px-3 py-2 text-sm ${preflightTone.chip}`}>
                                      <div className="text-xs font-bold uppercase text-muted-foreground">{entry.key}</div>
                                      <div className="mt-1 font-mono">{formatTagValue(entry.value)}</div>
                                    </div>
                                  ))
                                ) : (
                                  <div className="rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">No performance tags resolved.</div>
                                )}
                              </div>
                            </div>
                            <div className="rounded-2xl border bg-background/80 p-3">
                              <div className="text-xs font-bold uppercase text-muted-foreground">Experimental tags</div>
                              <div className="mt-2 grid gap-2">
                                {tagEntries(preflightPreview?.experimental_tags).length ? (
                                  tagEntries(preflightPreview?.experimental_tags).map((entry) => (
                                    <div key={entry.key} className="rounded-lg border bg-background px-3 py-2 text-sm">
                                      <div className="text-xs font-bold uppercase text-muted-foreground">{entry.key}</div>
                                      <div className="mt-1 font-mono">{formatTagValue(entry.value)}</div>
                                    </div>
                                  ))
                                ) : (
                                  <div className="rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">No experimental tags resolved.</div>
                                )}
                              </div>
                            </div>
                            <div className="rounded-2xl border bg-background/80 p-3">
                              <div className="text-xs font-bold uppercase text-muted-foreground">Command options</div>
                              <div className="mt-2 flex flex-wrap gap-2">
                                {(preflightPreview?.options ?? []).length ? (
                                  preflightPreview?.options.map((option) => (
                                    <span key={option} className="rounded-full border bg-background px-3 py-1 font-mono text-xs">
                                      {option}
                                    </span>
                                  ))
                                ) : (
                                  <span className="text-sm text-muted-foreground">No explicit DIA-NN options resolved yet.</span>
                                )}
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </section>
                  ) : null}

                  {setupError ? <div className="rounded-2xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{setupError}</div> : null}

                  <div className="flex flex-wrap justify-between gap-2 border-t pt-4">
                    <Button type="button" variant="secondary" onClick={() => (step === 0 ? setDialogOpen(false) : setStep((current) => current - 1))}>
                      <ChevronLeft className="h-4 w-4" />
                      {step === 0 ? "Cancel" : "Back"}
                    </Button>
                    {step < wizardSteps.length - 1 ? (
                      <Button type="button" onClick={() => setStep((current) => current + 1)}>
                        Next
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    ) : (
                      <Button type="submit" disabled={setupMutation.isPending}>
                        {setupMutation.isPending ? "Creating..." : "Create project and worklist"}
                      </Button>
                    )}
                  </div>
                </form>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Find a project</CardTitle>
          <CardDescription>Search by code, title, lab, or PI and keep the list intentionally compact.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-[1fr_220px]">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input className="pl-9" placeholder="Search code, title, lab, PI..." value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="paused">Paused</SelectItem>
                <SelectItem value="complete">Complete</SelectItem>
                <SelectItem value="archived">Archived</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <DataTable columns={projectColumns} data={projectQuery.data?.results ?? []} emptyLabel={projectQuery.isLoading ? "Loading projects..." : "No projects found."} />
    </div>
  );
}

function WizardProgress({ step }: { step: number }) {
  return (
    <div className="grid gap-2 sm:grid-cols-5">
      {wizardSteps.map((label, index) => (
        <div key={label} className={`rounded-2xl border px-3 py-2 text-sm font-bold ${index <= step ? "border-primary bg-primary/10 text-primary" : "bg-card text-muted-foreground"}`}>
          {index + 1}. {label}
        </div>
      ))}
    </div>
  );
}

function TextField(props: { label: string; value: string; onChange: (value: string) => void; type?: string; min?: number }) {
  return (
    <label className="grid gap-1 text-sm font-bold">
      {props.label}
      <Input type={props.type ?? "text"} min={props.min} value={props.value} onChange={(event) => props.onChange(event.target.value)} required />
    </label>
  );
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div className="rounded-2xl border bg-card p-3">
      <div className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="pt-1 text-xl font-black">{value}</div>
      {detail ? <div className="pt-1 text-sm text-muted-foreground">{detail}</div> : null}
    </div>
  );
}

function PlateMap({ samples, plateType }: { samples: SampleDraft[]; plateType: "96" | "384" }) {
  const sampleByWell = new Map(samples.map((sample) => [sample.well, sample]));
  const wells = buildWells(plateType);
  const columns = plateType === "384" ? 24 : 12;
  return (
    <div className="overflow-auto rounded-2xl border bg-card p-3">
      <div className="grid min-w-max gap-1" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 4rem))` }}>
        {wells.map((well) => {
          const sample = sampleByWell.get(well);
          const style = sample ? conditionStyles[sample.condition] ?? "border-amber-300 bg-amber-100 text-amber-950" : "border-border bg-muted/40 text-muted-foreground";
          return (
            <div key={well} className={`h-12 w-16 rounded-xl border p-1 text-[10px] ${style}`} title={sample ? `${sample.sample_id} (${sample.condition})` : well}>
              <div className="font-black">{well}</div>
              <div className="truncate">{sample?.sample_id ?? ""}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function parseSampleText(value: string): SampleDraft[] {
  const lines = value.split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length) return [];
  const delimiter = lines[0].includes("\t") ? "\t" : ",";
  const headers = lines[0].split(delimiter).map((header) => header.trim().toLowerCase());
  const sampleIndex = findHeader(headers, ["sample_id", "sample id", "sample", "id", "name"]);
  const conditionIndex = findHeader(headers, ["condition", "group", "status"]);
  const wellIndex = findHeader(headers, ["well"]);
  const plateIndex = findHeader(headers, ["plate", "plate_id"]);
  if (sampleIndex < 0 || conditionIndex < 0) return [];

  return lines.slice(1).flatMap((line) => {
    const values = line.split(delimiter).map((item) => item.trim());
    const sampleId = values[sampleIndex] ?? "";
    if (!sampleId) return [];
    return {
      sample_id: sampleId,
      condition: (values[conditionIndex] || "sample").toLowerCase(),
      well: (values[wellIndex] || "").toUpperCase(),
      plate: values[plateIndex] || "Plate 1",
      metadata: Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
    };
  });
}

function assignWells(samples: SampleDraft[], plateType: "96" | "384") {
  const used = new Set(samples.map((sample) => sample.well).filter(Boolean));
  const wells = buildWells(plateType);
  let nextWellIndex = 0;
  return samples.map((sample) => {
    if (sample.well) return sample;
    while (used.has(wells[nextWellIndex])) nextWellIndex += 1;
    const well = wells[nextWellIndex] ?? "";
    used.add(well);
    nextWellIndex += 1;
    return { ...sample, well };
  });
}

function buildWells(plateType: "96" | "384") {
  const rows = plateType === "384" ? "ABCDEFGHIJKLMNOP".split("") : "ABCDEFGH".split("");
  const columns = plateType === "384" ? 24 : 12;
  return rows.flatMap((row) => Array.from({ length: columns }, (_, index) => `${row}${String(index + 1).padStart(2, "0")}`));
}

function findHeader(headers: string[], candidates: string[]) {
  return headers.findIndex((header) => candidates.includes(header));
}

function countConditions(samples: SampleDraft[]) {
  return samples.reduce<Record<string, number>>((counts, sample) => {
    counts[sample.condition] = (counts[sample.condition] ?? 0) + 1;
    return counts;
  }, {});
}

function buildDemoSampleText(count: number) {
  const rows = ["sample_id,condition,subject_id,timepoint"];
  for (let index = 1; index <= count; index += 1) {
    const condition = index % 2 === 0 ? "diseased" : "healthy";
    rows.push(`${condition.toUpperCase()}-${String(Math.ceil(index / 2)).padStart(3, "0")},${condition},SUBJ-${String(index).padStart(3, "0")},baseline`);
  }
  return rows.join("\n");
}

function toggleOrganism(value: string, setOrganisms: (updater: (current: string[]) => string[]) => void) {
  setOrganisms((current) => {
    if (current.includes(value)) {
      const next = current.filter((item) => item !== value);
      return next.length ? next : current;
    }
    return [...current, value];
  });
}

function settingsForPreset(preset: string) {
  if (preset === DIANN_PRESET_SMOKE) {
    return {
      tags: {
        experimental: {
          report: "diann-first-pass.parquet",
          q_value: 0.01,
          matrices: false,
          individual_reports: false,
          individual_mass_acc: false,
          individual_windows: false,
          generate_speclib: false,
          fasta_search: false,
          out_library: "",
        },
      },
    };
  }
  if (preset === DIANN_PRESET_SPECLIB_REUSE) {
    return {
      tags: {
        experimental: {
          report: "diann-report.parquet",
          q_value: 0.005,
          matrices: true,
          individual_reports: true,
          individual_mass_acc: true,
          individual_windows: true,
          generate_speclib: false,
          fasta_search: false,
          out_library: "",
        },
      },
    };
  }
  return {
    tags: {
      experimental: {
        report: "diann-first-pass.parquet",
        q_value: 0.005,
        matrices: true,
        individual_reports: true,
        individual_mass_acc: true,
        individual_windows: true,
        generate_speclib: true,
        fasta_search: true,
        out_library: "diann-first-pass.speclib",
      },
    },
  };
}

function diannSpeclibModeForPreset(preset: string) {
  if (preset === DIANN_PRESET_SPECLIB_REUSE) return "reuse";
  if (preset === DIANN_PRESET_SMOKE) return "smoke";
  return "build";
}

function speclibModeLabel(mode: string) {
  if (mode === "reuse") return "Reuse speclib";
  if (mode === "smoke") return "Smoke only";
  return "Build speclib";
}

function speclibModeDetail(mode: string) {
  if (mode === "reuse") return "Use the generated project speclib for report runs.";
  if (mode === "smoke") return "Launcher check only. Not the production search path.";
  return "Generate a project speclib on the first pass.";
}

function configurationName(configurations: Array<{ id: number; name: string }>, value: string) {
  if (value === "none") return "No saved configuration";
  return configurations.find((configuration) => String(configuration.id) === value)?.name ?? "Selected configuration";
}
