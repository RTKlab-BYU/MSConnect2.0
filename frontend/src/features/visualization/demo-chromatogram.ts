import type { RawFile } from "@/lib/api/types";
import type { ChromatogramTrace } from "@/components/viz/uplot-chromatogram";

function numberFromMetadata(rawFile: RawFile | undefined, key: string, fallback: number) {
  if (!rawFile) return fallback;
  const telemetry = rawFile.metadata.lc_ms_telemetry;
  if (!telemetry || typeof telemetry !== "object" || Array.isArray(telemetry)) return fallback;
  const value = (telemetry as Record<string, unknown>)[key];
  return typeof value === "number" ? value : fallback;
}

export function demoChromatogramFromRawFile(rawFile: RawFile | undefined): ChromatogramTrace {
  const points = 120_000;
  const duration = numberFromMetadata(rawFile, "gradient_minutes", 45);
  const tic = rawFile ? numberFromMetadata(rawFile, "tic", 8.5e9) : 8.5e9;
  const seed = rawFile?.id ?? 1;
  const x = new Array<number>(points);
  const y = new Array<number>(points);

  const peaks = [
    { center: 8 + (seed % 5) * 0.4, width: 0.08, scale: 0.2 },
    { center: 17 + (seed % 3) * 0.7, width: 0.16, scale: 0.42 },
    { center: 29 + (seed % 7) * 0.22, width: 0.12, scale: 0.34 },
    { center: 36 + (seed % 4) * 0.31, width: 0.2, scale: 0.28 },
  ];

  for (let index = 0; index < points; index += 1) {
    const rt = (duration * index) / (points - 1);
    const baseline = tic * 0.000002 * (1 + Math.sin(rt * 1.9 + seed) * 0.08);
    const signal = peaks.reduce((sum, peak) => {
      const z = (rt - peak.center) / peak.width;
      return sum + tic * 0.000016 * peak.scale * Math.exp(-0.5 * z * z);
    }, baseline);
    x[index] = Number(rt.toFixed(5));
    y[index] = Math.max(0, signal + Math.sin(index * 0.17) * tic * 0.00000008);
  }

  return {
    label: rawFile?.filename ?? "Demo XIC",
    x,
    y,
  };
}
