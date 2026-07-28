import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, FlaskConical, HardDrive, Loader2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchProjectResearcherStatus, queryKeys } from "@/lib/api/queries";
import type { ProjectResearcherRun } from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/format";

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

  const data = statusQuery.data;
  const sampleRows = (data?.runs ?? []).filter((row) => row.sample.id === sampleId);
  const sample = sampleRows[0]?.sample;
  const projectRows = data?.runs ?? [];
  const totals = sumStats(sampleRows);
  const projectTotals = sumStats(projectRows);
  const rawFileCount = sampleRows.reduce((sum, row) => sum + row.raw_file_count, 0);
  const jobCount = sampleRows.reduce((sum, row) => sum + row.processing_job_count, 0);
  const failedCount = sampleRows.filter((row) => row.run.status === "failed" || row.processing_job?.status === "failed").length;

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
            <Button asChild>
              <Link to={`/qc?project=${projectId}`}>
                <BarChart3 className="h-4 w-4" />
                QC
              </Link>
            </Button>
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
                <span className="break-all">Storage: {row.raw_file?.storage_path ?? "-"}</span>
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
