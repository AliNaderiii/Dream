/**
 * Pure models for the skills learning workspace (MEM Stage F).
 *
 * Two concerns, no React: use-log statistics and version diffs. Both are
 * pinned by tests so the panel stays a thin rendering layer.
 *
 * Laws:
 * - any use outcome that is not exactly ``ok`` is a failure — an
 *   unrecognised outcome must count, never be dropped;
 * - the busiest skill orders first, ties broken by name so the table is
 *   deterministic;
 * - a diff never reorders or rewrites a line: Persian bodies come back
 *   byte-identical, just labelled.
 */

/** One `skills.use_log` row (wire shape). */
export interface SkillUseRow {
  name: string;
  invoked_at: number;
  outcome: string;
  duration_ms: number;
  source: string;
}

/** Aggregated stats for one skill. */
export interface SkillStat {
  name: string;
  runs: number;
  failures: number;
  medianMs: number;
}

/** Median of a numeric sample: average of the middle pair when even. */
export function median(values: readonly number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Per-skill run/failure counts and median duration, busiest first. */
export function summariseUses(uses: readonly SkillUseRow[]): SkillStat[] {
  const table = new Map<string, { durations: number[]; runs: number; failures: number }>();
  for (const use of uses) {
    const entry = table.get(use.name) ?? { durations: [], runs: 0, failures: 0 };
    entry.runs += 1;
    if (use.outcome !== 'ok') entry.failures += 1;
    if (Number.isFinite(use.duration_ms)) entry.durations.push(use.duration_ms);
    table.set(use.name, entry);
  }
  return [...table.entries()]
    .map(([name, entry]) => ({
      name,
      runs: entry.runs,
      failures: entry.failures,
      medianMs: median(entry.durations),
    }))
    .sort((a, b) => b.runs - a.runs || a.name.localeCompare(b.name));
}

export type DiffLineKind = 'added' | 'removed' | 'same';

/** One labelled line of a version diff; `text` is verbatim. */
export interface DiffLine {
  kind: DiffLineKind;
  text: string;
}

/**
 * Line diff between two skill versions (LCS on whole lines). An empty side
 * loses nothing: every line of the other side is added/removed.
 */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.length === 0 ? [] : before.split('\n');
  const b = after.length === 0 ? [] : after.split('\n');
  // Longest common subsequence table (version bodies are small).
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      lines.push({ kind: 'same', text: a[i] });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      lines.push({ kind: 'removed', text: a[i] });
      i += 1;
    } else {
      lines.push({ kind: 'added', text: b[j] });
      j += 1;
    }
  }
  while (i < a.length) {
    lines.push({ kind: 'removed', text: a[i] });
    i += 1;
  }
  while (j < b.length) {
    lines.push({ kind: 'added', text: b[j] });
    j += 1;
  }
  return lines;
}

/** Counts per kind, for the diff summary line. */
export function diffCounts(lines: readonly DiffLine[]): Record<DiffLineKind, number> {
  const counts: Record<DiffLineKind, number> = { added: 0, removed: 0, same: 0 };
  for (const line of lines) counts[line.kind] += 1;
  return counts;
}
