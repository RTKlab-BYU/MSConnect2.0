import { useMemo } from "react";

import { PlotFrame } from "@/components/viz/plot-frame";
import { UPlotChromatogram } from "@/components/viz/uplot-chromatogram";
import type { RawFile } from "@/lib/api/types";
import { useVizStore } from "@/store/viz-store";
import { demoChromatogramFromRawFile } from "@/features/visualization/demo-chromatogram";

export function ChromatogramPanel({ rawFile }: { rawFile: RawFile | undefined }) {
  const trace = useMemo(() => demoChromatogramFromRawFile(rawFile), [rawFile]);
  const retentionTimeWindow = useVizStore((state) => state.retentionTimeWindow);

  return (
    <PlotFrame
      title="Chromatogram Prototype"
      description="Canvas-rendered uPlot trace with worker downsampling. Production trace metadata should come from the API with signed object-storage URLs for compact binary payloads."
      toolbar={
        <div className="rounded-md border bg-secondary px-2 py-1 text-xs font-semibold text-muted-foreground">
          {retentionTimeWindow
            ? `${retentionTimeWindow.startMinutes}-${retentionTimeWindow.endMinutes} min selected`
            : "Drag across the plot to select RT"}
        </div>
      }
    >
      <UPlotChromatogram trace={trace} />
    </PlotFrame>
  );
}
