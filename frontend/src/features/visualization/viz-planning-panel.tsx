import { useMemo, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";

function RangeField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="grid gap-2 text-sm font-semibold">
      <span className="flex justify-between gap-2">
        {label}
        <span className="font-mono text-muted-foreground">{value.toLocaleString()}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-primary"
      />
    </label>
  );
}

function traceRecommendation(points: number, overlays: number) {
  if (points < 50_000 && overlays <= 6) return "uPlot canvas, no pre-decimation required";
  if (points <= 1_000_000 && overlays <= 12) return "server or worker min/max decimation before uPlot";
  return "server-side LOD plus WebGL renderer evaluation";
}

function matrixRecommendation(cells: number, features: number) {
  const values = cells * features;
  if (values <= 2_000_000) return "Canvas heatmap with tiled rendering";
  if (values <= 25_000_000) return "WebGL heatmap with feature/cell windowing";
  return "Server-tiled matrix pyramid with WebGL viewport rendering";
}

function scatterRecommendation(cells: number) {
  if (cells <= 25_000) return "Canvas scatter is acceptable";
  if (cells <= 250_000) return "WebGL point layer with brushing";
  return "WebGL with spatial index, progressive loading, and server-side bins";
}

export function VizPlanningPanel() {
  const [tracePoints, setTracePoints] = useState(50_000);
  const [overlays, setOverlays] = useState(4);
  const [cells, setCells] = useState(10_000);
  const [features, setFeatures] = useState(2_000);

  const recommendations = useMemo(
    () => ({
      trace: traceRecommendation(tracePoints, overlays),
      matrix: matrixRecommendation(cells, features),
      scatter: scatterRecommendation(cells),
    }),
    [cells, features, overlays, tracePoints],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Renderer Planning Inputs</CardTitle>
        <CardDescription>
          Typical 45-minute LC-MS XIC traces are often about 2,700-13,500 points at 1-5 Hz MS1 sampling.
          Profile spectra and extracted traces with many overlays can be much larger, so renderer choice is dynamic.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="grid gap-4 lg:grid-cols-2">
          <RangeField label="Points per chromatogram trace" value={tracePoints} min={5_000} max={1_500_000} step={5_000} onChange={setTracePoints} />
          <RangeField label="Overlaid traces" value={overlays} min={1} max={64} step={1} onChange={setOverlays} />
          <RangeField label="Cells / scatter points" value={cells} min={1_000} max={500_000} step={1_000} onChange={setCells} />
          <RangeField label="Heatmap features" value={features} min={100} max={25_000} step={100} onChange={setFeatures} />
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <div className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold">XIC / Spectra</span>
              <StatusBadge status={tracePoints < 50_000 ? "ready" : "assigned"} />
            </div>
            <p className="text-sm text-muted-foreground">{recommendations.trace}</p>
          </div>
          <div className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold">UMAP / PCA</span>
              <StatusBadge status={cells <= 25_000 ? "ready" : "assigned"} />
            </div>
            <p className="text-sm text-muted-foreground">{recommendations.scatter}</p>
          </div>
          <div className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold">Heatmap</span>
              <StatusBadge status={cells * features <= 2_000_000 ? "ready" : "assigned"} />
            </div>
            <p className="text-sm text-muted-foreground">{recommendations.matrix}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
