import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type SummaryDatum = {
  label: string;
  count: number;
};

export function SummaryChart({ title, data }: { title: string; data: SummaryDatum[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ left: -24, right: 8, top: 8, bottom: 0 }}>
            <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
            <Tooltip cursor={{ fill: "hsl(var(--secondary))" }} />
            <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
