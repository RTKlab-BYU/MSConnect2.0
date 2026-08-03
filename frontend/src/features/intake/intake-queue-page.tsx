import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, Search, XCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { PageHero, MetricCard } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchIntakeMetrics, fetchIntakeRequests, promoteIntakeRequest, queryKeys, reviewIntakeRequest } from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import { formatDate } from "@/lib/format";

export default function IntakeQueuePage() {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const metricsQuery = useQuery({
    queryKey: queryKeys.intakeMetrics(),
    queryFn: fetchIntakeMetrics,
    refetchInterval: 30_000,
  });
  const queueQuery = useQuery({
    queryKey: queryKeys.intakeRequests({ status, search }),
    queryFn: () => fetchIntakeRequests({ status: status === "all" ? "" : status, search, page: 1, page_size: 100 }),
    refetchInterval: 15_000,
  });
  const reviewMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "in_review" | "approved" | "rejected" }) =>
      reviewIntakeRequest(id, { status, review_note: status === "approved" ? "Approved from queue" : "" }),
    onSuccess: refreshQueue,
  });
  const promoteMutation = useMutation({
    mutationFn: (id: number) => promoteIntakeRequest(id),
    onSuccess: refreshQueue,
  });

  const rows = queueQuery.data?.results ?? [];

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Intake queue" }]} />
      <PageHero
        eyebrow="Admin intake"
        title="Intake queue"
        description="Review collaborator submissions, move them through review, and promote approved requests into projects."
        actions={
          <Button asChild variant="secondary">
            <Link to="/submissions/new">
              <ExternalLink className="h-4 w-4" />
              New request
            </Link>
          </Button>
        }
      />

      <section className="grid gap-3 md:grid-cols-3">
        <MetricCard label="Requests" value={metricsQuery.data?.totals.requests ?? "-"} detail="visible in queue" />
        <MetricCard label="Samples" value={metricsQuery.data?.totals.sample_count_estimate ?? "-"} detail="estimated intake load" />
        <MetricCard label="Approved" value={metricsQuery.data?.totals.approved ?? "-"} detail="ready to promote" />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <CardDescription>Search by title or filter by queue status.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_220px]">
          <label className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" placeholder="Search titles" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="submitted">Submitted</SelectItem>
              <SelectItem value="in_review">In review</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <div className="grid gap-3">
        {rows.map((item) => (
          <Card key={item.id}>
            <CardContent className="grid gap-3 p-4 md:grid-cols-[1fr_auto] md:items-center">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-semibold">{item.requested_title}</div>
                  <StatusBadge status={item.status} />
                </div>
                <div className="text-sm text-muted-foreground">
                  {item.institution_name || item.metadata.institution.name} · {item.contact_name || item.metadata.contact.name} · {item.sample_count_estimate ?? 0} samples
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Lab {item.lab} · Submitted {formatDate(item.created_at)} · Updated {formatDate(item.updated_at)}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" disabled={reviewMutation.isPending} onClick={() => reviewMutation.mutate({ id: item.id, status: "in_review" })}>
                  <Search className="h-4 w-4" />
                  Review
                </Button>
                <Button size="sm" variant="secondary" disabled={reviewMutation.isPending} onClick={() => reviewMutation.mutate({ id: item.id, status: "approved" })}>
                  <CheckCircle2 className="h-4 w-4" />
                  Approve
                </Button>
                <Button size="sm" variant="secondary" disabled={reviewMutation.isPending} onClick={() => reviewMutation.mutate({ id: item.id, status: "rejected" })}>
                  <XCircle className="h-4 w-4" />
                  Reject
                </Button>
                <Button size="sm" disabled={promoteMutation.isPending || item.status !== "approved"} onClick={() => promoteMutation.mutate(item.id)}>
                  Promote
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {!rows.length ? <div className="rounded-2xl border border-dashed p-6 text-sm text-muted-foreground">No intake requests match the current filter.</div> : null}
      </div>
    </div>
  );
}

function refreshQueue() {
  void queryClient.invalidateQueries({ queryKey: queryKeys.intakeRequests() });
  void queryClient.invalidateQueries({ queryKey: queryKeys.intakeMetrics() });
}
