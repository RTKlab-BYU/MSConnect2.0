import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ExternalLink, FlaskConical, RefreshCw, Save, Server, Users } from "lucide-react";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  fetchDeploymentSettings, fetchPipelineEvents, fetchProcessingNodes, fetchProcessingPipelines, fetchProjects,
  fetchProjectDiannPreflight, fetchSystemHealth, queryKeys, updateDeploymentSettings, updateProjectDiannSettings,
} from "@/lib/api/queries";

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function pretty(value: unknown) { return JSON.stringify(value ?? {}, null, 2); }
function tagEntries(value: Record<string, unknown> | undefined) { return Object.entries(value ?? {}).filter(([, item]) => item !== null && item !== undefined && String(item).trim() !== ""); }

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedExperimentId, setSelectedExperimentId] = useState<number | null>(null);
  const [threads, setThreads] = useState("");
  const [temp, setTemp] = useState("");
  const [selectedPrtc, setSelectedPrtc] = useState("");
  const [selectedTargeted, setSelectedTargeted] = useState("");
  const [projectJson, setProjectJson] = useState("{}");
  const [projectError, setProjectError] = useState("");
  const deploymentQuery = useQuery({ queryKey: queryKeys.deploymentSettings(), queryFn: fetchDeploymentSettings });
  const projectsQuery = useQuery({ queryKey: queryKeys.projects({ page: 1, page_size: 500 }), queryFn: () => fetchProjects({ page: 1, page_size: 500 }) });
  const nodesQuery = useQuery({ queryKey: queryKeys.processingNodes({ page: 1, page_size: 500 }), queryFn: () => fetchProcessingNodes({ page: 1, page_size: 500 }) });
  const pipelinesQuery = useQuery({ queryKey: queryKeys.processingPipelines({ page: 1, page_size: 500 }), queryFn: () => fetchProcessingPipelines({ page: 1, page_size: 500 }) });
  const healthQuery = useQuery({ queryKey: queryKeys.systemHealth(), queryFn: fetchSystemHealth, refetchInterval: 15_000 });
  const preflightQuery = useQuery({ queryKey: queryKeys.projectDiannPreflight(selectedProjectId ?? 0), queryFn: () => fetchProjectDiannPreflight(selectedProjectId as number), enabled: selectedProjectId !== null });
  const eventsQuery = useQuery({ queryKey: queryKeys.pipelineEvents({ project: selectedProjectId ?? undefined, page: 1, page_size: 50 }), queryFn: () => fetchPipelineEvents({ project: selectedProjectId as number, page: 1, page_size: 50 }), enabled: selectedProjectId !== null, refetchInterval: 15_000 });
  const deployment = deploymentQuery.data;
  const metadata = objectValue(deployment?.metadata);
  const diannMetadata = objectValue(metadata.diann);
  const performanceTags = objectValue(diannMetadata.performance_tags ?? metadata.diann_performance_tags);
  const projects = useMemo(() => projectsQuery.data?.results ?? [], [projectsQuery.data?.results]);
  const pipelines = pipelinesQuery.data?.results ?? [];
  const projectPreflight = preflightQuery.data;
  const experimentalTags = objectValue(projectPreflight?.experimental_tags);
  const skylinePipelines = pipelines.filter((pipeline) => objectValue(pipeline.parameters).engine === "skyline" || pipeline.name.toLowerCase().includes("skyline"));

  useEffect(() => { if (selectedProjectId === null && projects[0]) setSelectedProjectId(projects[0].id); }, [projects, selectedProjectId]);
  useEffect(() => { setSelectedPrtc(deployment?.prtc_skyline_pipeline ? String(deployment.prtc_skyline_pipeline) : ""); setSelectedTargeted(deployment?.targeted_skyline_pipeline ? String(deployment.targeted_skyline_pipeline) : ""); }, [deployment?.prtc_skyline_pipeline, deployment?.targeted_skyline_pipeline]);
  useEffect(() => { setThreads(performanceTags.threads === undefined ? "" : String(performanceTags.threads)); setTemp(performanceTags.temp === undefined ? "" : String(performanceTags.temp)); }, [deployment?.updated_at, performanceTags.temp, performanceTags.threads]);
  useEffect(() => { if (projectPreflight?.worklist?.experiment) setSelectedExperimentId(projectPreflight.worklist.experiment); setProjectJson(pretty(experimentalTags)); }, [projectPreflight?.worklist?.experiment, projectPreflight?.pipeline?.updated_at, experimentalTags]);

  const deploymentMutation = useMutation({
    mutationFn: () => updateDeploymentSettings({ prtc_skyline_pipeline: selectedPrtc ? Number(selectedPrtc) : null, targeted_skyline_pipeline: selectedTargeted ? Number(selectedTargeted) : null, metadata: { ...metadata, diann: { ...diannMetadata, performance_tags: { threads: threads.trim() || undefined, temp: temp.trim() || undefined } } } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.deploymentSettings() }),
  });
  const projectMutation = useMutation({
    mutationFn: () => { if (!selectedProjectId || !selectedExperimentId) throw new Error("Select a project with a processing worklist."); return updateProjectDiannSettings(selectedProjectId, selectedExperimentId, { tags: { experimental: JSON.parse(projectJson) } }); },
    onSuccess: async () => { setProjectError(""); await Promise.all([queryClient.invalidateQueries({ queryKey: queryKeys.projectDiannPreflight(selectedProjectId ?? 0) }), queryClient.invalidateQueries({ queryKey: queryKeys.pipelineEvents({ project: selectedProjectId ?? undefined, page: 1, page_size: 50 }) })]); },
    onError: (error) => setProjectError(error instanceof Error ? error.message : "Could not save project settings."),
  });
  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedProjectId), [projects, selectedProjectId]);

  return <div className="grid gap-4">
    <Breadcrumbs items={[{ label: "Settings" }]} />
    <PageHero eyebrow="Operational configuration" title="Settings and lifecycle" description="Edit global controls, inspect resolved project tags, and follow configuration changes from one server-side view." actions={<Button asChild variant="secondary"><a href="/admin/"><ExternalLink className="h-4 w-4" />Open Django admin</a></Button>} />
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5"><MetricCard label="Pipelines" value={pipelinesQuery.data?.count ?? "-"} detail="registered definitions" /><MetricCard label="Nodes" value={nodesQuery.data?.count ?? "-"} detail="processor hosts" /><MetricCard label="Projects" value={projectsQuery.data?.count ?? "-"} detail="available scopes" /><MetricCard label="Readiness" value={healthQuery.data?.status ?? "-"} detail="API and storage state" /><MetricCard label="Events" value={eventsQuery.data?.count ?? "-"} detail="selected project history" /></section>
    <Card><CardHeader><CardTitle>Global system settings</CardTitle><CardDescription>Stored in the site deployment record and applied to resolved project pipelines.</CardDescription></CardHeader><CardContent className="grid gap-4 xl:grid-cols-[1fr_1fr_1.4fr]"><Field label="DIA-NN threads"><Input value={threads} onChange={(event) => setThreads(event.target.value)} inputMode="numeric" placeholder="1" /></Field><Field label="DIA-NN temp path"><Input value={temp} onChange={(event) => setTemp(event.target.value)} placeholder="/scratch/diann" /></Field><div className="grid gap-3 sm:grid-cols-2"><Field label="PRTC Skyline pipeline"><PipelineSelect value={selectedPrtc} onChange={setSelectedPrtc} pipelines={skylinePipelines} /></Field><Field label="Targeted Skyline pipeline"><PipelineSelect value={selectedTargeted} onChange={setSelectedTargeted} pipelines={skylinePipelines} /></Field></div><div className="xl:col-span-3 flex items-center justify-between gap-3 border-t pt-3"><TagList title="Stored performance tags" tags={performanceTags} /><Button onClick={() => deploymentMutation.mutate()} disabled={deploymentMutation.isPending}><Save className="h-4 w-4" />Save global settings</Button></div></CardContent></Card>
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
      <Card><CardHeader><CardTitle>Project settings</CardTitle><CardDescription>Select a project to inspect the pipeline attached to its latest worklist.</CardDescription></CardHeader><CardContent className="grid gap-4"><Field label="Project"><select className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={selectedProjectId ?? ""} onChange={(event) => { setSelectedProjectId(event.target.value ? Number(event.target.value) : null); setSelectedExperimentId(null); }}><option value="">Select a project</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.code} · {project.title}</option>)}</select></Field><div className="grid gap-2 text-sm"><InfoRow label="Pipeline" value={projectPreflight?.pipeline ? `${projectPreflight.pipeline.name} · ${projectPreflight.pipeline.version}` : "Not configured"} /><InfoRow label="Source" value={projectPreflight?.source_label ?? "-"} /><InfoRow label="Preset" value={projectPreflight?.processing_preset ?? "-"} /><InfoRow label="Validity" value={projectPreflight ? (projectPreflight.is_valid ? "Valid" : projectPreflight.validation_errors.join(" ")) : "-"} /></div><TagList title="Resolved performance tags" tags={projectPreflight?.performance_tags ?? {}} /></CardContent></Card>
      <Card><CardHeader><CardTitle>Experimental DB tags</CardTitle><CardDescription>{selectedProject ? `Editable project tags for ${selectedProject.code}. Global performance tags remain authoritative.` : "Choose a project with a worklist to edit its pipeline tags."}</CardDescription></CardHeader><CardContent className="grid gap-3"><Textarea className="min-h-64 font-mono text-xs" value={projectJson} onChange={(event) => setProjectJson(event.target.value)} disabled={!projectPreflight?.worklist || !selectedExperimentId} /><div className="flex items-center justify-between gap-3"><span className="text-xs text-destructive">{projectError}</span><div className="flex gap-2"><Button variant="secondary" onClick={() => setProjectJson(pretty(experimentalTags))} disabled={!projectPreflight?.worklist}><RefreshCw className="h-4 w-4" />Reset</Button><Button onClick={() => { try { JSON.parse(projectJson); setProjectError(""); projectMutation.mutate(); } catch { setProjectError("Experimental tags must be valid JSON."); } }} disabled={!projectPreflight?.worklist || projectMutation.isPending}><Save className="h-4 w-4" />Save project tags</Button></div></div></CardContent></Card>
    </section>
    <Card><CardHeader><CardTitle>Lifecycle activity</CardTitle><CardDescription>Configuration, ingestion, processing, and completion events for the selected project. Refreshes automatically.</CardDescription></CardHeader><CardContent><div className="divide-y">{(eventsQuery.data?.results ?? []).map((event) => <div key={event.id} className="grid gap-1 py-3 sm:grid-cols-[180px_1fr_auto] sm:items-center"><div className="text-xs text-muted-foreground">{new Date(event.created_at).toLocaleString()}</div><div><div className="font-semibold capitalize">{event.event_type.replaceAll("_", " ")}</div><div className="text-sm text-muted-foreground">{event.message || event.actor_username || "System event"}</div></div><div className="text-xs text-muted-foreground">{event.from_status && event.to_status ? `${event.from_status} -> ${event.to_status}` : event.actor_username || "system"}</div></div>)}</div></CardContent></Card>
    <Card><CardHeader><CardTitle>Configuration areas</CardTitle><CardDescription>Direct access to the underlying operational registries.</CardDescription></CardHeader><CardContent><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><Area icon={Users} title="Users and labs" href="/admin/core/userprofile/" /><Area icon={FlaskConical} title="Instruments" href="/admin/core/instrumentconfiguration/" /><Area icon={Activity} title="Pipelines" href="/processing" /><Area icon={Server} title="Agents" href="/processing/admin" /></div></CardContent></Card>
  </div>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="grid gap-1.5 text-sm font-semibold"><span>{label}</span>{children}</label>; }
function PipelineSelect({ value, onChange, pipelines }: { value: string; onChange: (value: string) => void; pipelines: Array<{ id: number; name: string; version: string }> }) { return <select className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={value} onChange={(event) => onChange(event.target.value)}><option value="">Unset</option>{pipelines.map((pipeline) => <option key={pipeline.id} value={pipeline.id}>{pipeline.name} · {pipeline.version}</option>)}</select>; }
function InfoRow({ label, value }: { label: string; value: string }) { return <div className="flex justify-between gap-3 border-b py-2"><span className="text-muted-foreground">{label}</span><span className="text-right font-medium">{value}</span></div>; }
function TagList({ title, tags }: { title: string; tags: Record<string, unknown> }) { return <div><div className="mb-2 text-xs font-bold uppercase text-muted-foreground">{title}</div>{tagEntries(tags).length ? <div className="flex flex-wrap gap-2">{tagEntries(tags).map(([key, value]) => <span key={key} className="rounded-md border bg-background/60 px-2 py-1 font-mono text-xs">{key}={typeof value === "object" ? JSON.stringify(value) : String(value)}</span>)}</div> : <div className="text-sm text-muted-foreground">None configured</div>}</div>; }
function Area({ icon: Icon, title, href }: { icon: typeof Users; title: string; href: string }) { return <div className="rounded-lg border bg-background/60 p-4"><Icon className="h-4 w-4" /><div className="mt-3 font-semibold">{title}</div><Button asChild className="mt-3" size="sm" variant="secondary"><a href={href}>Open <ExternalLink className="h-3.5 w-3.5" /></a></Button></div>; }
