import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { WorklistGeneratorFlow } from "@/features/worklist-generator/worklist-generator-flow";
import { quickStartProject, fetchProjects, queryKeys } from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import { projectColumns } from "@/features/projects/table-columns";

export default function ProjectsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [quickStartOpen, setQuickStartOpen] = useState(false);
  const [quickStartError, setQuickStartError] = useState("");
  const [quickStartForm, setQuickStartForm] = useState({ title: "Untitled DIA Project", code: "" });

  const params = useMemo(
    () => ({ page: 1, page_size: 100, search, status: status === "all" ? "" : status }),
    [search, status],
  );
  const projectQuery = useQuery({
    queryKey: queryKeys.projects(params),
    queryFn: () => fetchProjects(params),
  });
  const quickStartMutation = useMutation({
    mutationFn: quickStartProject,
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects(params) });
      setQuickStartOpen(false);
      window.location.assign(response.experiment?.id ? `/app/projects/${response.project.id}/experiments/${response.experiment.id}` : `/app/projects/${response.project.id}`);
    },
    onError: (error) => {
      setQuickStartError(error instanceof Error ? error.message : "Could not create quick-start project.");
    },
  });

  function submitQuickStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuickStartError("");
    quickStartMutation.mutate({ title: quickStartForm.title, code: quickStartForm.code || undefined });
  }

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Projects" }]} />
      <PageHero
        eyebrow="Project operations"
        title="Projects"
        description="Start pre-acquisition projects, register samples, generate worklists, and give watcher agents expected filenames before LC-MS acquisition."
        actions={
          <>
            <StatusBadge status="active" />
            <Dialog open={quickStartOpen} onOpenChange={setQuickStartOpen}>
              <DialogTrigger asChild>
                <Button><Plus className="h-4 w-4" />Quick start</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Quick start project</DialogTitle>
                  <DialogDescription>Create the project now, then import or edit the LC-MS worklist from the project page.</DialogDescription>
                </DialogHeader>
                <form className="grid gap-3" onSubmit={submitQuickStart}>
                  <label className="grid gap-1 text-sm font-bold">
                    Project title
                    <Input value={quickStartForm.title} onChange={(event) => setQuickStartForm((current) => ({ ...current, title: event.target.value }))} required />
                  </label>
                  <label className="grid gap-1 text-sm font-bold">
                    Project code
                    <Input value={quickStartForm.code} placeholder="Auto-generated if blank" onChange={(event) => setQuickStartForm((current) => ({ ...current, code: event.target.value }))} />
                  </label>
                  {quickStartError ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{quickStartError}</div> : null}
                  <div className="flex justify-end gap-2 border-t pt-3">
                    <Button type="button" variant="secondary" onClick={() => setQuickStartOpen(false)}>Cancel</Button>
                    <Button type="submit" disabled={quickStartMutation.isPending}>{quickStartMutation.isPending ? "Creating..." : "Create project"}</Button>
                  </div>
                </form>
              </DialogContent>
            </Dialog>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="secondary">Advanced Setup</Button>
              </DialogTrigger>
              <DialogContent className="max-h-[92vh] max-w-5xl overflow-auto rounded-3xl p-6">
                <DialogHeader>
                  <DialogTitle className="text-2xl font-black tracking-tight">WorkListGenerator</DialogTitle>
                  <DialogDescription>Follow the three WorkListGenerator stages here.</DialogDescription>
                </DialogHeader>
                <WorklistGeneratorFlow />
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Find a project</CardTitle>
          <CardDescription>Search by code, title, lab, or PI and keep the list intentionally compact.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-[1fr_220px]">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input className="pl-9" placeholder="Search code, title, lab, PI..." value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger><SelectValue placeholder="Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="paused">Paused</SelectItem>
                <SelectItem value="complete">Complete</SelectItem>
                <SelectItem value="archived">Archived</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <DataTable columns={projectColumns} data={projectQuery.data?.results ?? []} emptyLabel={projectQuery.isLoading ? "Loading projects..." : "No projects found."} />
    </div>
  );
}
