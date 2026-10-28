import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, CheckCircle2, FlaskConical, Microscope, Server } from "lucide-react";
import { Link } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchCurrentUser, fetchProcessingJobsOverview, fetchProjects, fetchQcOverview, fetchRawFilesOverview, queryKeys } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { isOperatorRole } from "@/lib/ui-surface";

export default function DashboardPage() {
  const userQuery = useQuery({ queryKey: queryKeys.currentUser(), queryFn: fetchCurrentUser });
  const projectsQuery = useQuery({ queryKey: queryKeys.projects({ page: 1, page_size: 100 }), queryFn: () => fetchProjects({ page: 1, page_size: 100 }) });
  const filesQuery = useQuery({ queryKey: queryKeys.rawFilesOverview(), queryFn: () => fetchRawFilesOverview() });
  const jobsQuery = useQuery({ queryKey: queryKeys.processingJobsOverview(), queryFn: () => fetchProcessingJobsOverview() });
  const qcQuery = useQuery({ queryKey: queryKeys.qcOverview(), queryFn: () => fetchQcOverview() });
  const projects = projectsQuery.data?.results ?? [];
  const recentProjects = [...projects].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).slice(0, 5);
  const failed = jobsQuery.data?.failed ?? 0;
  const unmatched = filesQuery.data?.unmatched ?? 0;
  const outOfSpec = qcQuery.data?.out_of_spec_pair_count ?? 0;
  const attention = failed + unmatched + outOfSpec;
  const currentUser = userQuery.data;
  const isOperator = isOperatorRole(currentUser?.global_role);

  return <div className="grid gap-5">
    <Breadcrumbs items={[{ label: "Dashboard" }]} />
    <PageHero
      eyebrow={currentUser?.labs?.[0]?.name ?? "Research workspace"}
      title={`Welcome${currentUser?.username ? `, ${currentUser.username}` : " back"}`}
      description="Your projects and the next things that need attention, in one place. Open a project to follow its worklist, acquisition, processing, QC, and results."
      actions={<Button asChild><Link to="/projects"><FlaskConical className="h-4 w-4" />View projects</Link></Button>}
    />
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <MetricCard label="Projects" value={projectsQuery.data?.count ?? "-"} detail={`${projects.filter((p) => p.status === "active").length} active`} />
      <MetricCard label="Raw files" value={filesQuery.data?.total ?? "-"} detail={`${unmatched} unmatched`} />
      <MetricCard label="Active jobs" value={jobsQuery.data?.active ?? "-"} detail="queued or processing" />
      <MetricCard label="QC pairs" value={qcQuery.data?.complete_pair_count ?? "-"} detail={`${outOfSpec} need review`} />
      <MetricCard label="Needs attention" value={attention} detail={attention ? "exceptions across your workspace" : "no current exceptions"} />
    </section>
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div><CardTitle>Recent projects</CardTitle><CardDescription>Continue where your team last worked.</CardDescription></div>
          <Button asChild size="sm" variant="secondary"><Link to="/projects">All projects <ArrowRight className="h-4 w-4" /></Link></Button>
        </CardHeader>
        <CardContent className="divide-y">
          {recentProjects.map((project) => <Link key={project.id} to={`/projects/${project.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0 hover:text-primary">
            <div className="min-w-0"><div className="font-bold">{project.code} <span className="font-normal text-muted-foreground">· {project.title}</span></div><div className="mt-1 text-xs text-muted-foreground">Updated {formatDate(project.updated_at)}</div></div>
            <StatusBadge status={project.status} />
          </Link>)}
          {!recentProjects.length ? <div className="py-5 text-sm text-muted-foreground">{projectsQuery.isLoading ? "Loading projects…" : "No projects are available yet."}</div> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Workspace health</CardTitle><CardDescription>Items worth checking now.</CardDescription></CardHeader>
        <CardContent className="grid gap-2">
          <Attention icon={failed ? AlertTriangle : CheckCircle2} label="Failed processing jobs" value={failed} href="/processing" />
          <Attention icon={unmatched ? AlertTriangle : CheckCircle2} label="Unmatched raw files" value={unmatched} href="/uploads" />
          <Attention icon={outOfSpec ? AlertTriangle : CheckCircle2} label="HYE pairs out of spec" value={outOfSpec} href="/qc/hye" />
          {isOperator ? <div className="mt-2 grid grid-cols-2 gap-2"><Button asChild variant="secondary"><Link to="/monitoring"><Activity className="h-4 w-4" />Live monitoring</Link></Button><Button asChild variant="secondary"><Link to="/processing/admin"><Server className="h-4 w-4" />Processors</Link></Button></div> : null}
          <Button asChild variant="ghost" className="justify-start"><Link to="/qc/hye"><Microscope className="h-4 w-4" />Open QC workspaces</Link></Button>
        </CardContent>
      </Card>
    </section>
    <div className="text-xs text-muted-foreground">{currentUser?.email ? `Signed in as ${currentUser.email}` : ""}</div>
  </div>;
}

function Attention({ icon: Icon, label, value, href }: { icon: typeof AlertTriangle; label: string; value: number; href: string }) {
  return <Link to={href} className="flex items-center justify-between gap-3 rounded-lg border bg-background/50 p-3 hover:border-primary/40">
    <span className="flex items-center gap-2 text-sm"><Icon className={`h-4 w-4 ${value ? "text-warning" : "text-success"}`} />{label}</span><span className="font-black">{value}</span>
  </Link>;
}
