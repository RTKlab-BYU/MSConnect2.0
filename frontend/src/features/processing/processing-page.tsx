import type { ColumnDef } from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { SummaryChart } from "@/components/data/summary-chart";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  fetchProcessingJobs,
  fetchProcessingJobsOverview,
  fetchProcessingNodes,
  fetchProcessingNodesOverview,
  fetchProcessingPipelines,
  fetchProjects,
  queryKeys,
} from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import type { ProcessingJob, ProcessingNode } from "@/lib/api/types";

export default function ProcessingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const project = searchParams.get("project") ?? "all";
  const node = searchParams.get("node") ?? "all";
  const pipeline = searchParams.get("pipeline") ?? "all";
  const status = searchParams.get("status") ?? "all";
  const activeOnly = searchParams.get("active") === "true";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all" || value === "false") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  }

  const filterParams = {
    project: project === "all" ? "" : project,
    node: node === "all" ? "" : node,
    pipeline: pipeline === "all" ? "" : pipeline,
    status: status === "all" ? "" : status,
    active: activeOnly ? true : "",
  };
  const nodeLoadParams = {
    project: filterParams.project,
    pipeline: filterParams.pipeline,
    node: filterParams.node,
    active: true,
  };

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects({ page_size: 200 }),
    queryFn: () => fetchProjects({ page_size: 200 }),
  });
  const pipelinesQuery = useQuery({
    queryKey: queryKeys.processingPipelines({ page_size: 200 }),
    queryFn: () => fetchProcessingPipelines({ page_size: 200 }),
  });
  const nodesQuery = useQuery({
    queryKey: queryKeys.processingNodes({ page_size: 200 }),
    queryFn: () => fetchProcessingNodes({ page_size: 200 }),
  });
  const jobsOverviewQuery = useQuery({
    queryKey: queryKeys.processingJobsOverview(filterParams),
    queryFn: () => fetchProcessingJobsOverview(filterParams),
    refetchInterval: 20_000,
  });
  const nodeLoadQuery = useQuery({
    queryKey: queryKeys.processingJobsOverview(nodeLoadParams),
    queryFn: () => fetchProcessingJobsOverview(nodeLoadParams),
    refetchInterval: 20_000,
  });
  const nodesOverviewQuery = useQuery({
    queryKey: queryKeys.processingNodesOverview(),
    queryFn: () => fetchProcessingNodesOverview(),
    refetchInterval: 20_000,
  });
  const jobsQuery = useQuery({
    queryKey: queryKeys.processingJobs({ ...filterParams, page: 1, page_size: 200 }),
    queryFn: () => fetchProcessingJobs({ ...filterParams, page: 1, page_size: 200 }),
    refetchInterval: 20_000,
  });

  const activeJobsByNode = new Map((nodeLoadQuery.data?.by_node ?? []).map((row) => [row.node_id, row.count]));
  const jobs = jobsQuery.data?.results ?? [];
  const attentionJobs = jobs.filter((job) => job.status === "failed" || job.status === "retrying");
  const visibleNodes = (nodesQuery.data?.results ?? []).filter((item) => node === "all" || String(item.id) === node);

  const nodeColumns: ColumnDef<ProcessingNode>[] = [
    { accessorKey: "name", header: "Node" },
    { accessorKey: "node_type", header: "Type" },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    {
      accessorKey: "id",
      header: "Active Jobs",
      cell: ({ row }) => activeJobsByNode.get(row.original.id) ?? 0,
    },
    {
      accessorKey: "last_heartbeat_at",
      header: "Heartbeat",
      cell: ({ row }) => formatDate(row.original.last_heartbeat_at),
    },
    { accessorKey: "endpoint_url", header: "Endpoint" },
  ];

  const jobColumns: ColumnDef<ProcessingJob>[] = [
    { accessorKey: "id", header: "Job" },
    {
      accessorKey: "project_code",
      header: "Project",
      cell: ({ row }) => <Link className="font-semibold" to={`/projects/${row.original.project_id}`}>{row.original.project_code}</Link>,
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    { accessorKey: "run_name", header: "Run" },
    { accessorKey: "raw_file_filename", header: "Raw File" },
    {
      accessorKey: "pipeline_name",
      header: "Pipeline",
      cell: ({ row }) => `${row.original.pipeline_name} ${row.original.pipeline_version}`,
    },
    { accessorKey: "node_name", header: "Node" },
    {
      accessorKey: "started_at",
      header: "Started",
      cell: ({ row }) => formatDate(row.original.started_at),
    },
    {
      accessorKey: "error_message",
      header: "Error",
      cell: ({ row }) => row.original.error_message || "-",
    },
  ];

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Processing" }]} />

      <PageHero
        eyebrow="Distributed execution"
        title="Processing"
        description="Track node assignment, queue pressure, retries, and run-level processing work from a focused control surface."
        actions={
          <>
            <StatusBadge status="assigned" />
            <StatusBadge status="running" />
            <StatusBadge status="retrying" />
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Queue filters</CardTitle>
          <CardDescription>Scope the queue by project, node, pipeline, and job state.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <Select value={project} onValueChange={(value) => updateParam("project", value)}>
              <SelectTrigger>
                <SelectValue placeholder="Project" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All projects</SelectItem>
                {(projectsQuery.data?.results ?? []).map((item) => (
                  <SelectItem key={item.id} value={String(item.id)}>
                    {item.code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={node} onValueChange={(value) => updateParam("node", value)}>
              <SelectTrigger>
                <SelectValue placeholder="Node" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All nodes</SelectItem>
                {(nodesQuery.data?.results ?? []).map((item) => (
                  <SelectItem key={item.id} value={String(item.id)}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={pipeline} onValueChange={(value) => updateParam("pipeline", value)}>
              <SelectTrigger>
                <SelectValue placeholder="Pipeline" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All pipelines</SelectItem>
                {(pipelinesQuery.data?.results ?? []).map((item) => (
                  <SelectItem key={item.id} value={String(item.id)}>
                    {item.name} {item.version}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={(value) => updateParam("status", value)}>
              <SelectTrigger>
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
            <Select value={activeOnly ? "true" : "false"} onValueChange={(value) => updateParam("active", value)}>
              <SelectTrigger>
                <SelectValue placeholder="View" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="false">All jobs</SelectItem>
                <SelectItem value="true">Active only</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Active Jobs" value={jobsOverviewQuery.data?.active ?? "-"} detail="queued, assigned, running, retrying" />
        <MetricCard
          label="Queued"
          value={jobsOverviewQuery.data?.by_status.find((row) => row.status === "queued")?.count ?? 0}
          detail="waiting for node pickup"
        />
        <MetricCard
          label="Retrying"
          value={jobsOverviewQuery.data?.by_status.find((row) => row.status === "retrying")?.count ?? 0}
          detail="needs capacity or review"
        />
        <MetricCard label="Failed" value={jobsOverviewQuery.data?.failed ?? "-"} detail="attention required" />
        <MetricCard label="Nodes" value={nodesOverviewQuery.data?.total ?? "-"} detail="registered workers" />
        <MetricCard
          label="Node Errors"
          value={nodesOverviewQuery.data?.by_status.find((row) => row.status === "error")?.count ?? 0}
          detail="reported unhealthy"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <SummaryChart
          title="Jobs by Status"
          data={(jobsOverviewQuery.data?.by_status ?? []).map((row) => ({ label: row.status, count: row.count }))}
        />
        <SummaryChart
          title="Active Jobs by Node"
          data={(nodeLoadQuery.data?.by_node ?? []).map((row) => ({ label: row.node__name ?? "Unassigned", count: row.count }))}
        />
        <SummaryChart
          title="Nodes by Status"
          data={(nodesOverviewQuery.data?.by_status ?? []).map((row) => ({ label: row.status, count: row.count }))}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Processing Nodes</CardTitle>
          <CardDescription>Current node inventory with heartbeat and active job counts.</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={nodeColumns}
            data={visibleNodes}
            emptyLabel={nodesQuery.isLoading ? "Loading processing nodes..." : "No processing nodes found."}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Processing Jobs</CardTitle>
          <CardDescription>Global job queue with direct links back into project workspaces.</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={jobColumns}
            data={jobs}
            emptyLabel={jobsQuery.isLoading ? "Loading processing jobs..." : "No processing jobs found."}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Attention Queue</CardTitle>
          <CardDescription>Failed and retrying jobs visible in the current filter scope.</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable columns={jobColumns} data={attentionJobs} emptyLabel="No failed or retrying jobs in scope." />
        </CardContent>
      </Card>
    </div>
  );
}
