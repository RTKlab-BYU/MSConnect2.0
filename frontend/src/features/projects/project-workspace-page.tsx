import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

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
  fetchRuns,
  fetchSamples,
  queryKeys,
} from "@/lib/api/queries";
import {
  acquisitionColumns,
  processingJobColumns,
  rawFileColumns,
  runColumns,
  sampleColumns,
} from "@/features/projects/table-columns";

function MetricCard({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-bold uppercase text-muted-foreground">{label}</div>
        <div className="mt-2 text-2xl font-bold">{value}</div>
        <div className="mt-1 text-sm text-muted-foreground">{detail}</div>
      </CardContent>
    </Card>
  );
}

export default function ProjectWorkspacePage() {
  const projectId = Number(useParams().projectId);
  const [rawSearch, setRawSearch] = useState("");
  const [rawStatus, setRawStatus] = useState("all");
  const [jobStatus, setJobStatus] = useState("all");
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

  const project = projectQuery.data;
  const summary = summaryQuery.data;

  return (
    <div className="grid gap-4">
      <Breadcrumbs
        items={[
          { label: "Projects", href: "/projects" },
          { label: project?.code ?? "Project" },
        ]}
      />

      <section className="rounded-lg border bg-card p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase text-muted-foreground">Project workspace</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight">{project?.code ?? "Loading project"}</h1>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{project?.title ?? "Retrieving project metadata."}</p>
          </div>
          <div className="flex items-center gap-2">
            {project ? <StatusBadge status={project.status} /> : null}
            <Button asChild variant="secondary" size="sm">
              <Link to={`/qc?project=${projectId}`}>View QC</Link>
            </Button>
            <Button asChild variant="secondary" size="sm">
              <Link to={`/processing?project=${projectId}`}>View Processing</Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Raw Files" value={summary?.raw_file_count ?? "-"} detail="matched files" />
        <MetricCard label="Processing Jobs" value={summary?.processing_job_count ?? "-"} detail="DIA / quant jobs" />
        <MetricCard label="Samples" value={summary?.sample_count ?? "-"} detail="registered samples" />
        <MetricCard label="Runs" value={summary?.run_count ?? "-"} detail="planned/acquired" />
        <MetricCard label="Missing Raw" value={summary?.missing_raw_file_count ?? "-"} detail="worklist gaps" />
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

      <Tabs defaultValue="raw-files">
        <TabsList>
          <TabsTrigger value="raw-files">Raw Files</TabsTrigger>
          <TabsTrigger value="jobs">Processing Jobs</TabsTrigger>
          <TabsTrigger value="analysis">Analysis Viz</TabsTrigger>
          <TabsTrigger value="samples">Samples</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
          <TabsTrigger value="acquisitions">Acquisitions</TabsTrigger>
        </TabsList>

        <TabsContent value="raw-files">
          <Card className="mb-3">
            <CardHeader>
              <CardTitle>Raw Files</CardTitle>
              <CardDescription>Highest-growth SDMS table. Uses server search, status filters, opt-in pagination, and virtualized rows.</CardDescription>
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
              <CardTitle>Processing Jobs</CardTitle>
              <CardDescription>
                Long-running work is modeled as queued, assigned, running, complete, failed, or retrying.
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
                <CardTitle>Linked Selection Contract</CardTitle>
                <CardDescription>
                  Retention-time selection is stored in a shared Zustand visualization store. Spectrum, UMAP, heatmap,
                  and metadata panels can subscribe without prop drilling when real endpoints are available.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="samples">
          <DataTable
            columns={sampleColumns}
            data={samplesQuery.data?.results ?? []}
            emptyLabel={samplesQuery.isLoading ? "Loading samples..." : "No samples found."}
          />
        </TabsContent>

        <TabsContent value="runs">
          <DataTable
            columns={runColumns}
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
