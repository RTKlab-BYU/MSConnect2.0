import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, ExternalLink, FlaskConical, HardDrive, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchCurrentUser, fetchProjectResearcherStatus, fetchRunSummary, queryKeys } from "@/lib/api/queries";
import type { ProjectResearcherRun, RunSummary } from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/format";
import { isOperatorRole } from "@/lib/ui-surface";

const numberFormat = new Intl.NumberFormat();

export default function SampleReportPage() {
  const projectId = Number(useParams().projectId);
  const sampleId = Number(useParams().sampleId);
  const statusQuery = useQuery({
    queryKey: queryKeys.projectResearcherStatus(projectId),
    queryFn: () => fetchProjectResearcherStatus(projectId),
    enabled: Number.isFinite(projectId),
    refetchInterval: 30_000,
  });
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const isOperator = isOperatorRole(currentUserQuery.data?.global_role);

  const data = statusQuery.data;
  const sampleRows = (data?.runs ?? []).filter((row) => row.sample.id === sampleId);
  const sample = sampleRows[0]?.sample;
  const runSummaryQueries = useQueries({
    queries: sampleRows.map((row) => ({
      queryKey: queryKeys.runSummary(row.run.id),
      queryFn: () => fetchRunSummary(row.run.id),
      enabled: Number.isFinite(row.run.id),
      refetchInterval: 30_000,
    })),
  });
  const sampleRuns = sampleRows.map((row, index) => ({
    row,
    summary: runSummaryQueries[index]?.data,
    isLoading: runSummaryQueries[index]?.isLoading ?? false,
    isError: runSummaryQueries[index]?.isError ?? false,
  }));
  const projectRows = data?.runs ?? [];
  const totals = sumStats(sampleRows);
  const projectTotals = sumStats(projectRows);
  const rawFileCount = sampleRows.reduce((sum, row) => sum + row.raw_file_count, 0);
  const jobCount = sampleRows.reduce((sum, row) => sum + row.processing_job_count, 0);
  const failedCount = sampleRows.filter((row) => row.run.status === "failed" || row.processing_job?.status === "failed").length;
  const allArtifacts = sampleRuns.flatMap((item) => item.summary?.artifacts ?? []);
  const allRawFiles = sampleRuns.flatMap((item) => item.summary?.raw_files ?? (item.row.raw_file ? [item.row.raw_file] : []));
  const allDerivatives = sampleRuns.flatMap((item) => item.summary?.derivatives ?? []);

  if (statusQuery.isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading sample report
      </div>
    );
  }

  if (!sample || !data) {
    return (
      <div className="grid gap-4">
        <Breadcrumbs items={[{ label: "Projects", href: "/projects" }, { label: "Sample" }]} />
        <Card>
          <CardContent className="p-6">
            <div className="text-sm text-muted-foreground">This sample is not part of the selected project.</div>
            <Button asChild className="mt-4" variant="secondary">
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Back to project
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <Breadcrumbs
        items={[
          { label: "Projects", href: "/projects" },
          { label: data.project.code, href: `/projects/${projectId}` },
          { label: sample.name },
        ]}
      />

      <PageHero
        eyebrow="Sample report"
        title={sample.name}
        description={`${data.project.code} · ${sample.external_id || "No external ID"} · ${sample.species || "Species not set"} · ${sample.matrix || "Matrix not set"}`}
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            {isOperator ? (
              <Button asChild>
                <Link to={`/qc?project=${projectId}`}>
                  <BarChart3 className="h-4 w-4" />
                  QC
                </Link>
              </Button>
            ) : null}
          </>
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Runs" value={sampleRows.length} detail="for this sample" />
        <MetricCard label="Raw Files" value={rawFileCount} detail="matched inputs" />
        <MetricCard label="Jobs" value={jobCount} detail="processing attempts" />
        <MetricCard label="Failed" value={failedCount} detail="runs needing review" />
        <MetricCard label="Proteins" value={metric(totals.reported_protein_count || totals.protein_quant_count)} detail="reported or quantified" />
        <MetricCard label="Peptides" value={metric(totals.reported_peptide_count || totals.peptide_quant_count)} detail="reported or quantified" />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>DIA-NN Outputs</CardTitle>
          <CardDescription>Report files and supporting outputs for each run. This is the quickest place to find the actual DIA-NN artifacts.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {sampleRuns.map((item) => {
            const job = item.row.processing_job;
            return (
              <div key={item.row.run.id} className="rounded-lg border bg-background/50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-bold">{item.row.run.run_name}</div>
                    <div className="text-xs text-muted-foreground">{item.row.raw_file?.filename ?? "No raw file attached"}</div>
                  </div>
                  <StatusBadge status={job?.status ?? item.row.run.status} />
                </div>
                <div className="mt-3 grid gap-2 text-sm">
                  <ResultLine label="DIA-NN report" value={fileLink(diannReportPath(item) ?? "-")} />
                  <ResultLine label="Protein table" value={fileLink(resultFilePath(job, "protein_table") ?? "-")} />
                  <ResultLine label="Peptide table" value={fileLink(resultFilePath(job, "peptide_table") ?? "-")} />
                  <ResultLine label="Speclib" value={fileLink(diannSpeclibPath(item) ?? "-")} />
                  <ResultLine label="Log" value={fileLink(job?.log_path ?? "-")} />
                  <ResultLine label="Runtime manifest" value={fileLink(runtimeManifestPath(job) ?? "-")} />
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Sample Metadata</CardTitle>
            <CardDescription>Metadata exported from the MSConnect sample record.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 text-sm">
              <MetadataRow label="Sample ID" value={sample.id} />
              <MetadataRow label="External ID" value={sample.external_id || "-"} />
              <MetadataRow label="Species" value={sample.species || "-"} />
              <MetadataRow label="Matrix" value={sample.matrix || "-"} />
              <MetadataRow label="Digestion" value={sample.digestion_protocol || "-"} />
              <MetadataRow label="Enrichment" value={sample.enrichment_protocol || "-"} />
            </div>
            <div className="mt-4 rounded-lg border bg-background/50 p-3">
              <div className="text-xs font-black uppercase text-muted-foreground">Metadata JSON</div>
              <pre className="mt-2 max-h-64 overflow-auto text-xs"><code>{JSON.stringify(sample.metadata, null, 2)}</code></pre>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Project-Relative Stats</CardTitle>
            <CardDescription>Sample totals compared with all runs in the project.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <RelativeStat label="Reported proteins" value={totals.reported_protein_count} projectValue={projectTotals.reported_protein_count} />
            <RelativeStat label="Reported peptides" value={totals.reported_peptide_count} projectValue={projectTotals.reported_peptide_count} />
            <RelativeStat label="Reported precursors" value={totals.reported_precursor_count} projectValue={projectTotals.reported_precursor_count} />
            <RelativeStat label="MS1 features" value={totals.ms1_feature_count || totals.indexed_ms1_spectra_count} projectValue={projectTotals.ms1_feature_count || projectTotals.indexed_ms1_spectra_count} />
            <RelativeStat label="MS2 spectra" value={totals.ms2_spectra_count || totals.indexed_ms2_spectra_count} projectValue={projectTotals.ms2_spectra_count || projectTotals.indexed_ms2_spectra_count} />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Related Runs</CardTitle>
          <CardDescription>All injections, raw files, jobs, and result counts tied to this sample.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full min-w-[980px] text-sm">
              <thead className="bg-secondary/65 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                <tr>
                  <th className="px-3 py-3">Order</th>
                  <th className="px-3 py-3">Run</th>
                  <th className="px-3 py-3">Role</th>
                  <th className="px-3 py-3">Raw file</th>
                  <th className="px-3 py-3">Processing</th>
                  <th className="px-3 py-3">Proteins</th>
                  <th className="px-3 py-3">Peptides</th>
                  <th className="px-3 py-3">MS1</th>
                  <th className="px-3 py-3">MS2</th>
                  <th className="px-3 py-3">Updated</th>
                </tr>
              </thead>
              <tbody>
                {sampleRows.map((row) => (
                  <tr key={row.run.id} className="border-t">
                    <td className="px-3 py-3 font-mono">{row.run.worklist_position ?? "-"}</td>
                    <td className="px-3 py-3">
                      <div className="font-semibold">{row.run.run_name}</div>
                      <div className="max-w-[240px] truncate text-xs text-muted-foreground">{row.run.expected_filename || "No expected filename"}</div>
                    </td>
                    <td className="px-3 py-3"><StatusBadge status={row.run.file_role} /></td>
                    <td className="px-3 py-3">
                      {row.raw_file ? (
                        <div>
                          <div className="font-semibold">{row.raw_file.filename}</div>
                          <div className="text-xs text-muted-foreground">{formatBytes(row.raw_file.size_bytes)}</div>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">Missing</span>
                      )}
                    </td>
                    <td className="px-3 py-3">{row.processing_job ? <StatusBadge status={row.processing_job.status} /> : <span className="text-muted-foreground">Not queued</span>}</td>
                    <td className="px-3 py-3">{metric(row.stats.reported_protein_count || row.stats.protein_quant_count)}</td>
                    <td className="px-3 py-3">{metric(row.stats.reported_peptide_count || row.stats.peptide_quant_count)}</td>
                    <td className="px-3 py-3">{metric(row.stats.ms1_feature_count || row.stats.indexed_ms1_spectra_count)}</td>
                    <td className="px-3 py-3">{metric(row.stats.ms2_spectra_count || row.stats.indexed_ms2_spectra_count)}</td>
                    <td className="px-3 py-3">{formatDate(row.run.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Run Results</CardTitle>
            <CardDescription>Result files and artifacts written by the processor for each run.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {sampleRuns.map((item) => (
              <div key={item.row.run.id} className="rounded-lg border bg-background/50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-bold">{item.row.run.run_name}</div>
                    <div className="text-xs text-muted-foreground">{item.row.raw_file?.filename ?? "No raw file attached"}</div>
                  </div>
                  <StatusBadge status={item.row.processing_job?.status ?? item.row.run.status} />
                </div>

                {item.isLoading ? (
                  <div className="mt-3 text-sm text-muted-foreground">Loading result files...</div>
                ) : item.isError ? (
                  <div className="mt-3 text-sm text-muted-foreground">Run summary unavailable.</div>
                ) : (
                  <div className="mt-3 grid gap-3">
                    <div className="grid gap-2 text-sm">
                      <ResultLine label="Report" value={fileLink(artifactPath(item.summary, "diann_report") ?? "-")} />
                      <ResultLine label="Speclib" value={fileLink(artifactPath(item.summary, "other", "diann_speclib") ?? "-")} />
                      <ResultLine label="Log" value={fileLink(artifactPath(item.summary, "log") ?? item.row.processing_job?.log_path ?? "-")} />
                      <ResultLine label="Runtime manifest" value={fileLink(artifactPath(item.summary, "other", "runtime_manifest") ?? "-")} />
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-black uppercase tracking-[0.16em] text-muted-foreground">Artifacts</div>
                      <div className="grid gap-2">
                        {(item.summary?.artifacts ?? []).map((artifact) => (
                          <div key={artifact.id} className="rounded-md border bg-background p-2 text-xs">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="neutral">{artifact.artifact_type}</Badge>
                              {artifact.format ? <Badge variant="info">{artifact.format}</Badge> : null}
                              {artifact.retained ? <Badge variant="success">Retained</Badge> : <Badge variant="warning">Dropped</Badge>}
                            </div>
                            <div className="mt-1">{fileLink(artifact.path, "break-all font-mono text-[11px] text-muted-foreground")}</div>
                          </div>
                        ))}
                        {!item.summary?.artifacts?.length ? (
                          <div className="text-sm text-muted-foreground">No artifact records yet.</div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Files</CardTitle>
            <CardDescription>Raw inputs and derivative files attached to the sample.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div>
              <div className="mb-2 text-xs font-black uppercase tracking-[0.16em] text-muted-foreground">Raw inputs</div>
              <div className="grid gap-2">
                {allRawFiles.map((rawFile) => (
                  <div key={rawFile.id} className="rounded-md border bg-background p-2 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-semibold">{rawFile.filename}</div>
                      <StatusBadge status={rawFile.status} />
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      <div>{formatBytes(rawFile.size_bytes)}</div>
                      {fileLink(rawFile.storage_path, "break-all")}
                    </div>
                  </div>
                ))}
                {!allRawFiles.length ? <div className="text-sm text-muted-foreground">No raw files found.</div> : null}
              </div>
            </div>

            <div>
              <div className="mb-2 text-xs font-black uppercase tracking-[0.16em] text-muted-foreground">Derivatives</div>
              <div className="grid gap-2">
                {allDerivatives.map((derivative) => (
                  <div key={derivative.id} className="rounded-md border bg-background p-2 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="neutral">{derivative.derivative_type}</Badge>
                      <StatusBadge status={derivative.status} />
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {fileLink(derivative.path, "break-all")}
                      <div>{derivative.format || "Unknown format"}</div>
                    </div>
                  </div>
                ))}
                {!allDerivatives.length ? <div className="text-sm text-muted-foreground">No derivatives found.</div> : null}
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Combined Artifacts</CardTitle>
          <CardDescription>All sample-level artifacts collected from the latest run summaries.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="bg-secondary/65 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                <tr>
                  <th className="px-3 py-3">Run</th>
                  <th className="px-3 py-3">Artifact</th>
                  <th className="px-3 py-3">Format</th>
                  <th className="px-3 py-3">Path</th>
                </tr>
              </thead>
              <tbody>
                {allArtifacts.map((artifact) => (
                  <tr key={artifact.id} className="border-t">
                    <td className="px-3 py-3">{artifact.run_name}</td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="neutral">{artifact.artifact_type}</Badge>
                        {artifact.retained ? <Badge variant="success">Retained</Badge> : <Badge variant="warning">Dropped</Badge>}
                      </div>
                    </td>
                    <td className="px-3 py-3">{artifact.format || "-"}</td>
                    <td className="px-3 py-3">{fileLink(artifact.path, "break-all font-mono text-xs")}</td>
                  </tr>
                ))}
                {!allArtifacts.length ? (
                  <tr>
                    <td className="px-3 py-4 text-muted-foreground" colSpan={4}>
                      No artifacts found for this sample yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Acquisition And File Context</CardTitle>
          <CardDescription>Paths and identifiers for downstream analysis handoff.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {sampleRows.map((row) => (
            <div key={row.run.id} className="rounded-lg border bg-background/50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 font-bold">
                  <FlaskConical className="h-4 w-4" />
                  {row.run.run_name}
                </div>
                <StatusBadge status={row.run.status} />
              </div>
              <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                <span>Expected: {row.run.expected_filename || "-"}</span>
                <span>Raw file: {row.raw_file?.filename ?? "missing"}</span>
                <span className="break-all">Storage: {fileLink(row.raw_file?.storage_path ?? "-")}</span>
              </div>
              {row.raw_file ? (
                <Button asChild className="mt-3" size="sm" variant="secondary">
                  <Link to={`/spectra?rawFile=${row.raw_file.id}`}>
                    <HardDrive className="h-3.5 w-3.5" />
                    Open spectra
                  </Link>
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function MetadataRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-semibold">{value}</span>
    </div>
  );
}

function ResultLine({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="max-w-[70%] text-right font-mono text-xs">{value}</span>
    </div>
  );
}

function fileLink(value: string, className = "") {
  const href = fileHref(value);
  if (!href) {
    return <span className={`break-all ${className}`.trim()}>{value}</span>;
  }

  return (
    <a
      className={`inline-flex items-center gap-1 break-all font-medium text-primary underline decoration-dotted underline-offset-4 hover:text-primary/80 ${className}`.trim()}
      href={href}
      rel="noreferrer"
      target="_blank"
      title={value}
    >
      <span>{value}</span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0" />
    </a>
  );
}

function fileHref(value: string) {
  if (!value || value === "-") return null;
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(value)) return value;
  if (/^[a-zA-Z]:[\\/]/.test(value)) return `file:///${value.replace(/\\/g, "/")}`;
  if (value.startsWith("/")) return `file://${value}`;
  return null;
}

function artifactPath(summary: RunSummary | undefined, artifactType: string, role?: string): string | null {
  const artifact = (summary?.artifacts ?? []).find((item) => {
    if (item.artifact_type !== artifactType) return false;
    if (!role) return true;
    return item.metadata && typeof item.metadata === "object" && (item.metadata as Record<string, unknown>).role === role;
  });
  return artifact?.path ?? null;
}

function diannReportPath(item: { summary?: RunSummary; row: ProjectResearcherRun }) {
  return artifactPath(item.summary, "diann_report");
}

function diannSpeclibPath(item: { summary?: RunSummary; row: ProjectResearcherRun }) {
  return artifactPath(item.summary, "other", "diann_speclib");
}

function resultFilePath(job: ProjectResearcherRun["processing_job"], key: "protein_table" | "peptide_table") {
  if (!job?.metadata || typeof job.metadata !== "object") return null;
  const resultFiles = (job.metadata as Record<string, unknown>).result_files;
  if (!resultFiles || typeof resultFiles !== "object") return null;
  const path = (resultFiles as Record<string, unknown>)[`${key}_path`];
  return typeof path === "string" && path.trim() ? path : null;
}

function runtimeManifestPath(job: ProjectResearcherRun["processing_job"]) {
  if (!job?.stats || typeof job.stats !== "object") return null;
  const runtime = (job.stats as Record<string, unknown>).runtime;
  if (!runtime || typeof runtime !== "object") return null;
  const path = (runtime as Record<string, unknown>).runtime_manifest_path;
  return typeof path === "string" && path.trim() ? path : null;
}

function RelativeStat({ label, value, projectValue }: { label: string; value: number; projectValue: number }) {
  const pct = projectValue > 0 ? Math.round((value / projectValue) * 100) : 0;
  return (
    <div className="grid gap-2 rounded-lg border bg-background/50 p-3">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-bold">{label}</span>
        <span className="text-muted-foreground">{metric(value)} / {metric(projectValue)}</span>
      </div>
      <div className="h-2 rounded-full bg-muted">
        <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <div className="text-xs text-muted-foreground">{pct}% of project total</div>
    </div>
  );
}

function sumStats(rows: ProjectResearcherRun[]) {
  return rows.reduce(
    (sum, row) => ({
      protein_quant_count: sum.protein_quant_count + row.stats.protein_quant_count,
      peptide_quant_count: sum.peptide_quant_count + row.stats.peptide_quant_count,
      reported_protein_count: sum.reported_protein_count + row.stats.reported_protein_count,
      reported_peptide_count: sum.reported_peptide_count + row.stats.reported_peptide_count,
      reported_precursor_count: sum.reported_precursor_count + row.stats.reported_precursor_count,
      ms1_feature_count: sum.ms1_feature_count + row.stats.ms1_feature_count,
      ms2_spectra_count: sum.ms2_spectra_count + row.stats.ms2_spectra_count,
      indexed_ms1_spectra_count: sum.indexed_ms1_spectra_count + row.stats.indexed_ms1_spectra_count,
      indexed_ms2_spectra_count: sum.indexed_ms2_spectra_count + row.stats.indexed_ms2_spectra_count,
    }),
    {
      protein_quant_count: 0,
      peptide_quant_count: 0,
      reported_protein_count: 0,
      reported_peptide_count: 0,
      reported_precursor_count: 0,
      ms1_feature_count: 0,
      ms2_spectra_count: 0,
      indexed_ms1_spectra_count: 0,
      indexed_ms2_spectra_count: 0,
    },
  );
}

function metric(value: number) {
  return value ? numberFormat.format(value) : "-";
}
