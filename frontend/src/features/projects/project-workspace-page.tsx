import { useMutation, useQuery } from "@tanstack/react-query";
import { BarChart3, CheckCircle2, FileUp, HardDrive, Save, Settings2 } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
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
  fetchProjectResearcherStatus,
  importProjectWorklist,
  queueProjectReadyRuns,
  queryKeys,
  updateRun,
  updateWorklistEntry,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import { formatBytes, formatDate } from "@/lib/format";
import type { ProjectResearcherRun, WorklistImportRow } from "@/lib/api/types";

const roleOptions = ["sample", "qc", "library", "blank", "wash", "calibration"] as const;
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

export default function ProjectWorkspacePage() {
  const projectId = Number(useParams().projectId);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [worklistOpen, setWorklistOpen] = useState(false);
  const [worklistName, setWorklistName] = useState("Imported LC-MS worklist");
  const [worklistRows, setWorklistRows] = useState<WorklistImportRow[]>([]);
  const [worklistError, setWorklistError] = useState("");
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);

  const statusQuery = useQuery({
    queryKey: queryKeys.projectResearcherStatus(projectId),
    queryFn: () => fetchProjectResearcherStatus(projectId),
    enabled: Number.isFinite(projectId),
    refetchInterval: 30_000,
  });
  const data = statusQuery.data;
  const project = data?.project;
  const runs = data?.runs ?? [];
  const selectedRun = runs.find((row) => row.run.id === selectedRunId) ?? runs[0];
  const readyToProcess = runs.filter((row) => row.raw_file && !row.processing_job);
  const failedRows = runs.filter((row) => row.processing_job?.status === "failed" || row.run.status === "failed");

  const importMutation = useMutation({
    mutationFn: () => importProjectWorklist(projectId, { worklist_name: worklistName, rows: worklistRows }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projectResearcherStatus(projectId) });
      setWorklistOpen(false);
      setWorklistRows([]);
      setWorklistError("");
    },
    onError: (error) => setWorklistError(error instanceof Error ? error.message : "Could not import worklist."),
  });
  const queueMutation = useMutation({
    mutationFn: () => queueProjectReadyRuns(projectId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projectResearcherStatus(projectId) });
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
      await queryClient.invalidateQueries({ queryKey: queryKeys.projectResearcherStatus(projectId) });
      setEditDraft(null);
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

  return (
    <div className="grid gap-4">
      <Breadcrumbs
        items={[
          { label: "Projects", href: "/projects" },
          { label: project?.code ?? "Project" },
        ]}
      />

      <PageHero
        eyebrow="Researcher project"
        title={project?.code ?? "Loading project"}
        description={project?.title ?? "Retrieving project status."}
        actions={
          <>
            {project ? <StatusBadge status={project.status} /> : null}
            <span className={`inline-flex h-9 items-center rounded-md border px-3 text-sm font-bold ${healthClass}`}>{healthLabel}</span>
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
                  <DialogDescription>Upload a CSV or TSV worklist to create or update the project run ground truth.</DialogDescription>
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
                    <Button type="submit" disabled={importMutation.isPending || !worklistRows.length}>
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
        <MetricCard label="Project Status" value={project?.status ?? "-"} detail="research workflow" />
        <MetricCard label="Runs" value={data?.summary.run_count ?? "-"} detail="planned/acquired" />
        <MetricCard label="Raw Files" value={data?.summary.raw_file_count ?? "-"} detail={`${data?.summary.missing_raw_file_count ?? 0} missing`} />
        <MetricCard label="Queue" value={data?.system_health.active_jobs ?? "-"} detail="active jobs" />
        <MetricCard label="Failed" value={failedRows.length} detail="runs needing review" />
        <MetricCard label="Ready" value={readyToProcess.length} detail="uploaded, not queued" />
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Runs</CardTitle>
              <CardDescription>Each row is a planned LC-MS injection with raw-file, queue, and result status.</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" disabled={!readyToProcess.length || queueMutation.isPending} onClick={() => queueMutation.mutate()}>
                <CheckCircle2 className="h-4 w-4" />
                {queueMutation.isPending ? "Queueing..." : "Queue ready runs"}
              </Button>
              <Button asChild variant="secondary">
                <Link to={`/uploads?project=${projectId}`}>
                  <HardDrive className="h-4 w-4" />
                  Upload files
                </Link>
              </Button>
              <Button asChild variant="secondary">
                <Link to={`/qc?project=${projectId}`}>
                  <BarChart3 className="h-4 w-4" />
                  QC
                </Link>
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full min-w-[1120px] text-sm">
              <thead className="bg-secondary/65 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                <tr>
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
                    <td className="px-3 py-3 font-mono">{row.run.worklist_position ?? "-"}</td>
                    <td className="px-3 py-3">
                      <div className="font-semibold">{row.run.run_name}</div>
                      <div className="max-w-[220px] truncate text-xs text-muted-foreground">{row.run.expected_filename || "No expected filename"}</div>
                    </td>
                    <td className="px-3 py-3">{row.sample.name}</td>
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

      {selectedRun ? <RunDetail projectId={projectId} row={selectedRun} onEdit={() => startEdit(selectedRun)} /> : null}

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

function RunDetail({ projectId, row, onEdit }: { projectId: number; row: ProjectResearcherRun; onEdit: () => void }) {
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
              <Link className="font-medium text-primary" to={`/uploads?project=${projectId}&run=${row.run.id}`}>
                Upload for this run
              </Link>
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
    const roleValue = value(["file_role", "role", "type"]).toLowerCase();
    const fileRole = roleOptions.includes(roleValue as WorklistImportRow["file_role"]) ? roleValue as WorklistImportRow["file_role"] : "sample";
    return {
      position: Number.isFinite(positionValue) && positionValue > 0 ? positionValue : index + 1,
      sample_name: sampleName,
      run_name: value(["run_name", "run", "injection_name"]) || sampleName,
      expected_filename: expectedFilename,
      file_role: fileRole,
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
