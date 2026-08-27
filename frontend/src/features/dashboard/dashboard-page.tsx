import { useQueries, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, Database, FlaskConical, HardDrive, LineChart, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchCurrentUser, fetchProcessingJobsOverview, fetchProjectSummary, fetchProjects, fetchQcOverview, fetchRawFilesOverview, queryKeys } from "@/lib/api/queries";
import type { CountBy, CurrentUser, Project, ProjectSummary } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { isOperatorRole } from "@/lib/ui-surface";

const numberFormat = new Intl.NumberFormat();
const chartColors = [
  "hsl(var(--primary))",
  "hsl(var(--accent))",
  "hsl(var(--info))",
  "hsl(var(--warning))",
  "hsl(var(--destructive))",
];

export default function DashboardPage() {
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const projectsQuery = useQuery({
    queryKey: queryKeys.projects({ page: 1, page_size: 100 }),
    queryFn: () => fetchProjects({ page: 1, page_size: 100 }),
  });
  const rawFilesQuery = useQuery({
    queryKey: queryKeys.rawFilesOverview(),
    queryFn: () => fetchRawFilesOverview(),
  });
  const jobsQuery = useQuery({
    queryKey: queryKeys.processingJobsOverview(),
    queryFn: () => fetchProcessingJobsOverview(),
  });
  const qcQuery = useQuery({
    queryKey: queryKeys.qcOverview(),
    queryFn: () => fetchQcOverview(),
  });

  const projects = projectsQuery.data?.results ?? [];
  const recentProjects = [...projects]
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
    .slice(0, 4);
  const summaryQueries = useQueries({
    queries: recentProjects.map((project) => ({
      queryKey: queryKeys.projectSummary(project.id),
      queryFn: () => fetchProjectSummary(project.id),
    })),
  });

  const projectStatusData = buildProjectStatusData(projects);
  const reportRows = [
    { name: "Raw files", value: rawFilesQuery.data?.total ?? 0 },
    { name: "Processing jobs", value: jobsQuery.data?.total ?? 0 },
    { name: "Active jobs", value: jobsQuery.data?.active ?? 0 },
    { name: "Failed jobs", value: jobsQuery.data?.failed ?? 0 },
    { name: "QC injections", value: qcQuery.data?.qc_injection_count ?? 0 },
  ];
  const activeProjects = projects.filter((project) => project.status === "active").length;
  const completedProjects = projects.filter((project) => project.status === "complete").length;
  const attentionCount = (jobsQuery.data?.failed ?? 0) + (rawFilesQuery.data?.unmatched ?? 0) + (qcQuery.data?.out_of_spec_pair_count ?? 0);
  const currentUser = currentUserQuery.data;
  const isOperator = isOperatorRole(currentUser?.global_role);
  const greeting = currentUser ? `Hello, ${currentUser.username}` : "Welcome back";
  const roleLabel = currentUser ? roleTitle(currentUser.global_role) : "Workspace";
  const quickSignals = [
    {
      label: "Projects",
      value: metricValue(projects.length),
      detail: `${metricValue(activeProjects)} active, ${metricValue(completedProjects)} complete`,
    },
    {
      label: "Files",
      value: metricValue(rawFilesQuery.data?.total),
      detail: `${metricValue(rawFilesQuery.data?.unmatched)} unmatched`,
    },
    {
      label: "Jobs",
      value: metricValue(jobsQuery.data?.active),
      detail: `${metricValue(jobsQuery.data?.failed)} failed`,
    },
    {
      label: "QC",
      value: metricValue(qcQuery.data?.out_of_spec_pair_count),
      detail: `${metricValue(qcQuery.data?.complete_pair_count)} complete pairs`,
    },
  ];
  const missedItems = [
    jobsQuery.data?.failed ? `${metricValue(jobsQuery.data.failed)} processing job(s) need review.` : null,
    rawFilesQuery.data?.unmatched ? `${metricValue(rawFilesQuery.data.unmatched)} raw file(s) still need matching.` : null,
    qcQuery.data?.out_of_spec_pair_count ? `${metricValue(qcQuery.data.out_of_spec_pair_count)} QC pair(s) are out of spec.` : null,
  ].filter(Boolean) as string[];

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Dashboard" }]} />

      <PageHero
        eyebrow={roleLabel}
        title={greeting}
        description="Here is what you missed across projects, processing, and QC. Open a project, inspect the sample, or jump straight into the active workflow."
        actions={
          <>
            <div className="hidden rounded-full border bg-secondary/70 px-4 py-2 text-sm font-semibold text-muted-foreground md:block">
              {currentUser?.labs?.length ? `${currentUser.labs[0].name} workspace` : "No lab selected"}
            </div>
            <Button asChild variant="secondary">
              <Link to="/projects">
                <FlaskConical className="h-4 w-4" />
                View projects
              </Link>
            </Button>
            <Button asChild>
              <Link to="/monitoring">
                <LineChart className="h-4 w-4" />
                Monitor runs
              </Link>
            </Button>
          </>
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {quickSignals.map((item) => (
          <MetricCard key={item.label} label={item.label} value={item.value} detail={item.detail} />
        ))}
        <MetricCard label="Attention" value={metricValue(attentionCount)} detail={missedItems.length ? "items that need review" : "no current exceptions"} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-secondary/20">
            <CardTitle>What you missed</CardTitle>
            <CardDescription>Short operational summary for the current session.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 p-5">
            {missedItems.length ? (
              missedItems.map((item) => (
                <div key={item} className="rounded-2xl border bg-background/60 p-4 text-sm">
                  {item}
                </div>
              ))
            ) : (
              <div className="rounded-2xl border bg-background/60 p-4 text-sm text-muted-foreground">
                No current exceptions. The workspace is quiet.
              </div>
            )}
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-2xl border bg-background/60 p-4">
                <div className="text-[11px] font-black uppercase tracking-[0.16em] text-muted-foreground">Last refresh</div>
                <div className="mt-2 text-sm font-semibold">{formatDate(new Date().toISOString())}</div>
              </div>
              <div className="rounded-2xl border bg-background/60 p-4">
                <div className="text-[11px] font-black uppercase tracking-[0.16em] text-muted-foreground">Role</div>
                <div className="mt-2 text-sm font-semibold">{roleLabel}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-secondary/20">
            <CardTitle>Quick paths</CardTitle>
            <CardDescription>Fast entry points for the most common workflows.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 p-5">
            <QuickPath title="Projects" description="Open a project, inspect samples, and follow the active workflow." to="/projects" />
            {isOperator ? <QuickPath title="Monitoring" description="Check connected nodes, queue pressure, and processing health." to="/monitoring" /> : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>Portfolio Report</CardTitle>
            <CardDescription>Project status and operational totals across your accessible workspace.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 lg:grid-cols-[260px_1fr]">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={projectStatusData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={3}>
                    {projectStatusData.map((entry, index) => (
                      <Cell key={entry.name} fill={chartColors[index % chartColors.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => numberFormat.format(Number(value))} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="grid content-center gap-3">
              {projectStatusData.map((item, index) => (
                <div key={item.name} className="grid gap-2">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <div className="flex items-center gap-2 font-bold">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: chartColors[index % chartColors.length] }} />
                      {item.name}
                    </div>
                    <span className="text-muted-foreground">{numberFormat.format(item.value)}</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted">
                    <div className="h-2 rounded-full bg-primary" style={{ width: `${percentage(item.value, projects.length)}%` }} />
                  </div>
                </div>
              ))}
              {!projectStatusData.length ? <EmptyState label={projectsQuery.isLoading ? "Loading projects..." : "No projects yet."} /> : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Needs Attention</CardTitle>
            <CardDescription>Exceptions from processing, raw-file matching, and QC reports.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <AttentionRow icon={AlertTriangle} label="Failed processing jobs" value={jobsQuery.data?.failed ?? 0} status={(jobsQuery.data?.failed ?? 0) > 0 ? "failed" : "complete"} />
            <AttentionRow icon={HardDrive} label="Unmatched raw files" value={rawFilesQuery.data?.unmatched ?? 0} status={(rawFilesQuery.data?.unmatched ?? 0) > 0 ? "warning" : "complete"} />
            <AttentionRow icon={Database} label="Out-of-spec QC pairs" value={qcQuery.data?.out_of_spec_pair_count ?? 0} status={(qcQuery.data?.out_of_spec_pair_count ?? 0) > 0 ? "warning" : "complete"} />
            <div className="mt-1 rounded-lg border bg-background/50 p-3 text-sm">
              <div className="flex items-center gap-2 font-bold">
                {attentionCount ? <AlertTriangle className="h-4 w-4 text-warning" /> : <CheckCircle2 className="h-4 w-4 text-success" />}
                {attentionCount ? `${numberFormat.format(attentionCount)} items to review` : "No current exceptions"}
              </div>
              <p className="mt-1 text-muted-foreground">Use Monitoring for queue details or open a project report below.</p>
            </div>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Workspace Activity</CardTitle>
          <CardDescription>Current counts for files, processing, and QC reporting.</CardDescription>
        </CardHeader>
        <CardContent className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={reportRows} margin={{ left: -18, right: 10, top: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
              <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={12} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
              <Tooltip cursor={{ fill: "hsl(var(--muted) / 0.45)" }} formatter={(value) => numberFormat.format(Number(value))} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="hsl(var(--accent))" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <section className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-black">Latest Project Reports</h2>
            <p className="mt-1 text-sm text-muted-foreground">A snapshot of samples, runs, processing outputs, and reportable results.</p>
          </div>
          <Button asChild variant="secondary">
            <Link to="/projects">
              All projects
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {recentProjects.map((project, index) => (
            <ProjectReportCard
              key={project.id}
              project={project}
              summary={summaryQueries[index]?.data}
              loading={summaryQueries[index]?.isLoading ?? false}
            />
          ))}
          {!recentProjects.length ? <EmptyState label={projectsQuery.isLoading ? "Loading project reports..." : "No project reports available yet."} /> : null}
        </div>
      </section>
    </div>
  );
}

function ProjectReportCard({ project, summary, loading }: { project: Project; summary?: ProjectSummary; loading: boolean }) {
  const failedJobs = summary ? countBy(summary.jobs_by_status, "status", "failed") : 0;
  const missingRawFiles = summary?.missing_raw_file_count ?? 0;
  const reportableResults = (summary?.reported_protein_count ?? 0) + (summary?.reported_peptide_count ?? 0) + (summary?.reported_precursor_count ?? 0);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{project.code}</CardTitle>
            <CardDescription>{project.title}</CardDescription>
          </div>
          <StatusBadge status={project.status} />
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        {loading ? (
          <div className="flex h-28 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading report
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <ReportMetric label="Samples" value={summary?.sample_count ?? 0} />
              <ReportMetric label="Runs" value={summary?.run_count ?? 0} />
              <ReportMetric label="Raw Files" value={summary?.raw_file_count ?? 0} />
              <ReportMetric label="Jobs" value={summary?.processing_job_count ?? 0} />
            </div>
            <div className="grid gap-2 rounded-lg border bg-background/50 p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">Reportable results</span>
                <span className="font-black">{numberFormat.format(reportableResults)}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">Artifacts and derivatives</span>
                <span className="font-black">{numberFormat.format((summary?.artifact_count ?? 0) + (summary?.derivative_count ?? 0))}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">Exceptions</span>
                <span className={failedJobs || missingRawFiles ? "font-black text-warning" : "font-black text-success"}>
                  {numberFormat.format(failedJobs + missingRawFiles)}
                </span>
              </div>
            </div>
          </>
        )}
        <div className="flex items-center justify-between gap-3 border-t pt-3 text-sm text-muted-foreground">
          <span>Updated {formatDate(project.updated_at)}</span>
          <Button asChild variant="secondary" size="sm">
            <Link to={`/projects/${project.id}`}>
              Open report
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ReportMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-background/50 p-3">
      <div className="text-[11px] font-black uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-black">{numberFormat.format(value)}</div>
    </div>
  );
}

function AttentionRow({ icon: Icon, label, value, status }: { icon: typeof AlertTriangle; label: string; value: number; status: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border bg-background/50 p-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold">{label}</div>
          <div className="text-xs text-muted-foreground">{numberFormat.format(value)} current</div>
        </div>
      </div>
      <StatusBadge status={status} />
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="rounded-lg border bg-card p-4 text-sm text-muted-foreground">{label}</div>;
}

function buildProjectStatusData(projects: Project[]) {
  return ["active", "paused", "complete", "archived"]
    .map((status) => ({
      name: status[0].toUpperCase() + status.slice(1),
      value: projects.filter((project) => project.status === status).length,
    }))
    .filter((item) => item.value > 0);
}

function roleTitle(role: CurrentUser["global_role"]) {
  switch (role) {
    case "admin":
      return "Admin workspace";
    case "pi":
      return "PI workspace";
    case "collaborator":
      return "Collaborator workspace";
    default:
      return "Research workspace";
  }
}

function countBy<TKey extends string>(rows: CountBy<TKey>, key: TKey, value: string) {
  return rows.find((row) => row[key] === value)?.count ?? 0;
}

function metricValue(value?: number) {
  return value === undefined ? "-" : numberFormat.format(value);
}

function QuickPath({ title, description, to }: { title: string; description: string; to: string }) {
  return (
    <Link
      to={to}
      className="group rounded-2xl border bg-background/60 p-4 text-left no-underline transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-black text-foreground">{title}</div>
        <ArrowRight className="h-4 w-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-foreground" />
      </div>
      <div className="mt-1 text-sm leading-6 text-muted-foreground">{description}</div>
    </Link>
  );
}

function percentage(value: number, total: number) {
  if (!total) return 0;
  return Math.max(3, Math.round((value / total) * 100));
}
