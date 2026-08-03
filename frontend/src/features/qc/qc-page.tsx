import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { MetricCard, PageHero } from "@/components/layout/page-section";
import { MachineTrendChart } from "@/components/data/machine-trend-chart";
import { SummaryChart } from "@/components/data/summary-chart";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  fetchAcquisitions,
  fetchProjects,
  fetchQcDetails,
  fetchQcOverview,
  queryKeys,
} from "@/lib/api/queries";
import { formatDate } from "@/lib/format";

export default function QcPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const program = searchParams.get("program") === "prtc" ? "prtc" : "hye";
  const project = searchParams.get("project") ?? "all";
  const worklist = searchParams.get("worklist") ?? "all";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    if (key === "project") {
      next.delete("worklist");
    }
    setSearchParams(next, { replace: true });
  }

  const qcParams = {
    program,
    project: project === "all" ? "" : project,
    worklist: worklist === "all" ? "" : worklist,
  };

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects({ page_size: 200 }),
    queryFn: () => fetchProjects({ page_size: 200 }),
  });
  const worklistsQuery = useQuery({
    queryKey: queryKeys.acquisitions({ page_size: 200, project: project === "all" ? "" : project }),
    queryFn: () => fetchAcquisitions({ page_size: 200, project: project === "all" ? "" : project }),
  });
  const overviewQuery = useQuery({
    queryKey: queryKeys.qcOverview(qcParams),
    queryFn: () => fetchQcOverview(qcParams),
  });
  const detailsQuery = useQuery({
    queryKey: queryKeys.qcDetails(qcParams),
    queryFn: () => fetchQcDetails(qcParams),
  });

  const overview = overviewQuery.data;
  const details = detailsQuery.data;
  const pairStatusData = (overview?.pair_status_counts ?? []).map((row) => ({ label: row.status, count: row.count }));
  const prtcRuns = details?.runs ?? [];
  const machineSummaries = details?.machine_summaries ?? [];
  const machineSeries = details?.machine_series ?? [];
  const passThreshold = details ? Math.round(details.thresholds.pass_relative_error * 100) : 20;
  const warningThreshold = details ? Math.round(details.thresholds.warning_relative_error * 100) : 50;

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "QC" }]} />

      <PageHero
        eyebrow="Assay health"
        title="QC"
        description="Review embedded HYE controls as pseudo-project reporting while keeping room for future PRTC standards."
        actions={
          <>
            <StatusBadge status="qc" />
            <StatusBadge status={program === "hye" ? "pass" : "warning"} />
          </>
        }
      />

      <Tabs value={program} onValueChange={(value) => updateParam("program", value)}>
        <TabsList>
          <TabsTrigger value="hye">HYE</TabsTrigger>
          <TabsTrigger value="prtc">PRTC</TabsTrigger>
        </TabsList>

        <Card>
          <CardHeader>
            <CardTitle>QC filters</CardTitle>
            <CardDescription>Scope HYE pseudo-project reporting by project or acquisition worklist.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <Select value={project} onValueChange={(value) => updateParam("project", value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Project" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All projects</SelectItem>
                  {(projectsQuery.data?.results ?? []).map((item) => (
                    <SelectItem key={item.id} value={String(item.id)}>
                      {item.code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={worklist} onValueChange={(value) => updateParam("worklist", value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Worklist" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All worklists</SelectItem>
                  {(worklistsQuery.data?.results ?? []).map((item) => (
                    <SelectItem key={item.id} value={String(item.id)}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="rounded-2xl border bg-secondary/35 px-4 py-3 text-sm text-muted-foreground">
                Pair pass threshold: within {passThreshold}% of ideal B/A. Warning up to {warningThreshold}%.
              </div>
            </div>
          </CardContent>
        </Card>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard label="QC Injections" value={overview?.qc_injection_count ?? "-"} detail="control runs in scope" />
          <MetricCard label="Complete Pairs" value={overview?.complete_pair_count ?? "-"} detail="A/B pairs with quant output" />
          <MetricCard label="Out of Spec" value={overview?.out_of_spec_pair_count ?? "-"} detail="warning or failed pairs" />
          <MetricCard label="Missing Raw" value={overview?.missing_raw_file_count ?? "-"} detail="expected QC files not uploaded" />
          <MetricCard label="Latest Complete" value={formatDate(overview?.latest_completed_at)} detail="most recent finished pair" />
        </section>

        <TabsContent value="hye" className="grid gap-4">
          <section className="grid gap-4 xl:grid-cols-[1fr_360px]">
            <Card>
              <CardHeader>
                <CardTitle>Expected HYE composition</CardTitle>
                <CardDescription>Human remains constant while Yeast and E. coli shift between A and B.</CardDescription>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="border-b py-2">Organism</th>
                      <th className="border-b py-2">A</th>
                      <th className="border-b py-2">B</th>
                      <th className="border-b py-2">Ideal B/A</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b">
                      <td className="py-2 font-medium">Homo sapiens</td>
                      <td className="py-2">0.65</td>
                      <td className="py-2">0.65</td>
                      <td className="py-2">1.00</td>
                    </tr>
                    <tr className="border-b">
                      <td className="py-2 font-medium">Saccharomyces cerevisiae</td>
                      <td className="py-2">0.30</td>
                      <td className="py-2">0.15</td>
                      <td className="py-2">0.50</td>
                    </tr>
                    <tr>
                      <td className="py-2 font-medium">Escherichia coli</td>
                      <td className="py-2">0.05</td>
                      <td className="py-2">0.20</td>
                      <td className="py-2">4.00</td>
                    </tr>
                  </tbody>
                </table>
              </CardContent>
            </Card>

            <SummaryChart title="Pair Status" data={pairStatusData} />
          </section>

          {machineSummaries.length ? (
            <section className="grid gap-4">
              {machineSummaries.map((machine) => (
                <MachineTrendChart
                  key={machine.machine_key}
                  title={machine.machine_label}
                  description={`Pairs: ${machine.pair_count} · complete: ${machine.complete_pair_count} · latest: ${formatDate(machine.latest_completed_at)}`}
                  data={machineSeries.filter((point) => point.machine_key === machine.machine_key)}
                />
              ))}
            </section>
          ) : null}

          {details?.pairs.length ? (
            details.pairs.map((pair) => (
              <Card key={`${pair.worklist_id}-${pair.pair_label}`}>
                <CardHeader>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-xs font-bold uppercase text-muted-foreground">{pair.worklist_name}</div>
                      <CardTitle className="mt-1">{pair.pair_label}</CardTitle>
                      <CardDescription className="mt-2">
                        <span className="font-medium">A:</span> {pair.a_filename || pair.a_run_name || "Missing"}{" "}
                        <span className="ml-3 font-medium">B:</span> {pair.b_filename || pair.b_run_name || "Missing"}
                      </CardDescription>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={pair.status} />
                      <StatusBadge status={pair.machine_key === "unassigned" ? "warning" : "complete"} />
                      <Button asChild variant="secondary" size="sm">
                        <Link to={`/projects/${pair.project_id}`}>{pair.project_code}</Link>
                      </Button>
                      <Button asChild variant="secondary" size="sm">
                        <Link to={`/qc/hye/${pair.worklist_id}/${encodeURIComponent(pair.pair_label)}`}>Pair record</Link>
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-3">
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="rounded-2xl border bg-secondary/20 px-3 py-2 text-sm">
                      <div className="text-xs font-bold uppercase text-muted-foreground">Shared Proteins</div>
                      <div className="mt-1 text-lg font-semibold">{pair.shared_total_n}</div>
                    </div>
                    <div className="rounded-2xl border bg-secondary/20 px-3 py-2 text-sm">
                      <div className="text-xs font-bold uppercase text-muted-foreground">Completed</div>
                      <div className="mt-1 text-lg font-semibold">{formatDate(pair.completed_at)}</div>
                    </div>
                    <div className="rounded-2xl border bg-secondary/20 px-3 py-2 text-sm">
                      <div className="text-xs font-bold uppercase text-muted-foreground">Project</div>
                      <div className="mt-1 text-lg font-semibold">{pair.project_code}</div>
                    </div>
                    <div className="rounded-2xl border bg-secondary/20 px-3 py-2 text-sm">
                      <div className="text-xs font-bold uppercase text-muted-foreground">Machine</div>
                      <div className="mt-1 text-lg font-semibold">{pair.machine_label}</div>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[840px] text-sm">
                      <thead className="text-left text-xs uppercase text-muted-foreground">
                        <tr>
                          <th className="border-b px-2 py-2">Organism</th>
                          <th className="border-b px-2 py-2">Status</th>
                          <th className="border-b px-2 py-2">Shared N</th>
                          <th className="border-b px-2 py-2">Median log2 A</th>
                          <th className="border-b px-2 py-2">Median log2 B</th>
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
                            <td className="px-2 py-2">{organism.median_log2_a ?? "-"}</td>
                            <td className="px-2 py-2">{organism.median_log2_b ?? "-"}</td>
                            <td className="px-2 py-2">{organism.observed_ratio ?? "-"}</td>
                            <td className="px-2 py-2">{organism.ideal_ratio}</td>
                            <td className="px-2 py-2">
                              {organism.relative_error === null ? "-" : `${Math.round(organism.relative_error * 100)}%`}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <Card className="border-dashed">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base">Pair score</CardTitle>
                        <CardDescription>Levy-Jennings input for the selected HYE pair.</CardDescription>
                      </CardHeader>
                      <CardContent className="grid gap-2 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-muted-foreground">Mean relative error</span>
                          <span className="font-semibold">{pair.score === null ? "-" : pair.score.toFixed(4)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-muted-foreground">Worst relative error</span>
                          <span className="font-semibold">{pair.worst_relative_error === null ? "-" : pair.worst_relative_error.toFixed(4)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-muted-foreground">Machine key</span>
                          <span className="font-mono text-xs">{pair.machine_key}</span>
                        </div>
                      </CardContent>
                    </Card>
                    <Card className="border-dashed">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base">Machine routing</CardTitle>
                        <CardDescription>Run A and Run B can share or differ in machine identity.</CardDescription>
                      </CardHeader>
                      <CardContent className="grid gap-2 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-muted-foreground">A machine</span>
                          <span className="font-semibold">{pair.a_machine_label}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-muted-foreground">B machine</span>
                          <span className="font-semibold">{pair.b_machine_label}</span>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </CardContent>
              </Card>
            ))
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>No HYE QC pseudo-project</CardTitle>
                <CardDescription>{details?.empty_message || "Loading HYE QC metrics..."}</CardDescription>
              </CardHeader>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="prtc" className="grid gap-4">
          <Card>
            <CardHeader>
              <CardTitle>PRTC standards</CardTitle>
              <CardDescription>
                Skyline PRTC monitoring for the configured 15-peptide standard set.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl border bg-secondary/20 px-3 py-3">
                  <div className="text-xs font-bold uppercase text-muted-foreground">Completed PRTC</div>
                  <div className="mt-2 text-xl font-bold">{prtcRuns.length}</div>
                  <div className="mt-1 text-sm text-muted-foreground">Skyline jobs with saved stats</div>
                </div>
                <div className="rounded-2xl border bg-secondary/20 px-3 py-3">
                  <div className="text-xs font-bold uppercase text-muted-foreground">Detected Peptides</div>
                  <div className="mt-2 text-xl font-bold">
                    {prtcRuns[0] ? `${prtcRuns[0].detected_peptide_count}/${prtcRuns[0].expected_peptide_count}` : "-"}
                  </div>
                  <div className="mt-1 text-sm text-muted-foreground">latest completed injection</div>
                </div>
                <div className="rounded-2xl border bg-secondary/20 px-3 py-3">
                  <div className="text-xs font-bold uppercase text-muted-foreground">Max RT Shift</div>
                  <div className="mt-2 text-xl font-bold">{formatMetric(prtcRuns[0]?.max_abs_rt_shift_seconds, "s")}</div>
                  <div className="mt-1 text-sm text-muted-foreground">latest completed injection</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {prtcRuns.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Skyline PRTC runs</CardTitle>
                <CardDescription>Per-upload Skyline report stats saved by processor jobs.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[980px] text-sm">
                    <thead className="text-left text-xs uppercase text-muted-foreground">
                      <tr>
                        <th className="border-b px-2 py-2">Run</th>
                        <th className="border-b px-2 py-2">Status</th>
                        <th className="border-b px-2 py-2">Peptides</th>
                        <th className="border-b px-2 py-2">Total Area</th>
                        <th className="border-b px-2 py-2">Mean RT Shift</th>
                        <th className="border-b px-2 py-2">Max RT Shift</th>
                        <th className="border-b px-2 py-2">Missing</th>
                        <th className="border-b px-2 py-2">Completed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prtcRuns.map((run) => (
                        <tr key={run.job_id} className="border-b last:border-b-0">
                          <td className="px-2 py-2">
                            <div className="font-medium">{run.run_name || run.filename}</div>
                            <div className="text-xs text-muted-foreground">{run.filename}</div>
                          </td>
                          <td className="px-2 py-2">
                            <StatusBadge status={run.status === "fail" ? "failed" : run.status} />
                          </td>
                          <td className="px-2 py-2">
                            {run.detected_peptide_count}/{run.expected_peptide_count}
                          </td>
                          <td className="px-2 py-2">{formatMetric(run.total_area)}</td>
                          <td className="px-2 py-2">{formatMetric(run.mean_rt_shift_seconds, "s")}</td>
                          <td className="px-2 py-2">{formatMetric(run.max_abs_rt_shift_seconds, "s")}</td>
                          <td className="px-2 py-2">
                            {[...run.missing_peptides, ...run.out_of_tolerance_peptides].join(", ") || "-"}
                          </td>
                          <td className="px-2 py-2">{formatDate(run.finished_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>No PRTC Skyline results</CardTitle>
                <CardDescription>
                  {overview?.empty_message || "PRTC metrics will appear after PRTC uploads are processed by Skyline."}
                </CardDescription>
              </CardHeader>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function formatMetric(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) {
    return "-";
  }
  const formatted = Math.abs(value) >= 1000 ? value.toExponential(2) : value.toFixed(2);
  return suffix ? `${formatted} ${suffix}` : formatted;
}
