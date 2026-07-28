import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Database,
  ExternalLink,
  FileUp,
  FlaskConical,
  LineChart,
  Microscope,
  Server,
  Settings2,
  ShieldAlert,
  TerminalSquare,
} from "lucide-react";
import { Link } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  fetchAcquisitions,
  fetchProcessingJobsOverview,
  fetchProcessingNodes,
  fetchProcessingNodesOverview,
  fetchProcessingPipelines,
  fetchProjects,
  fetchRawFilesOverview,
  queryKeys,
} from "@/lib/api/queries";
import type { ProcessingNode } from "@/lib/api/types";
import { formatDate } from "@/lib/format";

const numberFormat = new Intl.NumberFormat();

const featureLinks = [
  {
    title: "Project Operations",
    description: "Portfolio, intake, project reports, sample pages, and selected-run queueing.",
    href: "/projects",
    icon: FlaskConical,
  },
  {
    title: "Processing Control",
    description: "Queue state, active jobs, node load, retry pressure, and attention jobs.",
    href: "/processing",
    icon: Activity,
  },
  {
    title: "Processor Admin",
    description: "Live processor hosts, IPs, engine health, storage roots, and admin controls.",
    href: "/processing/admin",
    icon: Server,
  },
  {
    title: "Monitoring",
    description: "Operational snapshots for queues, raw files, and node heartbeat trends.",
    href: "/monitoring",
    icon: LineChart,
  },
  {
    title: "QC Workspace",
    description: "HYE pairs, QC overview, chromatogram-backed checks, and exception review.",
    href: "/qc",
    icon: Microscope,
  },
  {
    title: "Uploads",
    description: "Direct upload sessions, raw-file storage registration, and file intake checks.",
    href: "/uploads",
    icon: FileUp,
  },
  {
    title: "Spectra",
    description: "Raw-file spectra, chromatograms, and run-level inspection surfaces.",
    href: "/spectra",
    icon: Database,
  },
  {
    title: "Settings",
    description: "Users, labs, instruments, pipelines, storage, agents, and security records.",
    href: "/settings",
    icon: Settings2,
  },
];

const processorBootProfiles = [
  {
    engine: "diann",
    host: "Linux or Windows worker",
    versionLabel: "DIA-NN install or container tag",
    command: [
      "MSCONNECT_PROCESSOR_ENGINE=diann \\",
      "MSCONNECT_AGENT_NAME=diann-01 \\",
      "MSCONNECT_AGENT_TOKEN=<processor-token> \\",
      "MSCONNECT_API_BASE_URL=http://msconnect-server:8000/api \\",
      "RAW_FILE_STORAGE_ROOT=/mnt/msconnect/raw \\",
      "RESULTS_ROOT=/mnt/msconnect/results \\",
      "PROCESSOR_SHARED_STORAGE_ROOT=/mnt/msconnect \\",
      ".venv/bin/python manage.py run_processor_agent --engine diann",
    ].join("\n"),
  },
  {
    engine: "fragpipe",
    host: "Linux or Windows worker",
    versionLabel: "FragPipe/MSFragger/Philosopher versions",
    command: [
      "MSCONNECT_PROCESSOR_ENGINE=fragpipe \\",
      "MSCONNECT_AGENT_NAME=fragpipe-01 \\",
      "MSCONNECT_AGENT_TOKEN=<processor-token> \\",
      "MSCONNECT_API_BASE_URL=http://msconnect-server:8000/api \\",
      "RAW_FILE_STORAGE_ROOT=/mnt/msconnect/raw \\",
      "RESULTS_ROOT=/mnt/msconnect/results \\",
      "PROCESSOR_SHARED_STORAGE_ROOT=/mnt/msconnect \\",
      ".venv/bin/python manage.py run_processor_agent --engine fragpipe",
    ].join("\n"),
  },
  {
    engine: "skyline",
    host: "Windows worker",
    versionLabel: "Skyline command-line install",
    command: [
      "$env:MSCONNECT_PROCESSOR_ENGINE='skyline'",
      "$env:MSCONNECT_AGENT_NAME='skyline-win-01'",
      "$env:MSCONNECT_AGENT_TOKEN='<processor-token>'",
      "$env:MSCONNECT_API_BASE_URL='http://msconnect-server:8000/api'",
      "$env:RAW_FILE_STORAGE_ROOT='\\\\nas\\msconnect\\raw'",
      "$env:RESULTS_ROOT='\\\\nas\\msconnect\\results'",
      "$env:PROCESSOR_SHARED_STORAGE_ROOT='\\\\nas\\msconnect'",
      ".\\.venv\\Scripts\\python manage.py run_processor_agent --engine skyline",
    ].join("\n"),
  },
  {
    engine: "spectronaut",
    host: "Windows enterprise worker",
    versionLabel: "Spectronaut CLI install",
    command: [
      "$env:MSCONNECT_PROCESSOR_ENGINE='spectronaut'",
      "$env:MSCONNECT_AGENT_NAME='spectronaut-win-01'",
      "$env:MSCONNECT_AGENT_TOKEN='<processor-token>'",
      "$env:MSCONNECT_API_BASE_URL='http://msconnect-server:8000/api'",
      "$env:RAW_FILE_STORAGE_ROOT='\\\\nas\\msconnect\\raw'",
      "$env:RESULTS_ROOT='\\\\nas\\msconnect\\results'",
      "$env:PROCESSOR_SHARED_STORAGE_ROOT='\\\\nas\\msconnect'",
      ".\\.venv\\Scripts\\python manage.py run_processor_agent --engine spectronaut",
    ].join("\n"),
  },
  {
    engine: "proteome-discoverer",
    host: "Windows enterprise worker",
    versionLabel: "Proteome Discoverer CLI or handoff wrapper",
    command: [
      "$env:MSCONNECT_PROCESSOR_ENGINE='proteome-discoverer'",
      "$env:MSCONNECT_AGENT_NAME='pd-win-01'",
      "$env:MSCONNECT_AGENT_TOKEN='<processor-token>'",
      "$env:MSCONNECT_API_BASE_URL='http://msconnect-server:8000/api'",
      "$env:RAW_FILE_STORAGE_ROOT='\\\\nas\\msconnect\\raw'",
      "$env:RESULTS_ROOT='\\\\nas\\msconnect\\results'",
      "$env:PROCESSOR_SHARED_STORAGE_ROOT='\\\\nas\\msconnect'",
      ".\\.venv\\Scripts\\python manage.py run_processor_agent --engine proteome-discoverer",
    ].join("\n"),
  },
];

const readinessCommands = [
  "curl -f http://localhost:8080/healthz/",
  "curl -f http://localhost:8080/readyz/",
  "docker compose run --rm watcher python manage.py check_agent_runtime --role watcher --write-test",
  "docker compose run --rm processor python manage.py check_agent_runtime --role processor --engine processor --write-test",
  "docker compose exec web python manage.py create_e2e_smoke_fixture --code E2E-SMOKE",
  "docker compose run --rm watcher python manage.py run_watcher_agent --once --match-run-by-name",
  "docker compose run --rm processor python manage.py run_processor_agent --once",
  "docker compose exec web python manage.py verify_e2e_smoke_fixture --code E2E-SMOKE",
];

export default function AdminDashboardPage() {
  const projectsQuery = useQuery({
    queryKey: queryKeys.projects({ page: 1, page_size: 1 }),
    queryFn: () => fetchProjects({ page: 1, page_size: 1 }),
  });
  const rawFilesQuery = useQuery({
    queryKey: queryKeys.rawFilesOverview(),
    queryFn: () => fetchRawFilesOverview(),
    refetchInterval: 15_000,
  });
  const jobsQuery = useQuery({
    queryKey: queryKeys.processingJobsOverview(),
    queryFn: () => fetchProcessingJobsOverview(),
    refetchInterval: 15_000,
  });
  const nodesQuery = useQuery({
    queryKey: queryKeys.processingNodes({ page: 1, page_size: 500 }),
    queryFn: () => fetchProcessingNodes({ page: 1, page_size: 500 }),
    refetchInterval: 10_000,
  });
  const nodesOverviewQuery = useQuery({
    queryKey: queryKeys.processingNodesOverview(),
    queryFn: () => fetchProcessingNodesOverview(),
    refetchInterval: 10_000,
  });
  const pipelinesQuery = useQuery({
    queryKey: queryKeys.processingPipelines({ page: 1, page_size: 1 }),
    queryFn: () => fetchProcessingPipelines({ page: 1, page_size: 1 }),
  });
  const acquisitionsQuery = useQuery({
    queryKey: queryKeys.acquisitions({ page: 1, page_size: 1 }),
    queryFn: () => fetchAcquisitions({ page: 1, page_size: 1 }),
  });
  const nodes = nodesQuery.data?.results ?? [];
  const redNodes = nodes.filter((node) => node.health === "red").length;
  const yellowNodes = nodes.filter((node) => node.health === "yellow").length;
  const engineRows = summarizeEngines(nodes);
  const systemStatus = redNodes || (jobsQuery.data?.failed ?? 0) > 0 ? "failed" : yellowNodes ? "warning" : "complete";

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Admin" }]} />

      <PageHero
        eyebrow="System administration"
        title="Admin dashboard"
        description="System-wide operations across projects, raw storage, processing, QC, uploads, agent health, and Django records."
        actions={
          <>
            <StatusBadge status={systemStatus} />
            <Button asChild variant="secondary">
              <Link to="/processing/admin">
                <Server className="h-4 w-4" />
                Processor admin
              </Link>
            </Button>
            <Button asChild>
              <a href="/admin/">
                <ExternalLink className="h-4 w-4" />
                Django admin
              </a>
            </Button>
          </>
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Projects" value={metricValue(projectsQuery.data?.count)} detail="system portfolio" />
        <MetricCard label="Raw Files" value={metricValue(rawFilesQuery.data?.total)} detail={`${metricValue(rawFilesQuery.data?.unmatched)} unmatched`} />
        <MetricCard label="Pipelines" value={metricValue(pipelinesQuery.data?.count)} detail="registered versions" />
        <MetricCard label="Worklists" value={metricValue(acquisitionsQuery.data?.count)} detail="acquisition plans" />
        <MetricCard label="Nodes" value={metricValue(nodesOverviewQuery.data?.total)} detail={`${metricValue(nodesOverviewQuery.data?.stale)} stale`} />
        <MetricCard label="Active Jobs" value={metricValue(jobsQuery.data?.active)} detail={`${metricValue(jobsQuery.data?.failed)} failed`} />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>End-to-End Readiness</CardTitle>
          <CardDescription>Run these checks before handing the system to users or adding external Windows processors.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 xl:grid-cols-[360px_1fr]">
          <div className="grid gap-3">
            <ReadinessStep title="Web" detail="/healthz proves Django is serving; /readyz checks database and storage roots." />
            <ReadinessStep title="Agents" detail="check_agent_runtime validates DNS, TCP, bearer token role, API ping, and shared storage." />
            <ReadinessStep title="Smoke" detail="Create a small fixture, let watcher import it, let processor complete it, then verify artifacts." />
          </div>
          <pre className="max-h-80 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-100"><code>{readinessCommands.join("\n")}</code></pre>
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>System Features</CardTitle>
            <CardDescription>Operational entry points for the full MSConnect workspace.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {featureLinks.map((feature) => (
              <FeatureLink key={feature.href} {...feature} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Live Processor Health</CardTitle>
            <CardDescription>All reporting nodes grouped by engine identity.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {engineRows.map((engine) => (
              <div key={engine.type} className="rounded-lg border bg-background/50 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-black">{engine.type}</div>
                  <StatusBadge status={engine.red ? "failed" : engine.yellow ? "warning" : "complete"} />
                </div>
                <div className="mt-2 text-sm text-muted-foreground">
                  {engine.total} nodes · {engine.green} green · {engine.yellow} yellow · {engine.red} red
                </div>
              </div>
            ))}
            {!engineRows.length ? <div className="rounded-lg border p-4 text-sm text-muted-foreground">No processor nodes have reported yet.</div> : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[420px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Newest Heartbeats</CardTitle>
            <CardDescription>Host identity, IP address, and heartbeat recency.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {nodes
              .slice()
              .sort((left, right) => new Date(right.last_heartbeat_at ?? 0).getTime() - new Date(left.last_heartbeat_at ?? 0).getTime())
              .slice(0, 8)
              .map((node) => (
                <NodeHeartbeatRow key={node.id} node={node} />
              ))}
            {!nodes.length ? <div className="rounded-lg border p-4 text-sm text-muted-foreground">No live instances registered.</div> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Boot Processor Nodes</CardTitle>
            <CardDescription>Start one command runner per engine or host pool; each heartbeat registers the node in Processor Admin.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-3 md:grid-cols-2">
              {processorBootProfiles.map((profile) => (
                <ProcessorBootCard key={profile.engine} {...profile} />
              ))}
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function ReadinessStep({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-lg border bg-background/50 p-3">
      <div className="flex items-center gap-2 font-black">
        <ShieldAlert className="h-4 w-4" />
        {title}
      </div>
      <div className="mt-1 text-sm leading-5 text-muted-foreground">{detail}</div>
    </div>
  );
}

function FeatureLink({
  title,
  description,
  href,
  icon: Icon,
}: {
  title: string;
  description: string;
  href: string;
  icon: typeof ShieldAlert;
}) {
  return (
    <Button asChild variant="ghost" className="h-auto justify-start rounded-lg border bg-background/50 p-4 text-left">
      <Link to={href} className="grid w-full gap-3">
        <span className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-secondary">
              <Icon className="h-4 w-4" />
            </span>
            <span className="truncate font-black">{title}</span>
          </span>
          <ArrowRight className="h-4 w-4 shrink-0" />
        </span>
        <span className="whitespace-normal text-sm font-normal leading-5 text-muted-foreground">{description}</span>
      </Link>
    </Button>
  );
}

function NodeHeartbeatRow({ node }: { node: ProcessingNode }) {
  return (
    <div className="rounded-lg border bg-background/50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold">{node.name}</div>
          <div className="text-xs text-muted-foreground">{node.node_type} · {node.ip_address || "No IP"}</div>
        </div>
        <StatusBadge status={node.health === "red" ? "failed" : node.health === "yellow" ? "warning" : "complete"} />
      </div>
      <div className="mt-2 text-xs text-muted-foreground">
        {node.last_heartbeat_at ? `${formatDate(node.last_heartbeat_at)} (${node.seconds_since_heartbeat ?? "-"}s ago)` : "No heartbeat"}
      </div>
    </div>
  );
}

function ProcessorBootCard({
  engine,
  host,
  versionLabel,
  command,
}: {
  engine: string;
  host: string;
  versionLabel: string;
  command: string;
}) {
  return (
    <div className="rounded-lg border bg-background/50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-black">
            <TerminalSquare className="h-4 w-4" />
            {engine}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">{host}</div>
        </div>
        <StatusBadge status="queued" />
      </div>
      <div className="mt-3 rounded-md border bg-secondary/45 p-2 text-xs text-muted-foreground">{versionLabel}</div>
      <pre className="mt-3 max-h-56 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100"><code>{command}</code></pre>
    </div>
  );
}

function summarizeEngines(nodes: ProcessingNode[]) {
  const byType = new Map<string, { type: string; total: number; green: number; yellow: number; red: number }>();
  for (const node of nodes) {
    const current = byType.get(node.node_type) ?? { type: node.node_type, total: 0, green: 0, yellow: 0, red: 0 };
    current.total += 1;
    current[node.health] += 1;
    byType.set(node.node_type, current);
  }
  return [...byType.values()].sort((left, right) => left.type.localeCompare(right.type));
}

function metricValue(value?: number) {
  return value === undefined ? "-" : numberFormat.format(value);
}
