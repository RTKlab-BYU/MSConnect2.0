import type { ColumnDef } from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  fetchRawFileChromatograms,
  fetchRawFileDerivatives,
  fetchRawFiles,
  fetchRawFileSpectra,
  fetchRawFileSpectrum,
  queryKeys,
} from "@/lib/api/queries";
import { formatBytes, formatDate } from "@/lib/format";
import type { RawFileDerivative, SpectrumSummary } from "@/lib/api/types";

function linePath(points: Array<[number, number]>, width: number, height: number) {
  const finitePoints = points.filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y) && y >= 0);
  if (!finitePoints.length) return "";
  const xMin = Math.min(...finitePoints.map(([x]) => x));
  const xMax = Math.max(...finitePoints.map(([x]) => x));
  const yMax = Math.max(...finitePoints.map(([, y]) => y), 1);
  return finitePoints
    .map(([x, y], index) => {
      const px = xMax === xMin ? 0 : ((x - xMin) / (xMax - xMin)) * width;
      const py = height - (y / yMax) * height;
      return `${index === 0 ? "M" : "L"}${px.toFixed(1)} ${py.toFixed(1)}`;
    })
    .join(" ");
}

function PeakPlot({ peaks }: { peaks: Array<[number, number]> }) {
  const finitePeaks = peaks.filter(([mz, intensity]) => Number.isFinite(mz) && Number.isFinite(intensity) && intensity >= 0);
  const width = 760;
  const height = 220;
  const mzMin = finitePeaks.length ? Math.min(...finitePeaks.map(([mz]) => mz)) : 0;
  const mzMax = finitePeaks.length ? Math.max(...finitePeaks.map(([mz]) => mz)) : 1;
  const intensityMax = Math.max(...finitePeaks.map(([, intensity]) => intensity), 1);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full rounded-md border bg-background">
      {finitePeaks.map(([mz, intensity]) => {
        const x = mzMax === mzMin ? width / 2 : ((mz - mzMin) / (mzMax - mzMin)) * width;
        const y = height - (intensity / intensityMax) * (height - 18);
        return <line key={`${mz}-${intensity}`} x1={x} x2={x} y1={height} y2={y} className="stroke-primary" strokeWidth="1.5" />;
      })}
      {!finitePeaks.length ? (
        <text x={width / 2} y={height / 2} textAnchor="middle" className="fill-muted-foreground text-sm">
          No centroid peaks available for this scan
        </text>
      ) : null}
    </svg>
  );
}

export default function SpectraPage() {
  const [searchParams] = useSearchParams();
  const requestedRawFileId = searchParams.get("rawFile") ?? "";
  const [rawFileId, setRawFileId] = useState(requestedRawFileId);
  const [selectedSpectrumId, setSelectedSpectrumId] = useState("");
  const rawFilesQuery = useQuery({
    queryKey: queryKeys.rawFiles({ page_size: 200 }),
    queryFn: () => fetchRawFiles({ page_size: 200 }),
  });
  const selectedId = Number(rawFileId || 0);
  const derivativesQuery = useQuery({
    queryKey: queryKeys.rawFileDerivatives({ raw_file: selectedId || "" }),
    queryFn: () => fetchRawFileDerivatives({ raw_file: selectedId }),
    enabled: Boolean(selectedId),
  });
  const spectraQuery = useQuery({
    queryKey: queryKeys.rawFileSpectra(selectedId, { limit: 500 }),
    queryFn: () => fetchRawFileSpectra(selectedId, { limit: 500 }),
    enabled: Boolean(selectedId),
  });
  const chromatogramsQuery = useQuery({
    queryKey: queryKeys.rawFileChromatograms(selectedId),
    queryFn: () => fetchRawFileChromatograms(selectedId),
    enabled: Boolean(selectedId),
  });
  const spectrumQuery = useQuery({
    queryKey: queryKeys.rawFileSpectrum(selectedId, selectedSpectrumId),
    queryFn: () => fetchRawFileSpectrum(selectedId, selectedSpectrumId),
    enabled: Boolean(selectedId && selectedSpectrumId),
  });

  const derivativeColumns: ColumnDef<RawFileDerivative>[] = [
    { accessorKey: "derivative_type", header: "Type" },
    { accessorKey: "format", header: "Format" },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    {
      accessorKey: "size_bytes",
      header: "Size",
      cell: ({ row }) => (row.original.size_bytes ? formatBytes(row.original.size_bytes) : "-"),
    },
    {
      accessorKey: "updated_at",
      header: "Updated",
      cell: ({ row }) => formatDate(row.original.updated_at),
    },
  ];
  const spectrumColumns: ColumnDef<SpectrumSummary>[] = [
    {
      accessorKey: "id",
      header: "Spectrum",
      cell: ({ row }) => (
        <Button variant="ghost" className="h-8 px-2" onClick={() => setSelectedSpectrumId(row.original.id)}>
          {row.original.id || row.original.scan_number}
        </Button>
      ),
    },
    { accessorKey: "ms_level", header: "MS" },
    { accessorKey: "retention_time_seconds", header: "RT sec" },
    { accessorKey: "precursor_mz", header: "Precursor" },
    { accessorKey: "base_peak_mz", header: "Base m/z" },
    { accessorKey: "tic", header: "TIC" },
  ];

  const chromatogramPath = useMemo(() => {
    const tic = chromatogramsQuery.data?.chromatograms.tic ?? [];
    return linePath(tic, 760, 160);
  }, [chromatogramsQuery.data]);
  const peaks = spectrumQuery.data?.spectrum.peaks ?? [];

  useEffect(() => {
    if (requestedRawFileId && requestedRawFileId !== rawFileId) {
      setRawFileId(requestedRawFileId);
      setSelectedSpectrumId("");
      return;
    }
    if (!rawFileId && rawFilesQuery.data?.results?.length) {
      const withDerivatives = rawFilesQuery.data.results.find((item) => item.status === "processed");
      setRawFileId(String((withDerivatives ?? rawFilesQuery.data.results[0]).id));
    }
  }, [rawFileId, rawFilesQuery.data, requestedRawFileId]);

  useEffect(() => {
    if (!selectedSpectrumId && spectraQuery.data?.spectra?.length) {
      setSelectedSpectrumId(spectraQuery.data.spectra[0].id);
    }
  }, [selectedSpectrumId, spectraQuery.data]);

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Spectra" }]} />
      <PageHero
        eyebrow="mzML preview"
        title="Spectra"
        description="Inspect converted spectra derivatives, chromatogram previews, and scan-level peaks from indexed raw files."
        actions={
          <>
            <StatusBadge status={spectraQuery.data?.index_derivative ? "ready" : "queued"} />
            <StatusBadge status="mzML" />
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Raw file</CardTitle>
          <CardDescription>Select an imported file with a ready spectrum index derivative.</CardDescription>
        </CardHeader>
        <CardContent>
          <Select value={rawFileId} onValueChange={(value) => { setRawFileId(value); setSelectedSpectrumId(""); }}>
            <SelectTrigger>
              <SelectValue placeholder="Choose raw file" />
            </SelectTrigger>
            <SelectContent>
              {(rawFilesQuery.data?.results ?? []).map((item) => (
                <SelectItem key={item.id} value={String(item.id)}>
                  {item.filename}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Chromatogram
            </CardTitle>
            <CardDescription>TIC preview from the selected spectrum index.</CardDescription>
          </CardHeader>
          <CardContent>
            <svg viewBox="0 0 760 160" className="h-44 w-full rounded-md border bg-background">
              <path d={chromatogramPath} fill="none" className="stroke-primary" strokeWidth="2" />
            </svg>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Derivatives</CardTitle>
            <CardDescription>Converted and indexed files registered for this raw file.</CardDescription>
          </CardHeader>
          <CardContent>
            <DataTable columns={derivativeColumns} data={derivativesQuery.data?.results ?? []} estimateSize={42} emptyLabel="No derivatives registered." />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Scan list</CardTitle>
          <CardDescription>{spectraQuery.data ? `${spectraQuery.data.count} indexed spectra available.` : "No raw file selected."}</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable columns={spectrumColumns} data={spectraQuery.data?.spectra ?? []} estimateSize={42} emptyLabel="No spectra in the current index." />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Spectrum detail
          </CardTitle>
          <CardDescription>{selectedSpectrumId || "Select a scan to plot centroid peaks."}</CardDescription>
        </CardHeader>
        <CardContent>
          <PeakPlot peaks={peaks} />
        </CardContent>
      </Card>
    </div>
  );
}
