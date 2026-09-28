import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { PlotFrame } from "@/components/viz/plot-frame";
import { UPlotChromatogram } from "@/components/viz/uplot-chromatogram";
import type { RawFile } from "@/lib/api/types";
import { fetchRawFileChromatograms, queryKeys } from "@/lib/api/queries";
import { useVizStore } from "@/store/viz-store";

export function ChromatogramPanel({ rawFile }: { rawFile: RawFile | undefined }) {
  const chromatogramsQuery = useQuery({
    queryKey: queryKeys.rawFileChromatograms(rawFile?.id ?? 0),
    queryFn: () => fetchRawFileChromatograms(rawFile!.id),
    enabled: Boolean(rawFile?.id),
    refetchInterval: 30_000,
  });
  const trace = useMemo(() => {
    const tic = chromatogramsQuery.data?.chromatograms.tic ?? [];
    return {
      label: rawFile?.filename ?? "TIC",
      x: tic.map(([retentionTimeSeconds]) => retentionTimeSeconds / 60),
      y: tic.map(([, intensity]) => intensity),
    };
  }, [chromatogramsQuery.data, rawFile?.filename]);
  const retentionTimeWindow = useVizStore((state) => state.retentionTimeWindow);

  return (
    <PlotFrame
      title="Live TIC"
      description="Indexed total-ion chromatogram from the selected raw file. Refreshes while acquisition processing updates the index."
      toolbar={
        <div className="rounded-md border bg-secondary px-2 py-1 text-xs font-semibold text-muted-foreground">
          {retentionTimeWindow
            ? `${retentionTimeWindow.startMinutes}-${retentionTimeWindow.endMinutes} min selected`
            : "Drag across the plot to select RT"}
        </div>
      }
    >
      {chromatogramsQuery.isLoading ? (
        <div className="flex min-h-[320px] items-center justify-center text-sm text-muted-foreground">Loading chromatogram…</div>
      ) : chromatogramsQuery.isError ? (
        <div className="flex min-h-[320px] items-center justify-center text-sm text-destructive">Chromatogram unavailable for this file.</div>
      ) : trace.x.length ? (
        <UPlotChromatogram trace={trace} />
      ) : (
        <div className="flex min-h-[320px] items-center justify-center text-sm text-muted-foreground">
          No indexed chromatogram is available yet. The watcher and processor will populate it after conversion.
        </div>
      )}
    </PlotFrame>
  );
}
