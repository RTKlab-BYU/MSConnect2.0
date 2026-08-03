import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Microscope } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { MachineTrendChart } from "@/components/data/machine-trend-chart";
import { MetricCard, PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { fetchQcDetails, queryKeys } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { RouteFallback } from "@/components/shell/route-fallback";

export default function HyePairPage() {
  const params = useParams();
  const worklistId = Number(params.worklistId);
  const pairLabel = params.pairLabel ?? "";

  const detailsQuery = useQuery({
    queryKey: queryKeys.qcDetails({ program: "hye", worklist: String(worklistId) }),
    queryFn: () => fetchQcDetails({ program: "hye", worklist: String(worklistId) }),
    enabled: Number.isFinite(worklistId),
  });

  if (detailsQuery.isLoading) {
    return <RouteFallback label="Loading HYE pair" />;
  }

  const pair = detailsQuery.data?.pairs.find((item) => item.pair_label === pairLabel);
  if (!pair) {
    return (
      <div className="grid gap-4">
        <Breadcrumbs items={[{ label: "QC", href: "/qc" }, { label: "HYE pair" }]} />
        <Card>
          <CardHeader>
            <CardTitle>HYE pair not found</CardTitle>
            <CardDescription>The selected pair is not available in the current QC scope.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="secondary">
              <Link to="/qc">
                <ArrowLeft className="h-4 w-4" />
                Back to QC
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const machineSeries = (detailsQuery.data?.machine_series ?? []).filter((point) => point.machine_key === pair.machine_key);
  const machineSummary = (detailsQuery.data?.machine_summaries ?? []).find((item) => item.machine_key === pair.machine_key);
  const machinePairCount = machineSummary?.pair_count ?? machineSeries.length;
  const machineMeanScore = machineSummary?.mean_score;
  const machineBands =
    machineSummary?.lower_band === null || machineSummary?.upper_band === null || machineSummary?.lower_band === undefined || machineSummary?.upper_band === undefined
      ? "-"
      : `${machineSummary.lower_band.toFixed(4)} to ${machineSummary.upper_band.toFixed(4)}`;

  return (
    <div className="grid gap-4">
      <Breadcrumbs
        items={[
          { label: "QC", href: "/qc" },
          { label: pair.worklist_name, href: `/qc?worklist=${pair.worklist_id}&program=hye` },
          { label: pair.pair_label },
        ]}
      />

      <PageHero
        eyebrow="HYE record"
        title={pair.pair_label}
        description={`Pair stats for ${pair.worklist_name} on ${pair.machine_label}.`}
        actions={
          <Button asChild variant="secondary">
            <Link to={`/qc?worklist=${pair.worklist_id}&program=hye`}>
              <ArrowLeft className="h-4 w-4" />
              Back to QC
            </Link>
          </Button>
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Status" value={pair.status} detail={pair.machine_label} />
        <MetricCard label="Score" value={pair.score === null ? "-" : pair.score.toFixed(4)} detail="mean relative error" />
        <MetricCard label="Worst" value={pair.worst_relative_error === null ? "-" : pair.worst_relative_error.toFixed(4)} detail="worst organism error" />
        <MetricCard label="Completed" value={formatDate(pair.completed_at)} detail={`Project ${pair.project_code}`} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <MachineTrendChart
          title={machineSummary?.machine_label ?? pair.machine_label}
          description={`Run history for this machine across ${machinePairCount} HYE pairs.`}
          data={machineSeries}
        />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Microscope className="h-4 w-4" />
              Machine context
            </CardTitle>
            <CardDescription>Instrument metadata carried with the run and pair.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <InfoRow label="Machine" value={pair.machine_label} />
            <InfoRow label="Machine key" value={pair.machine_key} />
            <InfoRow label="A machine" value={pair.a_machine_label} />
            <InfoRow label="B machine" value={pair.b_machine_label} />
            <InfoRow label="Pair count" value={String(machinePairCount)} />
            <InfoRow label="Mean score" value={machineMeanScore === null || machineMeanScore === undefined ? "-" : machineMeanScore.toFixed(4)} />
            <InfoRow label="Bands" value={machineBands} />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Organism stats</CardTitle>
          <CardDescription>Observed A/B ratios and relative error for this pair.</CardDescription>
        </CardHeader>
        <CardContent>
          <table className="w-full min-w-[840px] text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="border-b px-2 py-2">Organism</th>
                <th className="border-b px-2 py-2">Status</th>
                <th className="border-b px-2 py-2">Shared N</th>
                <th className="border-b px-2 py-2">Observed B/A</th>
                <th className="border-b px-2 py-2">Ideal B/A</th>
                <th className="border-b px-2 py-2">Relative Error</th>
              </tr>
            </thead>
            <tbody>
              {pair.organisms.map((organism) => (
                <tr key={organism.organism} className="border-b last:border-b-0">
                  <td className="px-2 py-2 font-medium">{organism.organism}</td>
                  <td className="px-2 py-2">
                    <StatusBadge status={organism.status} />
                  </td>
                  <td className="px-2 py-2">{organism.shared_n}</td>
                  <td className="px-2 py-2">{organism.observed_ratio ?? "-"}</td>
                  <td className="px-2 py-2">{organism.ideal_ratio}</td>
                  <td className="px-2 py-2">
                    {organism.relative_error === null ? "-" : `${Math.round(organism.relative_error * 100)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-2xl border bg-background/50 px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-semibold">{value}</span>
    </div>
  );
}
