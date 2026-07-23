import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus, Search, Wand2 } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";
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
import { createPreAcquisitionSetup, fetchInstrumentConfigurations, fetchProjects, queryKeys } from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import { projectColumns } from "@/features/projects/table-columns";

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

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
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
  const [processingPreset, setProcessingPreset] = useState("Standard DIA-NN plasma");
  const [fastaUploadName, setFastaUploadName] = useState("");
  const [speclibUploadName, setSpeclibUploadName] = useState("");
  const [diannVersion, setDiannVersion] = useState("1.9");

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
  const setupMutation = useMutation({
    mutationFn: createPreAcquisitionSetup,
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects(params) });
      setDialogOpen(false);
      setStep(0);
      navigate(`/projects/${response.project.id}`);
    },
    onError: (error) => {
      setSetupError(error instanceof Error ? error.message : "Could not create pre-acquisition project.");
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

    setupMutation.mutate({
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
      fasta_upload_name: fastaUploadName,
      speclib_upload_name: speclibUploadName,
      diann_version: diannVersion,
      diann_settings: settingsForPreset(processingPreset),
    });
  }

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
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4" />
                  New project
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
                          <Select value={processingPreset} onValueChange={setProcessingPreset}>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="Standard DIA-NN plasma">Standard DIA-NN plasma</SelectItem>
                              <SelectItem value="High confidence IDs">High confidence IDs</SelectItem>
                              <SelectItem value="Fast smoke test">Fast smoke test</SelectItem>
                            </SelectContent>
                          </Select>
                        </label>
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
                        <TextField label="DIA-NN version" value={diannVersion} onChange={setDiannVersion} />
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
                    </section>
                  ) : null}

                  {step === 4 ? (
                    <section className="grid gap-3 md:grid-cols-2">
                      <Metric label="Project" value={projectForm.code || "-"} detail={projectForm.title} />
                      <Metric label="Samples" value={samples.length} detail={`${conditionCounts.healthy ?? 0} healthy, ${conditionCounts.diseased ?? 0} diseased`} />
                      <Metric label="Plate" value={`${plateType} well`} detail={`HYE every ${hyeInterval || 0} samples`} />
                      <Metric label="Runs" value={plannedRunCount} detail={`${hyePairCount} HYE pairs`} />
                      <Metric label="Processing" value={processingPreset} detail={`${organisms.join(", ")} on DIA-NN ${diannVersion}`} />
                      <Metric
                        label="Configuration"
                        value={configurationName(configurationQuery.data?.results ?? [], instrumentConfiguration)}
                        detail="Saved lab LC-MS setup"
                      />
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
  if (preset === "Fast smoke test") return { q_value: 0.01, matrices: false, threads: 4 };
  if (preset === "High confidence IDs") return { q_value: 0.005, matrices: true, protein_inference: "strict", threads: 8 };
  return { q_value: 0.01, matrices: true, threads: 8 };
}

function configurationName(configurations: Array<{ id: number; name: string }>, value: string) {
  if (value === "none") return "No saved configuration";
  return configurations.find((configuration) => String(configuration.id) === value)?.name ?? "Selected configuration";
}
