import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export type MachineTrendPoint = {
  completed_at: string | null;
  pair_label: string;
  score: number | null;
  mean_score: number | null;
  lower_band: number | null;
  upper_band: number | null;
  [key: string]: string | number | null | undefined;
};

export function MachineTrendChart({
  title,
  description,
  data,
  metric = "score",
  metricLabel = "Health score",
}: {
  title: string;
  description?: string;
  data: MachineTrendPoint[];
  metric?: string;
  metricLabel?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="h-72">
        {data.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ left: -18, right: 12, top: 8, bottom: 0 }}>
              <XAxis dataKey="pair_label" tickLine={false} axisLine={false} fontSize={12} />
              <YAxis tickLine={false} axisLine={false} fontSize={12} />
              <Tooltip
                cursor={{ stroke: "hsl(var(--border))" }}
                formatter={(value) => (typeof value === "number" ? value.toFixed(4) : String(value ?? "-"))}
                labelFormatter={(label) => String(label)}
              />
              <Line name={metricLabel} type="monotone" dataKey={metric} stroke="hsl(var(--primary))" strokeWidth={2.5} dot={{ r: 3 }} />
              {metric === "score" ? <>
                <Line type="monotone" dataKey="mean_score" stroke="hsl(var(--info))" strokeWidth={1.8} dot={false} />
                <Line type="monotone" dataKey="upper_band" stroke="hsl(var(--warning))" strokeWidth={1.2} dot={false} strokeDasharray="4 4" />
                <Line type="monotone" dataKey="lower_band" stroke="hsl(var(--warning))" strokeWidth={1.2} dot={false} strokeDasharray="4 4" />
              </> : null}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center rounded-2xl border border-dashed text-sm text-muted-foreground">
            No machine trend data yet.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
