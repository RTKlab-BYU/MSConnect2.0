import type { ColumnDef } from "@tanstack/react-table";
import { Link } from "react-router-dom";

import { StatusBadge } from "@/components/ui/status-badge";
import { formatBytes, formatDate } from "@/lib/format";
import type { AcquisitionWorklist, ProcessingJob, Project, RawFile, Run, Sample } from "@/lib/api/types";

export const projectColumns: ColumnDef<Project>[] = [
  {
    accessorKey: "code",
    header: "Project",
    cell: ({ row }) => (
      <Link className="font-semibold" to={`/projects/${row.original.id}`}>
        {row.original.code}
      </Link>
    ),
  },
  { accessorKey: "title", header: "Title" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  { accessorKey: "lab", header: "Lab ID" },
  { accessorKey: "pi", header: "PI ID" },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => formatDate(row.original.updated_at),
  },
];

export const rawFileColumns: ColumnDef<RawFile>[] = [
  { accessorKey: "filename", header: "File" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "file_role",
    header: "Role",
    cell: ({ row }) => <StatusBadge status={row.original.file_role} />,
  },
  {
    accessorKey: "size_bytes",
    header: "Size",
    cell: ({ row }) => formatBytes(row.original.size_bytes),
  },
  {
    accessorKey: "match_confidence",
    header: "Match",
    cell: ({ row }) => (row.original.match_confidence === null ? "-" : row.original.match_confidence.toFixed(2)),
  },
  {
    accessorKey: "imported_at",
    header: "Imported",
    cell: ({ row }) => formatDate(row.original.imported_at),
  },
  { accessorKey: "storage_path", header: "Storage" },
];

export const processingJobColumns: ColumnDef<ProcessingJob>[] = [
  { accessorKey: "id", header: "Job" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  { accessorKey: "run_name", header: "Run" },
  { accessorKey: "raw_file_filename", header: "Raw File" },
  {
    accessorKey: "pipeline_name",
    header: "Pipeline",
    cell: ({ row }) => `${row.original.pipeline_name} ${row.original.pipeline_version}`,
  },
  { accessorKey: "node_name", header: "Node" },
  {
    accessorKey: "started_at",
    header: "Started",
    cell: ({ row }) => formatDate(row.original.started_at),
  },
  {
    accessorKey: "finished_at",
    header: "Finished",
    cell: ({ row }) => formatDate(row.original.finished_at),
  },
  { accessorKey: "log_path", header: "Log" },
];

export const sampleColumns: ColumnDef<Sample>[] = [
  { accessorKey: "name", header: "Sample" },
  { accessorKey: "external_id", header: "External ID" },
  { accessorKey: "species", header: "Species" },
  { accessorKey: "matrix", header: "Matrix" },
  { accessorKey: "digestion_protocol", header: "Digestion" },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => formatDate(row.original.updated_at),
  },
];

export const runColumns: ColumnDef<Run>[] = [
  { accessorKey: "worklist_position", header: "Order" },
  { accessorKey: "run_name", header: "Run" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "file_role",
    header: "Role",
    cell: ({ row }) => <StatusBadge status={row.original.file_role} />,
  },
  { accessorKey: "expected_filename", header: "Expected File" },
  {
    accessorKey: "acquisition_started_at",
    header: "Started",
    cell: ({ row }) => formatDate(row.original.acquisition_started_at),
  },
];

export const acquisitionColumns: ColumnDef<AcquisitionWorklist>[] = [
  { accessorKey: "name", header: "Worklist" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  { accessorKey: "experiment", header: "Experiment ID" },
  { accessorKey: "configuration", header: "Configuration ID" },
  { accessorKey: "notes", header: "Notes" },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => formatDate(row.original.updated_at),
  },
];
