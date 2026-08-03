import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Files } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { RouteFallback } from "@/components/shell/route-fallback";
import { fetchIntakeRequest, queryKeys } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";

export default function SubmissionDetailPage() {
  const params = useParams();
  const requestId = Number(params.submissionId);
  const intakeQuery = useQuery({
    queryKey: queryKeys.intakeRequests({ id: requestId }),
    queryFn: () => fetchIntakeRequest(requestId),
    enabled: Number.isFinite(requestId),
  });
  const intake = intakeQuery.data;

  if (intakeQuery.isLoading || !intake) {
    return <RouteFallback label="Loading submission" />;
  }

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Submissions", href: "/submissions" }, { label: intake.requested_title }]} />
      <PageHero
        eyebrow="Submission detail"
        title={intake.requested_title}
        description="Review the intake payload, status, and request metadata."
        actions={
          <Button asChild variant="secondary">
            <Link to="/submissions">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
          </Button>
        }
      />

      <section className="grid gap-3 md:grid-cols-3">
        <Metric label="Status" value={<StatusBadge status={intake.status} />} detail={`Submitted ${formatDate(intake.created_at)}`} />
        <Metric label="Samples" value={String(intake.sample_count_estimate ?? 0)} detail={intake.matrix || "No matrix"} />
        <Metric label="Invoice" value={intake.invoice_email || "-"} detail={intake.contact_email || "-"} />
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Files className="h-4 w-4" />
            Intake payload
          </CardTitle>
          <CardDescription>All structured fields are preserved in the metadata JSON for auditability.</CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-auto rounded-2xl border bg-background/80 p-4 text-xs">{JSON.stringify(intake.metadata, null, 2)}</pre>
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: ReactNode; detail: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-black uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
        <div className="mt-2 text-lg font-bold">{value}</div>
        <div className="mt-1 text-sm text-muted-foreground">{detail}</div>
      </CardContent>
    </Card>
  );
}
