/**
 * Profiling summary: headline counts plus one expandable card per column
 * with a mini histogram (numeric) or top-values list (categorical).
 */

import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { formatBytes } from '@/lib/bridge/data-science';
import type { ColumnProfileDto, DatasetProfileDto } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

function MiniHistogram({ counts }: { counts: number[] }) {
  const max = Math.max(...counts, 1);
  return (
    <div className="flex h-12 items-end gap-px" role="img" aria-label="Value distribution">
      {counts.map((count, i) => (
        <span
          key={i}
          className="flex-1 rounded-t-sm bg-accent"
          style={{ height: `${Math.max(4, (count / max) * 100)}%`, opacity: 0.75 }}
        />
      ))}
    </div>
  );
}

function roleBadge(role: string | undefined): 'accent' | 'info' | 'success' | 'neutral' {
  switch (role) {
    case 'numeric':
      return 'accent';
    case 'datetime':
      return 'info';
    case 'boolean':
      return 'success';
    default:
      return 'neutral';
  }
}

function StatPair({ label, value }: { label: string; value: string | number | undefined }) {
  if (value === undefined) return null;
  return (
    <span className="flex justify-between gap-3">
      <span className="text-fg-muted">{label}</span>
      <span className="tabular">{typeof value === 'number' ? formatNumber(value) : value}</span>
    </span>
  );
}

function formatNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(Math.abs(value) < 10 ? 4 : 2);
}

function ColumnCard({ name, profile }: { name: string; profile: ColumnProfileDto }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-lg border border-border-default bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 p-2.5 text-start hover:bg-surface-2"
      >
        {open ? (
          <ChevronDown className="size-4 shrink-0 text-fg-muted" aria-hidden />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-fg-muted rtl:rotate-180" aria-hidden />
        )}
        <span className="truncate font-medium">{name}</span>
        <Badge variant={roleBadge(profile.role)}>{profile.role ?? profile.dtype}</Badge>
        {profile.missing > 0 && (
          <Badge variant="warning">{profile.missing_pct?.toFixed(1) ?? '?'}% missing</Badge>
        )}
        {(profile.outliers_iqr ?? 0) > 0 && (
          <Badge variant="danger">{profile.outliers_iqr} outliers</Badge>
        )}
      </button>
      {open && (
        <div className="grid gap-3 border-t border-border-default p-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1 text-caption">
            <StatPair label="dtype" value={profile.dtype} />
            <StatPair label="unique" value={profile.unique} />
            <StatPair label="missing" value={profile.missing} />
            <StatPair label="mean" value={profile.mean} />
            <StatPair label="std" value={profile.std} />
            <StatPair label="min" value={profile.min} />
            <StatPair label="median" value={profile.median} />
            <StatPair label="max" value={profile.max} />
          </div>
          <div>
            {profile.histogram ? (
              <MiniHistogram counts={profile.histogram.counts} />
            ) : profile.top_values ? (
              <ul className="flex flex-col gap-1 text-caption">
                {profile.top_values.slice(0, 6).map((entry) => (
                  <li key={entry.value} className="flex justify-between gap-3">
                    <span className="truncate">{entry.value}</span>
                    <span className="tabular text-fg-muted">{entry.count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-caption text-fg-muted">No distribution available.</p>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

export function ProfilingCard({ profile }: { profile: DatasetProfileDto }) {
  const headline: { label: string; value: string }[] = [
    { label: 'Rows', value: profile.row_count.toLocaleString() },
    { label: 'Columns', value: String(profile.column_count) },
    {
      label: 'Missing',
      value: profile.missing_pct === null ? '—' : `${profile.missing_pct.toFixed(2)}%`,
    },
    {
      label: 'Duplicates',
      value: profile.duplicate_rows === null ? '—' : String(profile.duplicate_rows),
    },
  ];
  if (profile.memory_bytes !== undefined) {
    headline.push({ label: 'In-memory', value: formatBytes(profile.memory_bytes) });
  }

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
        {headline.map((stat) => (
          <div
            key={stat?.label}
            className={cn('rounded-lg border border-border-default bg-surface p-3')}
          >
            <dt className="text-caption text-fg-muted">{stat?.label}</dt>
            <dd className="text-h3 font-semibold tabular">{stat.value}</dd>
          </div>
        ))}
      </dl>
      {profile.sampled && (
        <p className="text-caption text-warning-fg">
          Large file: statistics were computed with chunked aggregation; quantiles are approximate.
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {Object.entries(profile.columns).map(([name, column]) => (
          <ColumnCard key={name} name={name} profile={column} />
        ))}
      </ul>
    </div>
  );
}
