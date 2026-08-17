/**
 * Dataset preview grid (TanStack Table): sort, filter, paginate, column
 * resize, row hover, per-cell copy. Purely presentational — the rows come
 * from `data.get_dataset` / `data.clean_data` previews.
 */

import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ArrowUpDown, Check, Copy } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { formatCell } from '@/lib/bridge/data-science';
import { cn } from '@/utils/cn';

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  /** Rows per page. */
  pageSize?: number;
}

function CopyableCell({ value }: { value: unknown }) {
  const [copied, setCopied] = useState(false);
  const text = formatCell(value);
  const copy = () => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };
  return (
    <span className="group/cell flex items-center gap-1">
      <span className="truncate">{text}</span>
      <button
        type="button"
        aria-label={`Copy ${text}`}
        onClick={copy}
        className="invisible shrink-0 rounded p-0.5 text-fg-muted hover:bg-surface-2 hover:text-fg-primary group-hover/cell:visible"
      >
        {copied ? (
          <Check className="size-3 text-success-fg" aria-hidden />
        ) : (
          <Copy className="size-3" aria-hidden />
        )}
      </button>
    </span>
  );
}

export function DataTable({ columns, rows, pageSize = 25 }: DataTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState('');

  const columnDefs = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      columns.map((name) => ({
        id: name,
        accessorFn: (row) => row[name],
        header: name,
        cell: (info) => <CopyableCell value={info.getValue()} />,
        sortDescFirst: false,
        sortUndefined: 'last',
        size: 160,
        minSize: 80,
        maxSize: 480,
      })),
    [columns],
  );

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: 'includesString',
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    initialState: { pagination: { pageSize } },
  });

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <input
          type="search"
          role="searchbox"
          aria-label="Filter rows"
          placeholder="Filter rows…"
          value={globalFilter}
          onChange={(event) => setGlobalFilter(event.target.value)}
          className="h-8 w-64 rounded-md border border-border-default bg-surface px-2.5 text-body outline-none focus:border-accent"
        />
        <span className="text-caption text-fg-muted">
          {table.getFilteredRowModel().rows.length} of {rows.length} rows
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border-default">
        <table className="w-full border-collapse text-body" style={{ width: table.getTotalSize() }}>
          <thead className="sticky top-0 z-10 bg-surface-2">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      style={{ width: header.getSize() }}
                      className="relative border-b border-e border-border-default px-2.5 py-1.5 text-start font-semibold"
                    >
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        aria-label={`Sort by ${header.column.id}`}
                        className="flex w-full items-center gap-1 hover:text-accent-text"
                      >
                        <span className="truncate">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                        </span>
                        {sorted === 'asc' ? (
                          <ArrowUp className="size-3 shrink-0" aria-hidden />
                        ) : sorted === 'desc' ? (
                          <ArrowDown className="size-3 shrink-0" aria-hidden />
                        ) : (
                          <ArrowUpDown className="size-3 shrink-0 text-fg-muted" aria-hidden />
                        )}
                      </button>
                      {/* Column resize handle. */}
                      <span
                        role="separator"
                        aria-orientation="vertical"
                        onMouseDown={header.getResizeHandler()}
                        onTouchStart={header.getResizeHandler()}
                        className={cn(
                          'absolute end-0 top-0 h-full w-1 cursor-col-resize touch-none select-none',
                          header.column.getIsResizing() ? 'bg-accent' : 'hover:bg-border-strong',
                        )}
                      />
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-surface-2">
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    style={{ width: cell.column.getSize() }}
                    className="max-w-0 border-b border-e border-border-default px-2.5 py-1 tabular"
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-caption text-fg-muted">
          Page {table.getState().pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}
        </span>
        <div className="flex gap-1.5">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
