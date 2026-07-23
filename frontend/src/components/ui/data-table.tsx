import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import type { CSSProperties } from "react";
import { useRef, useState } from "react";

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
  estimateSize = 44,
  emptyLabel = "No records found.",
  className,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const parentRef = useRef<HTMLDivElement>(null);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan: 12,
  });

  return (
    <div className={cn("overflow-hidden rounded-2xl border bg-card/95 shadow-[0_18px_50px_rgb(15_23_42/0.06)]", className)}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[960px] border-collapse text-sm">
          <thead className="bg-secondary/65 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
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
        </table>
        <div ref={parentRef} className="max-h-[560px] overflow-auto">
          <table className="w-full min-w-[960px] border-collapse text-sm">
            <tbody style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
              {rows.length ? (
                virtualizer.getVirtualItems().map((virtualRow) => {
                  const row = rows[virtualRow.index];
                  return (
                    <tr
                      key={row.id}
                      className="absolute left-0 grid w-full grid-cols-[repeat(var(--col-count),minmax(0,1fr))] border-b hover:bg-secondary/45"
                      style={
                        {
                          "--col-count": row.getVisibleCells().length,
                          height: `${virtualRow.size}px`,
                          transform: `translateY(${virtualRow.start}px)`,
                        } as CSSProperties
                      }
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="truncate px-4 py-2.5 align-middle">
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
