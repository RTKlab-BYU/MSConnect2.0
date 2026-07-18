import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatDate } from "@/lib/format";
import { useRunStatusFeed } from "@/lib/realtime/status-feed";

type HistoryPoint = {
  time: string;
  active: number;
  failed: number;
  rawFiles: number;
};

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

export default function MonitoringPage() {
  const feed = useRunStatusFeed();
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const active = feed.jobsOverview?.active ?? 0;
  const failed = feed.jobsOverview?.failed ?? 0;
  const rawFiles = feed.rawFilesOverview?.total ?? 0;

  useEffect(() => {
    if (!feed.lastUpdatedAt) return;
    setHistory((current) => [
      ...current.slice(-39),
      {
        time: new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
          new Date(feed.lastUpdatedAt),
        ),
        active,
        failed,
        rawFiles,
      },
    ]);
  }, [active, failed, feed.lastUpdatedAt, rawFiles]);

  const statusText = useMemo(() => {
    if (feed.reconnecting) return "Reconnecting and reconciling snapshot";
    if (feed.connected) return "Polling fallback connected";
    return "Polling fallback interrupted";
  }, [feed.connected, feed.reconnecting]);

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Monitoring" }]} />

      <section className="rounded-lg border bg-card p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase text-muted-foreground">High-throughput operations</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight">Run and Processing Dashboard</h1>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              Uses one centralized polling feed today. The hook is transport-neutral so a WebSocket or SSE source can replace polling later.
            </p>
          </div>
          <div className="rounded-md border bg-secondary px-3 py-2 text-sm font-semibold">
            {statusText}
            {feed.lastUpdatedAt ? (
              <span className="ml-2 text-muted-foreground">{formatDate(new Date(feed.lastUpdatedAt).toISOString())}</span>
            ) : null}
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Active Jobs" value={active} detail="queued, assigned, running, retrying" />
        <MetricCard label="Failed Jobs" value={failed} detail="needs review" />
        <MetricCard label="Processing Nodes" value={feed.nodesOverview?.total ?? "-"} detail="registered workers" />
        <MetricCard label="Raw Files" value={rawFiles} detail="known SDMS files" />
        <MetricCard label="Unmatched Raw" value={feed.rawFilesOverview?.unmatched ?? "-"} detail="operator review" />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>Backlog Trend</CardTitle>
            <CardDescription>Local dashboard history from reconciled polling snapshots.</CardDescription>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ left: -24, right: 8, top: 8, bottom: 0 }}>
                <XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
                <Tooltip cursor={{ stroke: "hsl(var(--border))" }} />
                <Area dataKey="active" stroke="hsl(var(--info))" fill="hsl(var(--info) / 0.18)" />
                <Area dataKey="failed" stroke="hsl(var(--destructive))" fill="hsl(var(--destructive) / 0.14)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Node Health</CardTitle>
            <CardDescription>Current processing/uploader node records from the main API.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2">
              {feed.nodes.map((node) => (
                <div key={node.id} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold">{node.name}</div>
                      <div className="text-xs text-muted-foreground">{node.node_type}</div>
                    </div>
                    <StatusBadge status={node.status} />
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    Last heartbeat: {formatDate(node.last_heartbeat_at)}
                  </div>
                </div>
              ))}
              {!feed.nodes.length && (
                <div className="rounded-md border p-4 text-sm text-muted-foreground">No processing nodes registered.</div>
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Active Jobs</CardTitle>
          <CardDescription>Jobs use the formal queued → assigned → running → complete / failed / retrying state model.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2">
            {feed.activeJobs.map((job) => (
              <div key={job.id} className="grid gap-2 rounded-md border p-3 md:grid-cols-[120px_160px_1fr_1fr]">
                <div className="font-mono text-sm">Job #{job.id}</div>
                <StatusBadge status={job.status} />
                <div className="text-sm text-muted-foreground">Run ID {job.run}</div>
                <div className="truncate text-sm text-muted-foreground">
                  Node: {job.node_name ?? "not assigned"}
                </div>
              </div>
            ))}
            {!feed.activeJobs.length && (
              <div className="rounded-md border p-4 text-sm text-muted-foreground">No queued or running jobs.</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
