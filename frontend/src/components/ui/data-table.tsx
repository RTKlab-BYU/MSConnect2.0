import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type DataTableProps<TData, TValue> = {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  estimateSize?: number;
  emptyLabel?: string;
  className?: string;
};

export function DataTable<TData, TValue>({
  columns,
  data,
  emptyLabel = "No records found.",
  className,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;

  return (
    <div className={cn("min-w-0 overflow-hidden rounded-2xl border bg-card/95 shadow-[0_18px_50px_rgb(15_23_42/0.06)]", className)}>
      <div className="table-scroll">
        <div className="max-h-[560px] overflow-auto">
        <table className="w-full min-w-[960px] border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-secondary/95 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sort = header.column.getIsSorted();
                  return (
                    <th key={header.id} className="border-b px-4 py-3 font-bold">
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <Button
                          className="-ml-2 h-8 px-2 text-xs uppercase tracking-[0.08em]"
                          variant="ghost"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sort === "asc" ? (
                            <ArrowUp className="h-3.5 w-3.5" />
                          ) : sort === "desc" ? (
                            <ArrowDown className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronsUpDown className="h-3.5 w-3.5 opacity-55" />
                          )}
                        </Button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
            <tbody>
              {rows.length ? (
                rows.map((row) => {
                  return (
                    <tr key={row.id} className="border-b hover:bg-secondary/45">
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="break-words px-4 py-2.5 align-top whitespace-normal">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td className="px-3 py-8 text-center text-muted-foreground" colSpan={columns.length}>
                    {emptyLabel}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
