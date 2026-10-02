import { useState } from "react";
import { CheckCircle2, Download, FileSpreadsheet, WandSparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHero } from "@/components/layout/page-section";

type GeneratedFile = { kind: "ms" | "lc"; name: string; url: string };
type GenerationResponse = { job_id: string; files: GeneratedFile[] };

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

export default function WorklistGeneratorPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<GenerationResponse | null>(null);
  const [error, setError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  async function generate() {
    if (!file) {
      setError("Choose a completed .xlsx or .xlsm worklist workbook first.");
      return;
    }
    setError("");
    setResult(null);
    setIsGenerating(true);
    try {
      const formData = new FormData();
      formData.append("worklist", file);
      const response = await fetch("/api/capabilities/worklist-generator/generate/", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken() },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorMessage(payload));
      setResult(payload as GenerationResponse);
    } catch (generationError) {
      setError(generationError instanceof Error ? generationError.message : "The workbook could not be processed.");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Acquisition tools"
        title="Worklist generator"
        description="Upload a completed instrument workbook to produce the MS and LC vendor CSV files used for acquisition. The generator applies the same validation and blocking rules as the command-line tool."
      />

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><WandSparkles className="h-5 w-5 text-accent" /> Generate vendor worklists</CardTitle>
          <CardDescription>Supported inputs: Excel workbooks containing the User and Manager sheets.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <label className="block space-y-2 text-sm font-bold" htmlFor="worklist-file">
            Worklist workbook
            <span className="flex items-center gap-3 rounded-xl border border-dashed p-4 font-normal">
              <FileSpreadsheet className="h-5 w-5 shrink-0 text-accent" />
              <input
                id="worklist-file"
                type="file"
                accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="min-w-0 text-sm"
              />
            </span>
          </label>
          {file ? <p className="text-sm text-muted-foreground">Selected: {file.name}</p> : null}
          {error ? <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
          <Button type="button" onClick={generate} disabled={isGenerating || !file}>
            {isGenerating ? "Generating…" : "Generate MS + LC CSVs"}
          </Button>
        </CardContent>
      </Card>

      {result ? (
        <Card className="max-w-3xl border-emerald-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-emerald-600" /> Worklists ready</CardTitle>
            <CardDescription>Download both files before leaving this page. They are isolated to this generation run.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            {result.files.map((generatedFile) => (
              <Button key={generatedFile.kind} asChild variant="secondary">
                <a href={generatedFile.url} download><Download className="h-4 w-4" /> {generatedFile.name}</a>
              </Button>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
