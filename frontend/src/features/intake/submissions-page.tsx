import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ClipboardList, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchCurrentUser, fetchIntakeRequests, queryKeys } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";

export default function SubmissionsPage() {
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const submissionsQuery = useQuery({
    queryKey: queryKeys.intakeRequests({ mine: true, page: 1, page_size: 100 }),
    queryFn: () => fetchIntakeRequests({ mine: true, page: 1, page_size: 100 }),
  });
  const submissions = submissionsQuery.data?.results ?? [];

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Submissions" }]} />
      <PageHero
        eyebrow="Collaborator workspace"
        title="My submissions"
        description="Track what has been submitted, what is in review, and which requests are ready for the next step."
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to="/submissions/new">
                <Plus className="h-4 w-4" />
                New request
              </Link>
            </Button>
            <Button asChild>
              <Link to="/uploads">
                <ArrowRight className="h-4 w-4" />
                Upload files
              </Link>
            </Button>
          </>
        }
      />

      <section className="grid gap-3 md:grid-cols-3">
        <Metric label="Labs" value={currentUserQuery.data?.labs.length ?? 0} detail="authorized orgs" />
        <Metric label="Open requests" value={submissions.filter((item) => item.status !== "approved").length} detail="needs attention" />
        <Metric label="Approved" value={submissions.filter((item) => item.status === "approved").length} detail="ready for project promotion" />
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4" />
            Submission queue
          </CardTitle>
          <CardDescription>Only requests from your labs are visible here.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {submissions.map((item) => (
            <div key={item.id} className="grid gap-2 rounded-2xl border bg-background/60 p-4 md:grid-cols-[1fr_auto] md:items-center">
              <div>
                <div className="font-semibold">{item.requested_title}</div>
                <div className="text-sm text-muted-foreground">
                  {item.institution_name || item.metadata.institution.name} · {item.sample_count_estimate ?? 0} samples · submitted {formatDate(item.created_at)}
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  Contact: {item.contact_name || "-"} · {item.contact_email || "-"} · Billing: {item.invoice_email || "-"}
                </div>
              </div>
              <div className="flex flex-col items-start gap-2 md:items-end">
                <StatusBadge status={item.status} />
                <Button asChild variant="secondary" size="sm">
                  <Link to={`/submissions/${item.id}`}>Open</Link>
                </Button>
              </div>
            </div>
          ))}
          {!submissions.length ? <div className="rounded-2xl border border-dashed p-6 text-sm text-muted-foreground">No requests yet. Start one from the submission wizard.</div> : null}
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-black uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
        <div className="mt-2 text-3xl font-black">{value}</div>
        <div className="mt-1 text-sm text-muted-foreground">{detail}</div>
      </CardContent>
    </Card>
  );
}
