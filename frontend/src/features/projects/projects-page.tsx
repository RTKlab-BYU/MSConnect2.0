import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchProjects, queryKeys } from "@/lib/api/queries";
import { projectColumns } from "@/features/projects/table-columns";

export default function ProjectsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const params = useMemo(
    () => ({
      page: 1,
      page_size: 100,
      search,
      status: status === "all" ? "" : status,
    }),
    [search, status],
  );
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.projects(params),
    queryFn: () => fetchProjects(params),
  });

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Projects" }]} />
      <section className="rounded-lg border bg-card p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase text-muted-foreground">Project operations</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight">Projects</h1>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              Project is the top-level workspace for samples, acquisitions, raw files, and processing state.
            </p>
          </div>
          <div className="flex gap-2">
            <StatusBadge status="active" />
            <StatusBadge status="running" />
            <StatusBadge status="failed" />
          </div>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Project Search</CardTitle>
          <CardDescription>Search uses the additive DRF `search` parameter. Pagination is opt-in for this React app.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-[1fr_220px]">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search code, title, lab, PI..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
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

      <DataTable
        columns={projectColumns}
        data={data?.results ?? []}
        emptyLabel={isLoading ? "Loading projects..." : "No projects found."}
      />
    </div>
  );
}
