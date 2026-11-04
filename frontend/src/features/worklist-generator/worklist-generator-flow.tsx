import { useMemo, useState } from "react";
import { CheckCircle2, Download, FileSpreadsheet, Upload, WandSparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type GeneratedFile = { kind: string; name: string; url: string };
type GenerationResponse = { job_id: string; files: GeneratedFile[] };

const stages = [
  { label: "Metadata", description: "Describe the project and conditions." },
  { label: "Plate layout", description: "Fill the generated User and Manager workbook." },
  { label: "Worklists", description: "Generate the instrument-ready MS and LC CSVs." },
];

function csrfToken() {
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrftoken="))
    ?.slice("csrftoken=".length) ?? "";
}

function errorMessage(payload: unknown) {
  if (!payload || typeof payload !== "object") return "The workbook could not be processed.";
  const values = Object.values(payload as Record<string, unknown>).flatMap((value) => (Array.isArray(value) ? value : [value]));
  return values.filter((value) => typeof value === "string").join(" ") || "The workbook could not be processed.";
}

async function postJson(path: string, body: unknown) {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(errorMessage(payload));
  return payload as GenerationResponse;
}

async function postFile(path: string, field: string, file: File) {
  const formData = new FormData();
  formData.append(field, file);
  const response = await fetch(path, {
    method: "POST",
    body: formData,
    credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken() },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(errorMessage(payload));
  return payload as GenerationResponse;
}

function FileDownload({ file }: { file: GeneratedFile }) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState("");

  async function downloadFile() {
    setError("");
    setIsDownloading(true);
    try {
      const response = await fetch(file.url, { credentials: "same-origin" });
      if (!response.ok) {
        throw new Error(`Download failed (${response.status}).`);
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = file.name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "The file could not be downloaded.");
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <div className="grid gap-1">
      <Button type="button" variant="secondary" onClick={downloadFile} disabled={isDownloading}>
        <Download className="h-4 w-4" />
        {isDownloading ? "Downloading…" : file.name}
      </Button>
      {error ? <span className="text-xs text-destructive">{error}</span> : null}
    </div>
  );
}

export function WorklistGeneratorFlow() {
  const [stage, setStage] = useState(0);
  const [projectName, setProjectName] = useState("");
  const [description, setDescription] = useState("");
  const [groupsText, setGroupsText] = useState("");
  const [metadataFile, setMetadataFile] = useState<File | null>(null);
  const [worklistFile, setWorklistFile] = useState<File | null>(null);
  const [metadataResult, setMetadataResult] = useState<GenerationResponse | null>(null);
  const [worklistResult, setWorklistResult] = useState<GenerationResponse | null>(null);
  const [finalResult, setFinalResult] = useState<GenerationResponse | null>(null);
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const groups = useMemo(
    () => groupsText.split(/[,\n]/).map((group) => group.trim()).filter(Boolean),
    [groupsText],
  );

  async function generateMetadata() {
    setError("");
    setIsBusy(true);
    try {
      const result = await postJson("/api/capabilities/worklist-generator/metadata/", {
        name: projectName,
        description,
        groups,
      });
      setMetadataResult(result);
      setStage(1);
    } catch (generationError) {
      setError(generationError instanceof Error ? generationError.message : "The metadata workbook could not be created.");
    } finally {
      setIsBusy(false);
    }
  }

  async function generateWorklistTemplate() {
    if (!metadataFile) return;
    setError("");
    setIsBusy(true);
    try {
      const result = await postFile("/api/capabilities/worklist-generator/worklist-template/", "metadata", metadataFile);
      setWorklistResult(result);
      setStage(2);
    } catch (generationError) {
      setError(generationError instanceof Error ? generationError.message : "The worklist template could not be created.");
    } finally {
      setIsBusy(false);
    }
  }

  async function generateWorklists() {
    if (!worklistFile) return;
    setError("");
    setIsBusy(true);
    try {
      const result = await postFile("/api/capabilities/worklist-generator/generate/", "worklist", worklistFile);
      setFinalResult(result);
    } catch (generationError) {
      setError(generationError instanceof Error ? generationError.message : "The worklists could not be generated.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="grid gap-5">
      <div className="grid gap-2 md:grid-cols-3">
        {stages.map((item, index) => (
          <button
            key={item.label}
            type="button"
            onClick={() => setStage(index)}
            disabled={index === 1 && !metadataResult || index === 2 && !worklistResult}
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
        <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm" role="status" aria-live="polite">
          Metadata workbook available:
          <div className="mt-2 flex flex-wrap gap-2">{metadataResult.files.map((file) => <FileDownload key={file.name} file={file} />)}</div>
        </div>
      ) : null}
      {worklistResult && stage === 2 ? (
        <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm" role="status" aria-live="polite">
          Plate-layout workbook available:
          <div className="mt-2 flex flex-wrap gap-2">{worklistResult.files.map((file) => <FileDownload key={file.name} file={file} />)}</div>
        </div>
      ) : null}

      {stage === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><WandSparkles className="h-5 w-5 text-accent" /> Generate metadata workbook</CardTitle>
            <CardDescription>Enter the project outline and initial condition names. You will complete the generated Excel workbook before continuing.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-1 text-sm font-bold">
              Project name
              <Input name="project_name" autoComplete="off" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="e.g., Plasma cohort" />
            </label>
            <label className="grid gap-1 text-sm font-bold">
              Project description
              <textarea name="project_description" autoComplete="off" className="min-h-24 rounded-md border border-input bg-background px-3 py-2 text-sm font-normal" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Describe the experiment and its purpose…" />
            </label>
            <label className="grid gap-1 text-sm font-bold">
              Conditions
              <textarea name="conditions" autoComplete="off" className="min-h-28 rounded-md border border-input bg-background px-3 py-2 text-sm font-normal" value={groupsText} onChange={(event) => setGroupsText(event.target.value)} placeholder={"e.g., Control\nTreatment"} />
              <span className="text-xs font-normal text-muted-foreground">{groups.length} condition{groups.length === 1 ? "" : "s"} detected.</span>
            </label>
            {metadataResult ? (
              <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm" role="status" aria-live="polite">
                Metadata workbook ready. Download it, complete it in Excel, then continue to Step 2.
                <div className="mt-3 flex flex-wrap gap-2">{metadataResult.files.map((file) => <FileDownload key={file.name} file={file} />)}</div>
              </div>
            ) : null}
            <div className="flex justify-end">
              <Button type="button" onClick={generateMetadata} disabled={isBusy || !projectName.trim() || groups.length === 0}>
                {isBusy ? "Generating…" : "Generate metadata workbook"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {stage === 1 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Upload className="h-5 w-5 text-accent" /> Generate plate-layout workbook</CardTitle>
            <CardDescription>Upload the completed metadata workbook from Step 1. WLG will create the workbook with your conditions ready on the User sheet.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-2 text-sm font-bold" htmlFor="metadata-workbook">
              Completed metadata workbook
              <span className="flex items-center gap-3 rounded-md border border-dashed p-3 font-normal">
                <FileSpreadsheet className="h-5 w-5 shrink-0 text-accent" />
                <input id="metadata-workbook" name="metadata_workbook" type="file" accept=".xlsx,.xlsm" onChange={(event) => setMetadataFile(event.target.files?.[0] ?? null)} className="min-w-0 text-sm" />
              </span>
            </label>
            {metadataFile ? <p className="text-sm text-muted-foreground">Selected: {metadataFile.name}</p> : null}
            {worklistResult ? (
              <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm" role="status" aria-live="polite">
                Plate-layout workbook ready. Download it, complete the User and Manager sheets, then continue to Step 3.
                <div className="mt-3 flex flex-wrap gap-2">{worklistResult.files.map((file) => <FileDownload key={file.name} file={file} />)}</div>
              </div>
            ) : null}
            <div className="flex justify-between gap-2">
              <Button type="button" variant="secondary" onClick={() => setStage(0)}>Back</Button>
              <Button type="button" onClick={generateWorklistTemplate} disabled={isBusy || !metadataFile}>
                {isBusy ? "Generating…" : "Generate plate-layout workbook"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {stage === 2 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-accent" /> Generate MS and LC worklists</CardTitle>
            <CardDescription>Upload the completed User and Manager workbook. The validated vendor CSV files will be available for download.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-2 text-sm font-bold" htmlFor="completed-worklist">
              Completed plate-layout workbook
              <span className="flex items-center gap-3 rounded-md border border-dashed p-3 font-normal">
                <FileSpreadsheet className="h-5 w-5 shrink-0 text-accent" />
                <input id="completed-worklist" name="completed_worklist" type="file" accept=".xlsx,.xlsm" onChange={(event) => { setWorklistFile(event.target.files?.[0] ?? null); setFinalResult(null); }} className="min-w-0 text-sm" />
              </span>
            </label>
            {worklistFile ? <p className="text-sm text-muted-foreground">Selected: {worklistFile.name}</p> : null}
            {finalResult ? (
              <div className="rounded-md border border-success/40 bg-success/5 p-3 text-sm" role="status" aria-live="polite">
                Worklists ready. Download both files before leaving this flow.
                <div className="mt-3 flex flex-wrap gap-2">{finalResult.files.map((file) => <FileDownload key={file.name} file={file} />)}</div>
              </div>
            ) : null}
            <div className="flex justify-between gap-2">
              <Button type="button" variant="secondary" onClick={() => setStage(1)}>Back</Button>
              <Button type="button" onClick={generateWorklists} disabled={isBusy || !worklistFile}>
                {isBusy ? "Generating…" : "Generate MS + LC CSVs"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {error ? <p role="alert" aria-live="polite" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
