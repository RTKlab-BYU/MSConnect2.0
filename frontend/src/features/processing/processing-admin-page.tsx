import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Pause, Play, Power, RefreshCw, RotateCcw, Server, ShieldAlert, Stethoscope } from "lucide-react";
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
  fetchProcessingNodes,
  fetchProcessingNodesOverview,
  fetchProcessingNodeEvents,
  markProcessingNodeOffline,
  runProcessingNodeDiagnostics,
  queryKeys,
} from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import type { ProcessingNode } from "@/lib/api/types";
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
  const [typeFilter, setTypeFilter] = useState("all");
  const nodesQuery = useQuery({
    queryKey: queryKeys.processingNodes({ page: 1, page_size: 500 }),
    queryFn: () => fetchProcessingNodes({ page: 1, page_size: 500 }),
    refetchInterval: 10_000,
  });
  const overviewQuery = useQuery({
    queryKey: queryKeys.processingNodesOverview(),
    queryFn: () => fetchProcessingNodesOverview(),
    refetchInterval: 10_000,
  });
  const jobsQuery = useQuery({
    queryKey: queryKeys.processingJobsOverview({ active: true }),
    queryFn: () => fetchProcessingJobsOverview({ active: true }),
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
    mutationFn: (node: ProcessingNode) => runProcessingNodeDiagnostics(node.id, ["api", "storage", "engine"]),
    onSuccess: refreshNodes,
  });

  const nodes = nodesQuery.data?.results ?? [];
  const visibleNodes = nodes.filter((node) => typeFilter === "all" || node.node_type === typeFilter);
  const engines = summarizeEngines(nodes);
  const redNodes = nodes.filter((node) => node.health === "red").length;
  const yellowNodes = nodes.filter((node) => node.health === "yellow").length;

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Processing", href: "/processing" }, { label: "Admin" }]} />

      <PageHero
        eyebrow="Admin control"
        title="Node administration"
        description="Live watcher and processor inventory, engine health, host identity, shared storage settings, diagnostics, and control requests."
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

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Nodes" value={overviewQuery.data?.total ?? "-"} detail="registered workers" />
        <MetricCard label="Stale" value={overviewQuery.data?.stale ?? 0} detail="heartbeat older than 180s" />
        <MetricCard label="Red" value={redNodes} detail="offline, stale, or error" />
        <MetricCard label="Yellow" value={yellowNodes} detail="delayed heartbeat" />
        <MetricCard label="Active Jobs" value={jobsQuery.data?.active ?? "-"} detail="assigned/running/retrying" />
        <MetricCard label="Failed Jobs" value={jobsQuery.data?.failed ?? "-"} detail="needs operator review" />
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Engine Health</CardTitle>
              <CardDescription>Node types correspond to installed processor instances such as DIA-NN, FragPipe, Skyline, Spectronaut, and Proteome Discoverer.</CardDescription>
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
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {engines.map((engine) => (
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
          {!engines.length ? <div className="rounded-lg border p-4 text-sm text-muted-foreground">No processor nodes have reported yet.</div> : null}
        </CardContent>
      </Card>

      <div className="grid gap-4">
        {visibleNodes.map((node) => (
          <NodeAdminCard
            key={node.id}
            node={node}
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
  busy,
  onControl,
  onOffline,
  onDiagnostics,
}: {
  node: ProcessingNode;
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
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-4 w-4" />
              {node.name}
            </CardTitle>
            <CardDescription>{node.node_type} · {node.ip_address || "No IP reported"}</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={node.status} />
            <StatusBadge status={node.health === "red" ? "failed" : node.health === "yellow" ? "warning" : "complete"} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="grid gap-3 md:grid-cols-2">
          <InfoBlock label="Heartbeat" value={node.last_heartbeat_at ? `${formatDate(node.last_heartbeat_at)} (${node.seconds_since_heartbeat ?? "-"}s ago)` : "Never"} />
          <InfoBlock label="Endpoint" value={node.endpoint_url || "-"} />
          <InfoBlock label="Image / Install" value={node.container_image || "-"} />
          <InfoBlock label="Engine profile" value={engineProfile(node)} />
          <InfoBlock label="IP Address" value={node.ip_address || "-"} />
          <InfoBlock label="Shared Storage" value={stringSetting(node.settings.processor_shared_storage_root) || stringSetting(node.settings.results_root) || "-"} />
          <InfoBlock label="Raw Storage" value={stringSetting(node.settings.raw_file_storage_root) || "-"} />
        </div>

        <div className="grid gap-3">
          <div className="rounded-lg border bg-secondary/45 p-3">
            <div className="flex items-center gap-2 text-sm font-black">
              <ShieldAlert className="h-4 w-4" />
              Control
            </div>
            {controlCommand ? (
              <div className="mt-2 rounded-lg border bg-background/70 p-2 text-xs text-muted-foreground">
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
          <details className="rounded-lg border bg-background/50 p-3">
            <summary className="cursor-pointer text-sm font-black">Settings and metadata</summary>
            <pre className="mt-3 max-h-64 overflow-auto text-xs"><code>{JSON.stringify({ settings: node.settings, metadata: node.metadata }, null, 2)}</code></pre>
          </details>
          <div className="rounded-lg border bg-background/50 p-3">
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

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background/50 p-3">
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
