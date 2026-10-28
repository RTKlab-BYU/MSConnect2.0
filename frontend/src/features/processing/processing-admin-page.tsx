import { useMutation, useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Loader2, Pause, Play, Power, RefreshCw, RotateCcw, Server, ShieldAlert, Stethoscope } from "lucide-react";
import { Link, NavLink, useSearchParams } from "react-router-dom";
import { useState } from "react";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  controlProcessingNode,
  fetchProcessingJobsOverview,
  fetchProcessingJobs,
  fetchProcessingNodes,
  fetchProcessingNodeEvents,
  fetchAdminRuntimeSettings,
  markProcessingNodeOffline,
  runProcessingNodeDiagnostics,
  queryKeys,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import type { ProcessingJob, ProcessingNode } from "@/lib/api/types";
import { formatDate } from "@/lib/format";

const controlOptions = ["start", "pause", "resume", "drain", "restart", "stop", "upgrade", "reconfigure"] as const;
const controlLabels: Record<(typeof controlOptions)[number], string> = {
  start: "Start",
  pause: "Disable",
  resume: "Enable",
  drain: "Drain",
  restart: "Restart",
  stop: "Stop",
  upgrade: "Upgrade",
  reconfigure: "Reconfigure",
};

export default function ProcessingAdminPage() {
  const [searchParams] = useSearchParams();
  const nodeSection = searchParams.get("type") === "watcher" ? "watcher" : "processor";
  const isWatcher = nodeSection === "watcher";
  const [typeFilter, setTypeFilter] = useState("all");
  const nodesQuery = useQuery({
    queryKey: queryKeys.processingNodes({ page: 1, page_size: 500 }),
    queryFn: () => fetchProcessingNodes({ page: 1, page_size: 500 }),
    refetchInterval: 10_000,
  });
  const runtimeQuery = useQuery({ queryKey: queryKeys.adminRuntimeSettings(), queryFn: fetchAdminRuntimeSettings });
  const jobsQuery = useQuery({
    queryKey: queryKeys.processingJobsOverview({ active: true }),
    queryFn: () => fetchProcessingJobsOverview({ active: true }),
    enabled: !isWatcher,
    refetchInterval: 10_000,
  });
  const activeJobsQuery = useQuery({
    queryKey: queryKeys.processingJobs({ active: true, page: 1, page_size: 500 }),
    queryFn: () => fetchProcessingJobs({ active: true, page: 1, page_size: 500 }),
    enabled: !isWatcher,
    refetchInterval: 10_000,
  });
  const controlMutation = useMutation({
    mutationFn: ({ node, command }: { node: ProcessingNode; command: (typeof controlOptions)[number] }) => {
      const parameters = command === "upgrade" || command === "reconfigure"
        ? { profile: window.prompt(`Approved profile for ${command}`, engineProfile(node)) || engineProfile(node) }
        : undefined;
      return controlProcessingNode(node.id, { command, reason: "Admin dashboard request", parameters });
    },
    onSuccess: refreshNodes,
  });
  const offlineMutation = useMutation({
    mutationFn: (node: ProcessingNode) => markProcessingNodeOffline(node.id, "Admin dashboard mark-offline"),
    onSuccess: refreshNodes,
  });
  const diagnosticsMutation = useMutation({
    mutationFn: (node: ProcessingNode) => runProcessingNodeDiagnostics(node.id, node.node_type.toLowerCase() === "watcher" ? ["api", "storage"] : ["api", "storage", "engine"]),
    onSuccess: refreshNodes,
  });

  const nodes = (nodesQuery.data?.results ?? []).filter((node) => (node.node_type.toLowerCase() === "watcher") === isWatcher);
  const visibleNodes = nodes.filter((node) => isWatcher || typeFilter === "all" || node.node_type === typeFilter);
  const engines = summarizeEngines(nodes);
  const redNodes = nodes.filter((node) => node.health === "red").length;
  const yellowNodes = nodes.filter((node) => node.health === "yellow").length;
  const greenNodes = nodes.filter((node) => node.health === "green").length;
  const slurm = runtimeQuery.data?.compute.slurm;

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Administration", href: "/admin" }, { label: "Nodes & compute" }, { label: isWatcher ? "Watchers" : "Processors" }]} />

      <PageHero
        eyebrow="Admin control"
        title={isWatcher ? "Watcher administration" : "Processor administration"}
        description={isWatcher ? "Acquisition watcher agents only: heartbeat, file discovery, and upload service health." : "Processing workers only: engine health, Slurm/cloud execution readiness, shared storage, diagnostics, and control requests."}
        actions={
          <>
            <Button variant="secondary" onClick={refreshNodes}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
            <StatusBadge status={redNodes ? "failed" : yellowNodes ? "warning" : "complete"} />
          </>
        }
      />

      <nav aria-label="Node administration sections" className="flex w-fit gap-1 rounded-lg bg-muted p-1">
        <NavLink to="/processing/admin?type=processor" aria-current={!isWatcher ? "page" : undefined} className={`rounded-md px-4 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${!isWatcher ? "bg-card font-semibold text-foreground shadow-sm" : "text-muted-foreground hover:bg-card/70 hover:text-foreground"}`}>Processors</NavLink>
        <NavLink to="/processing/admin?type=watcher" aria-current={isWatcher ? "page" : undefined} className={`rounded-md px-4 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${isWatcher ? "bg-card font-semibold text-foreground shadow-sm" : "text-muted-foreground hover:bg-card/70 hover:text-foreground"}`}>Watchers</NavLink>
      </nav>

      <section className={`grid gap-3 sm:grid-cols-2 ${isWatcher ? "xl:grid-cols-4" : "xl:grid-cols-6"}`}>
        <MetricCard label={isWatcher ? "Watchers" : "Processors"} value={nodes.length} detail="registered in this instance" />
        <MetricCard label="Online" value={greenNodes} detail="heartbeat ≤ 75 seconds" />
        <MetricCard label="Delayed" value={yellowNodes} detail="heartbeat 76–180 seconds" />
        <MetricCard label="Offline / error" value={redNodes} detail="no heartbeat, >180s, offline, or error" />
        {!isWatcher ? <MetricCard label="Active Jobs" value={jobsQuery.data?.active ?? "-"} detail="assigned / running / retrying" /> : null}
        {!isWatcher ? <MetricCard label="Failed Jobs" value={jobsQuery.data?.failed ?? "-"} detail="needs operator review" /> : null}
      </section>

      {!isWatcher ? <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Processor engines</CardTitle>
              <CardDescription>Only processing workers are included here; acquisition watcher health is under the Watchers tab.</CardDescription>
            </div>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All engine types</SelectItem>
                {engines.map((engine) => (
                  <SelectItem key={engine.type} value={engine.type}>{engine.type}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {engines.map((engine) => (
            <div key={engine.type} className="min-w-0 rounded-md bg-muted p-3">
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                <div className="min-w-0 break-words font-semibold">{engine.type}</div>
                <StatusBadge className="shrink-0" status={engine.red ? "failed" : engine.yellow ? "warning" : "complete"} />
              </div>
              <div className="mt-2 break-words text-sm text-muted-foreground">
                {engine.total} {engine.total === 1 ? "node" : "nodes"} · {engine.green} green · {engine.yellow} yellow · {engine.red} red
              </div>
            </div>
          ))}
          {!engines.length ? <div className="rounded-md bg-muted p-4 text-sm text-muted-foreground">No processor nodes have reported yet.</div> : null}
        </CardContent>
      </Card> : <Card>
        <CardHeader><CardTitle>Watcher responsibilities</CardTitle><CardDescription>Watchers discover new acquisition files and register them against expected project runs. They do not appear in processor health or engine-load summaries.</CardDescription></CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3"><p className="max-w-2xl text-sm text-muted-foreground">Per-project live watcher routes are shown in that project’s Acquisition page. This tab reports only globally registered watcher agents.</p><Button asChild variant="secondary"><Link to="/watcher">Open watcher activity</Link></Button></CardContent>
      </Card>}

      {!isWatcher ? <Card>
        <CardHeader><CardTitle>Compute integrations</CardTitle><CardDescription>Execution configuration is read from the server environment. Cloud execution is not available until a provider adapter is implemented.</CardDescription></CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2">
          <IntegrationSummary title="Slurm" ready={Boolean(slurm?.configured)} detail={slurm?.configured ? `${slurm.host}:${slurm.port} · credentials/config present` : "Not ready: set host, dedicated remote root, container image, SSH key, and known_hosts for the Slurm processor."} />
          <IntegrationSummary title="Cloud compute" ready={false} detail="Not connected. No cloud adapter is configured; the UI will not offer cloud execution as if it were available." />
        </CardContent>
      </Card> : null}

      <div className="grid gap-4">
        {visibleNodes.map((node) => (
          <NodeAdminCard
            key={node.id}
            node={node}
            isWatcher={isWatcher}
            activeJobs={(activeJobsQuery.data?.results ?? []).filter((job) => job.node === node.id)}
            busy={controlMutation.isPending || offlineMutation.isPending || diagnosticsMutation.isPending}
            onControl={(command) => controlMutation.mutate({ node, command })}
            onOffline={() => offlineMutation.mutate(node)}
            onDiagnostics={() => diagnosticsMutation.mutate(node)}
          />
        ))}
        {!visibleNodes.length ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">No processing nodes match the current filter.</CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function NodeAdminCard({
  node,
  isWatcher,
  activeJobs,
  busy,
  onControl,
  onOffline,
  onDiagnostics,
}: {
  node: ProcessingNode;
  isWatcher: boolean;
  activeJobs: ProcessingJob[];
  busy: boolean;
  onControl: (command: (typeof controlOptions)[number]) => void;
  onOffline: () => void;
  onDiagnostics: () => void;
}) {
  const eventsQuery = useQuery({
    queryKey: ["processing-node-events", node.id],
    queryFn: () => fetchProcessingNodeEvents(node.id),
    refetchInterval: 15_000,
  });
  const control = node.active_control ?? {};
  const controlCommand = typeof control.command === "string" ? control.command : "";
  const controlStatus = typeof control.status === "string" ? control.status : "";

  return (
    <Card>
      <CardHeader>
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="flex min-w-0 flex-wrap items-center gap-2 break-words">
              <Server className="h-4 w-4 shrink-0" />
              {node.name}
            </CardTitle>
            <CardDescription>{node.node_type} · {node.ip_address || "No IP reported"}</CardDescription>
          </div>
          <div className="flex max-w-full flex-wrap items-center gap-2">
            <StatusBadge status={node.status} />
            <StatusBadge status={node.health === "red" ? "failed" : node.health === "yellow" ? "warning" : "complete"} />
          </div>
        </div>
      </CardHeader>
      {node.health !== "green" && node.health_guidance ? (
        <div role={node.health === "red" ? "alert" : "status"} className={`mx-4 mb-3 border-l-2 px-3 py-2 text-xs ${node.health === "red" ? "border-destructive bg-destructive/5" : "border-warning bg-warning/5"}`}>
          <span className="font-semibold">How to clear this status:</span> {node.health_guidance}
        </div>
      ) : null}
      <CardContent className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="grid min-w-0 gap-3 md:grid-cols-2">
          <InfoBlock label="Heartbeat" value={node.last_heartbeat_at ? `${formatDate(node.last_heartbeat_at)} (${node.seconds_since_heartbeat ?? "-"}s ago)` : "Never"} />
          <InfoBlock label="Endpoint" value={node.endpoint_url || "-"} />
          <InfoBlock label="Image / Install" value={node.container_image || "-"} />
          {!isWatcher ? <InfoBlock label="Engine profile" value={engineProfile(node)} /> : null}
          <InfoBlock label="IP Address" value={node.ip_address || "-"} />
          <InfoBlock label="Shared Storage" value={stringSetting(node.settings.processor_shared_storage_root) || stringSetting(node.settings.results_root) || "-"} />
          <InfoBlock label="Raw Storage" value={stringSetting(node.settings.raw_file_storage_root) || "-"} />
        </div>

          <div className="grid min-w-0 gap-3">
          {!isWatcher ? <section className="min-w-0 rounded-md bg-muted p-3" aria-label="Current processor work">
            <div className="flex items-center gap-2 text-sm font-semibold"><Activity className="h-4 w-4" /> Current work</div>
            <div className="mt-2 grid gap-3">
              {activeJobs.map((job) => <JobProgress key={job.id} job={job} />)}
              {!activeJobs.length ? <p className="text-xs text-muted-foreground">No active jobs assigned to this processor.</p> : null}
            </div>
          </section> : null}
          <div className="min-w-0 rounded-md bg-secondary p-3">
            <div className="flex items-center gap-2 text-sm font-black">
              <ShieldAlert className="h-4 w-4" />
              Control
            </div>
            {controlCommand ? (
              <div className="mt-2 break-words rounded-sm bg-card p-2 text-xs text-muted-foreground">
                Pending: <span className="font-bold text-foreground">{controlCommand}</span> · {controlStatus || "requested"}
              </div>
            ) : (
              <div className="mt-2 text-xs text-muted-foreground">No active control request.</div>
            )}
            <div className="mt-3 grid grid-cols-2 gap-2">
                <Button size="sm" variant="secondary" disabled={busy} onClick={onDiagnostics}>
                  <Stethoscope className="h-3.5 w-3.5" />
                  Test connection
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("start")}>
                  <Play className="h-3.5 w-3.5" />
                  {controlLabels.start}
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("pause")}>
                  <Pause className="h-3.5 w-3.5" />
                  {controlLabels.pause}
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("resume")}>
                  <Play className="h-3.5 w-3.5" />
                  {controlLabels.resume}
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("drain")}>
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {controlLabels.drain}
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("restart")}>
                  <RotateCcw className="h-3.5 w-3.5" />
                  {controlLabels.restart}
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("stop")}>
                  <Power className="h-3.5 w-3.5" />
                  {controlLabels.stop}
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("upgrade")}>
                  <RefreshCw className="h-3.5 w-3.5" />
                  {controlLabels.upgrade}
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => onControl("reconfigure")}>
                  <RotateCcw className="h-3.5 w-3.5" />
                  {controlLabels.reconfigure}
                </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={onOffline}>
                Offline
              </Button>
            </div>
          </div>
          <details className="min-w-0 rounded-md bg-muted p-3">
            <summary className="cursor-pointer text-sm font-black">Settings and metadata</summary>
            <pre className="mt-3 max-h-64 overflow-auto text-xs"><code>{JSON.stringify({ settings: node.settings, metadata: node.metadata }, null, 2)}</code></pre>
          </details>
          <div className="min-w-0 rounded-md bg-muted p-3">
            <div className="text-sm font-black">Recent activity</div>
            <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
              {(eventsQuery.data ?? []).slice(0, 5).map((event) => (
                <div key={event.id} className="flex justify-between gap-2">
                  <span>{event.event_type}{event.command ? ` · ${event.command}` : ""}</span>
                  <span>{event.status}</span>
                </div>
              ))}
              {!eventsQuery.data?.length ? <span>No recorded node events.</span> : null}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function JobProgress({ job }: { job: ProcessingJob }) {
  const rawPercent = job.stats.progress_percent;
  const percent = typeof rawPercent === "number" && Number.isFinite(rawPercent)
    ? Math.max(0, Math.min(100, rawPercent))
    : null;
  const title = job.raw_file_filename || job.run_name || `Processing job ${job.id}`;
  return <div className="min-w-0 border-t border-border/60 pt-2 first:border-t-0 first:pt-0">
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
      <span className="min-w-0 break-words text-xs font-semibold">{title}</span>
      <span className="flex shrink-0 items-center gap-1 text-xs text-primary">
        {job.status === "running" ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Activity className="h-3.5 w-3.5" aria-hidden="true" />}{job.status}
      </span>
    </div>
    <div className="mt-1 h-2 overflow-hidden rounded-full bg-background" role="progressbar" aria-label={`${title} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined} aria-valuetext={percent === null ? "Progress percentage not reported by processor" : `${percent}%`}>
      {percent === null
        ? <div className="h-full w-1/3 animate-[msconnect-progress-sweep_1.8s_ease-in-out_infinite] bg-primary" />
        : <div className="h-full bg-primary transition-[width] duration-500" style={{ width: `${percent}%` }} />}
    </div>
    {percent === null ? <p className="mt-1 text-[11px] text-muted-foreground">Working · processor does not report percent complete</p> : <p className="mt-1 text-[11px] text-muted-foreground">{percent}% complete</p>}
  </div>;
}

function IntegrationSummary({ title, ready, detail }: { title: string; ready: boolean; detail: string }) {
  return <div className="min-w-0 rounded-md bg-muted p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{title}</h3><StatusBadge status={ready ? "complete" : "warning"} /></div>
    <p className="mt-2 break-words text-sm text-muted-foreground">{detail}</p>
  </div>;
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md bg-muted p-3">
      <div className="text-[11px] font-black uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className="mt-2 break-all text-sm font-semibold">{value}</div>
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

function refreshNodes() {
  void queryClient.invalidateQueries({ queryKey: queryKeys.processingNodes() });
  void queryClient.invalidateQueries({ queryKey: queryKeys.processingNodesOverview() });
}

function stringSetting(value: unknown) {
  return typeof value === "string" ? value : "";
}

function engineProfile(node: ProcessingNode) {
  return (
    stringSetting(node.metadata.processor_engine_profile) ||
    stringSetting(node.metadata.processor_engine_version) ||
    stringSetting(node.settings.processor_engine_version) ||
    stringSetting(node.settings.engine_version) ||
    `${node.node_type} · profile unknown`
  );
}
