import type { ColumnDef } from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Eye, FileArchive, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { SummaryChart } from "@/components/data/summary-chart";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChromatogramPanel } from "@/features/visualization/chromatogram-panel";
import { VizPlanningPanel } from "@/features/visualization/viz-planning-panel";
import {
  fetchAcquisitions,
  fetchProcessingJobs,
  fetchProject,
  fetchProjectSummary,
  fetchRawFiles,
  fetchRunSummary,
  fetchRuns,
  fetchSamples,
  queryKeys,
} from "@/lib/api/queries";
import { formatBytes, formatDate } from "@/lib/format";
import type { ProcessingJobArtifact, RawFileDerivative, Run, Sample } from "@/lib/api/types";
import {
  acquisitionColumns,
  processingJobColumns,
  rawFileColumns,
  runColumns,
  sampleColumns,
} from "@/features/projects/table-columns";

export default function ProjectWorkspacePage() {
  const projectId = Number(useParams().projectId);
  const [activeTab, setActiveTab] = useState("raw-files");
  const [rawSearch, setRawSearch] = useState("");
  const [rawStatus, setRawStatus] = useState("all");
  const [jobStatus, setJobStatus] = useState("all");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const commonParams = useMemo(() => ({ project: projectId, page: 1, page_size: 100 }), [projectId]);
  const rawParams = useMemo(
    () => ({
      ...commonParams,
      search: rawSearch,
      status: rawStatus === "all" ? "" : rawStatus,
    }),
    [commonParams, rawSearch, rawStatus],
  );
  const jobParams = useMemo(
    () => ({
      ...commonParams,
      status: jobStatus === "all" ? "" : jobStatus,
    }),
    [commonParams, jobStatus],
  );

  const projectQuery = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => fetchProject(projectId),
    enabled: Number.isFinite(projectId),
  });
  const summaryQuery = useQuery({
    queryKey: queryKeys.projectSummary(projectId),
    queryFn: () => fetchProjectSummary(projectId),
    enabled: Number.isFinite(projectId),
    refetchInterval: 60_000,
  });
  const rawFilesQuery = useQuery({
    queryKey: queryKeys.rawFiles(rawParams),
    queryFn: () => fetchRawFiles(rawParams),
    enabled: Number.isFinite(projectId),
    refetchInterval: 45_000,
  });
  const jobsQuery = useQuery({
    queryKey: queryKeys.processingJobs(jobParams),
    queryFn: () => fetchProcessingJobs(jobParams),
    enabled: Number.isFinite(projectId),
    refetchInterval: 30_000,
  });
  const samplesQuery = useQuery({
    queryKey: queryKeys.samples(commonParams),
    queryFn: () => fetchSamples(commonParams),
    enabled: Number.isFinite(projectId),
  });
  const runsQuery = useQuery({
    queryKey: queryKeys.runs(commonParams),
    queryFn: () => fetchRuns(commonParams),
    enabled: Number.isFinite(projectId),
  });
  const acquisitionsQuery = useQuery({
    queryKey: queryKeys.acquisitions(commonParams),
    queryFn: () => fetchAcquisitions(commonParams),
    enabled: Number.isFinite(projectId),
  });
  const runSummaryQuery = useQuery({
    queryKey: queryKeys.runSummary(selectedRunId ?? 0),
    queryFn: () => fetchRunSummary(selectedRunId ?? 0),
    enabled: Boolean(selectedRunId),
    refetchInterval: 45_000,
  });

  const project = projectQuery.data;
  const summary = summaryQuery.data;
  const runs = runsQuery.data?.results ?? [];
  const selectedRunSummary = runSummaryQuery.data;
  const selectedRunRawFile = selectedRunSummary?.raw_files[0];

  useEffect(() => {
    if (!selectedRunId && runs.length) {
      setSelectedRunId(runs[0].id);
    }
  }, [runs, selectedRunId]);

  const inspectRun = (runId: number) => {
    setSelectedRunId(runId);
    setActiveTab("run-detail");
  };

  const sampleInspectColumns = useMemo<ColumnDef<Sample>[]>(
    () => [
      ...sampleColumns,
      {
        id: "inspect",
        header: "Inspect",
        cell: ({ row }) => {
          const run = runs.find((item) => item.sample === row.original.id);
          return (
            <Button size="sm" variant="secondary" disabled={!run} onClick={() => run && inspectRun(run.id)}>
              <Eye className="h-3.5 w-3.5" />
              Run
            </Button>
          );
        },
      },
    ],
    [runs],
  );

  const runInspectColumns = useMemo<ColumnDef<Run>[]>(
    () => [
      ...runColumns,
      {
        id: "inspect",
        header: "Inspect",
        cell: ({ row }) => (
          <Button size="sm" variant="secondary" onClick={() => inspectRun(row.original.id)}>
            <Eye className="h-3.5 w-3.5" />
            Details
          </Button>
        ),
      },
    ],
    [],
  );

  const derivativeColumns = useMemo<ColumnDef<RawFileDerivative>[]>(
    () => [
      { accessorKey: "derivative_type", header: "Type" },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      { accessorKey: "format", header: "Format" },
      {
        accessorKey: "size_bytes",
        header: "Size",
        cell: ({ row }) => (row.original.size_bytes ? formatBytes(row.original.size_bytes) : "-"),
      },
      {
        accessorKey: "updated_at",
        header: "Updated",
        cell: ({ row }) => formatDate(row.original.updated_at),
      },
      { accessorKey: "path", header: "Path" },
    ],
    [],
  );

  const artifactColumns = useMemo<ColumnDef<ProcessingJobArtifact>[]>(
    () => [
      { accessorKey: "artifact_type", header: "Artifact" },
      { accessorKey: "format", header: "Format" },
      {
        accessorKey: "size_bytes",
        header: "Size",
        cell: ({ row }) => (row.original.size_bytes ? formatBytes(row.original.size_bytes) : "-"),
      },
      {
        accessorKey: "retained",
        header: "Retained",
        cell: ({ row }) => (row.original.retained ? "Yes" : "No"),
      },
      {
        accessorKey: "updated_at",
        header: "Updated",
        cell: ({ row }) => formatDate(row.original.updated_at),
      },
      { accessorKey: "path", header: "Path" },
    ],
    [],
  );

  return (
    <div className="grid gap-4">
      <Breadcrumbs
        items={[
          { label: "Projects", href: "/projects" },
          { label: project?.code ?? "Project" },
        ]}
      />

      <PageHero
        eyebrow="Project workspace"
        title={project?.code ?? "Loading project"}
        description={project?.title ?? "Retrieving project metadata."}
        actions={
          <>
            {project ? <StatusBadge status={project.status} /> : null}
            <Button asChild variant="secondary" size="sm">
              <Link to={`/qc?project=${projectId}`}>View QC</Link>
            </Button>
            <Button asChild variant="secondary" size="sm">
              <Link to={`/processing?project=${projectId}`}>View Processing</Link>
            </Button>
          </>
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Raw Files" value={summary?.raw_file_count ?? "-"} detail="matched files" />
        <MetricCard label="Processing Jobs" value={summary?.processing_job_count ?? "-"} detail="DIA / quant jobs" />
        <MetricCard label="Samples" value={summary?.sample_count ?? "-"} detail="registered samples" />
        <MetricCard label="Runs" value={summary?.run_count ?? "-"} detail="planned/acquired" />
        <MetricCard label="Missing Raw" value={summary?.missing_raw_file_count ?? "-"} detail="worklist gaps" />
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard
          label="Proteins"
          value={summary?.reported_protein_count || summary?.protein_quant_count || "-"}
          detail={`${summary?.protein_quant_count ?? 0} quant rows`}
        />
        <MetricCard
          label="Peptides"
          value={summary?.reported_peptide_count || summary?.peptide_quant_count || "-"}
          detail={`${summary?.peptide_quant_count ?? 0} quant rows`}
        />
        <MetricCard
          label="Precursors"
          value={summary?.reported_precursor_count || "-"}
          detail="reported by engine"
        />
        <MetricCard label="MS1" value={summary?.ms1_feature_count || summary?.indexed_ms1_spectra_count || "-"} detail="features / scans" />
        <MetricCard label="MS2" value={summary?.ms2_spectra_count || summary?.indexed_ms2_spectra_count || "-"} detail="spectra" />
        <MetricCard label="Outputs" value={summary?.artifact_count ?? "-"} detail={`${summary?.derivative_count ?? 0} derivatives`} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <SummaryChart
          title="Raw Files by Status"
          data={(summary?.raw_files_by_status ?? []).map((row) => ({ label: row.status, count: row.count }))}
        />
        <SummaryChart
          title="Processing Jobs by Status"
          data={(summary?.jobs_by_status ?? []).map((row) => ({ label: row.status, count: row.count }))}
        />
      </section>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="raw-files">Raw Files</TabsTrigger>
          <TabsTrigger value="jobs">Processing Jobs</TabsTrigger>
          <TabsTrigger value="analysis">Analysis Viz</TabsTrigger>
          <TabsTrigger value="run-detail">Run Detail</TabsTrigger>
          <TabsTrigger value="samples">Samples</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
          <TabsTrigger value="acquisitions">Acquisitions</TabsTrigger>
        </TabsList>

        <TabsContent value="raw-files">
          <Card className="mb-3">
            <CardHeader>
              <CardTitle>Raw files</CardTitle>
              <CardDescription>Search and filter matched raw files without leaving the project workspace.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-[1fr_220px]">
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    className="pl-9"
                    placeholder="Search filename, checksum, storage path..."
                    value={rawSearch}
                    onChange={(event) => setRawSearch(event.target.value)}
                  />
                </div>
                <Select value={rawStatus} onValueChange={setRawStatus}>
                  <SelectTrigger>
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="discovered">Discovered</SelectItem>
                    <SelectItem value="validated">Validated</SelectItem>
                    <SelectItem value="imported">Imported</SelectItem>
                    <SelectItem value="processed">Processed</SelectItem>
                    <SelectItem value="failed">Failed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
          <DataTable
            columns={rawFileColumns}
            data={rawFilesQuery.data?.results ?? []}
            emptyLabel={rawFilesQuery.isLoading ? "Loading raw files..." : "No raw files found."}
          />
        </TabsContent>

        <TabsContent value="jobs">
          <Card className="mb-3">
            <CardHeader>
              <CardTitle>Processing jobs</CardTitle>
              <CardDescription>
                Track queued, assigned, running, complete, failed, and retrying jobs.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Select value={jobStatus} onValueChange={setJobStatus}>
                <SelectTrigger className="max-w-[240px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="queued">Queued</SelectItem>
                  <SelectItem value="assigned">Assigned</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="complete">Complete</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                  <SelectItem value="retrying">Retrying</SelectItem>
                </SelectContent>
              </Select>
            </CardContent>
          </Card>
          <DataTable
            columns={processingJobColumns}
            data={jobsQuery.data?.results ?? []}
            emptyLabel={jobsQuery.isLoading ? "Loading processing jobs..." : "No processing jobs found."}
          />
        </TabsContent>

        <TabsContent value="analysis">
          <div className="grid gap-4">
            <ChromatogramPanel rawFile={rawFilesQuery.data?.results[0]} />
            <VizPlanningPanel />
            <Card>
              <CardHeader>
                <CardTitle>Linked analysis selection</CardTitle>
                <CardDescription>
                  Retention-time selection can drive future spectrum, UMAP, heatmap, and metadata panels.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="run-detail">
          <div className="grid gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Run detail</CardTitle>
                <CardDescription>Select a project run to inspect processing stats, retained outputs, and spectra context.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                  <Select value={selectedRunId ? String(selectedRunId) : ""} onValueChange={(value) => setSelectedRunId(Number(value))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Choose run" />
                    </SelectTrigger>
                    <SelectContent>
                      {runs.map((run) => (
                        <SelectItem key={run.id} value={String(run.id)}>
                          {run.worklist_position ? `${run.worklist_position}. ` : ""}
                          {run.run_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button asChild variant="secondary" disabled={!selectedRunRawFile}>
                    <Link to={selectedRunRawFile ? `/spectra?rawFile=${selectedRunRawFile.id}` : "/spectra"}>
                      <Activity className="h-4 w-4" />
                      Spectra
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>

            <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
              <MetricCard label="Raw Files" value={selectedRunSummary?.stats.raw_file_count ?? "-"} detail={selectedRunRawFile?.filename ?? "selected run"} />
              <MetricCard label="Jobs" value={selectedRunSummary?.stats.processing_job_count ?? "-"} detail="processing attempts" />
              <MetricCard label="Proteins" value={selectedRunSummary?.stats.reported_protein_count || selectedRunSummary?.stats.protein_quant_count || "-"} detail="reported / imported" />
              <MetricCard label="Peptides" value={selectedRunSummary?.stats.reported_peptide_count || selectedRunSummary?.stats.peptide_quant_count || "-"} detail="reported / imported" />
              <MetricCard label="MS1" value={selectedRunSummary?.stats.ms1_feature_count || selectedRunSummary?.stats.indexed_ms1_spectra_count || "-"} detail="features / scans" />
              <MetricCard label="MS2" value={selectedRunSummary?.stats.ms2_spectra_count || selectedRunSummary?.stats.indexed_ms2_spectra_count || "-"} detail="spectra" />
            </section>

            <div className="grid gap-4 xl:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-4 w-4" />
                    Processing stats
                  </CardTitle>
                  <CardDescription>
                    {selectedRunSummary
                      ? `${selectedRunSummary.stats.indexed_spectra_count} indexed spectra, ${selectedRunSummary.stats.artifact_count} retained artifacts.`
                      : "Choose a run to load its processing summary."}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <dl className="grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-muted-foreground">Sample</dt>
                      <dd className="font-semibold">{selectedRunSummary?.sample.name ?? "-"}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Status</dt>
                      <dd>{selectedRunSummary ? <StatusBadge status={selectedRunSummary.run.status} /> : "-"}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Protein IDs</dt>
                      <dd className="font-semibold">{selectedRunSummary?.stats.protein_identification_count ?? "-"}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Peptide IDs</dt>
                      <dd className="font-semibold">{selectedRunSummary?.stats.peptide_identification_count ?? "-"}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Derivatives</dt>
                      <dd className="font-semibold">{selectedRunSummary?.stats.derivative_count ?? "-"}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Raw file</dt>
                      <dd className="truncate font-semibold">{selectedRunRawFile?.filename ?? "-"}</dd>
                    </div>
                  </dl>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileArchive className="h-4 w-4" />
                    Processing jobs
                  </CardTitle>
                  <CardDescription>Pipeline executions tied to the selected run.</CardDescription>
                </CardHeader>
                <CardContent>
                  <DataTable
                    columns={processingJobColumns}
                    data={selectedRunSummary?.processing_jobs ?? []}
                    emptyLabel={runSummaryQuery.isLoading ? "Loading jobs..." : "No jobs for this run."}
                  />
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Retained artifacts</CardTitle>
                <CardDescription>DIA-NN reports, imported tables, logs, and enterprise handoff outputs stay attached here.</CardDescription>
              </CardHeader>
              <CardContent>
                <DataTable
                  columns={artifactColumns}
                  data={selectedRunSummary?.artifacts ?? []}
                  emptyLabel={runSummaryQuery.isLoading ? "Loading artifacts..." : "No retained artifacts for this run."}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Spectra derivatives</CardTitle>
                <CardDescription>mzML, spectrum index, and preview derivatives available for the selected run.</CardDescription>
              </CardHeader>
              <CardContent>
                <DataTable
                  columns={derivativeColumns}
                  data={selectedRunSummary?.derivatives ?? []}
                  emptyLabel={runSummaryQuery.isLoading ? "Loading derivatives..." : "No spectra derivatives for this run."}
                />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="samples">
          <DataTable
            columns={sampleInspectColumns}
            data={samplesQuery.data?.results ?? []}
            emptyLabel={samplesQuery.isLoading ? "Loading samples..." : "No samples found."}
          />
        </TabsContent>

        <TabsContent value="runs">
          <DataTable
            columns={runInspectColumns}
            data={runsQuery.data?.results ?? []}
            emptyLabel={runsQuery.isLoading ? "Loading runs..." : "No runs found."}
          />
        </TabsContent>

        <TabsContent value="acquisitions">
          <DataTable
            columns={acquisitionColumns}
            data={acquisitionsQuery.data?.results ?? []}
            emptyLabel={acquisitionsQuery.isLoading ? "Loading acquisitions..." : "No acquisition worklists found."}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
