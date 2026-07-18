import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import { useDownsampledTrace, type TraceData } from "@/components/viz/use-downsampled-trace";
import { useVizStore } from "@/store/viz-store";

export type ChromatogramTrace = TraceData & {
  label: string;
  color?: string;
};

type UPlotChromatogramProps = {
  trace: ChromatogramTrace;
  height?: number;
};

export function UPlotChromatogram({ trace, height = 320 }: UPlotChromatogramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  const setRetentionTimeWindow = useVizStore((state) => state.setRetentionTimeWindow);
  const downsampled = useDownsampledTrace(trace);
  const data = useMemo(() => [downsampled.x, downsampled.y] as uPlot.AlignedData, [downsampled.x, downsampled.y]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const options: uPlot.Options = {
      width: container.clientWidth || 800,
      height,
      cursor: {
        drag: {
          setScale: false,
          x: true,
          y: false,
        },
      },
      hooks: {
        setSelect: [
          (plot) => {
            if (plot.select.width <= 2) {
              setRetentionTimeWindow(null);
              return;
            }
            const startMinutes = plot.posToVal(plot.select.left, "x");
            const endMinutes = plot.posToVal(plot.select.left + plot.select.width, "x");
            setRetentionTimeWindow({
              startMinutes: Number(Math.min(startMinutes, endMinutes).toFixed(3)),
              endMinutes: Number(Math.max(startMinutes, endMinutes).toFixed(3)),
            });
          },
        ],
      },
      scales: {
        x: { time: false },
      },
      axes: [
        { label: "Retention time (min)" },
        { label: "Intensity", size: 72 },
      ],
      series: [
        {},
        {
          label: trace.label,
          stroke: trace.color ?? "hsl(var(--primary))",
          width: 1,
        },
      ],
    };

    const plot = new uPlot(options, data, container);
    plotRef.current = plot;

    const resize = () => plot.setSize({ width: container.clientWidth || 800, height });
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    return () => {
      observer.disconnect();
      plot.destroy();
      plotRef.current = null;
    };
  }, [data, height, setRetentionTimeWindow, trace.color, trace.label]);

  useEffect(() => {
    plotRef.current?.setData(data);
  }, [data]);

  return <div ref={containerRef} className="min-h-[320px] w-full" />;
}
