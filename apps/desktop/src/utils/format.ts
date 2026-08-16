/**
 * Display formatting for the values the bridge hands back.
 *
 * Sidecar timestamps are epoch *seconds* as floats (Python's `time.time()`),
 * while `Date` wants milliseconds — every helper here takes seconds so the call
 * sites never have to remember the factor.
 */

/** Turns a duration in seconds into a compact reading: `4s`, `2m 30s`, `1h 05m`. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—';
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  if (minutes < 60) return `${minutes}m ${String(secs).padStart(2, '0')}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`;
}

/** Wall-clock time of an epoch-seconds instant, e.g. `14:05`. */
export function formatClock(epochSeconds: number | null | undefined): string {
  if (epochSeconds === null || epochSeconds === undefined) return '—';
  return new Date(epochSeconds * 1000).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Date and time of an epoch-seconds instant, e.g. `12 Mar, 14:05`. */
export function formatDateTime(epochSeconds: number | null | undefined): string {
  if (epochSeconds === null || epochSeconds === undefined) return '—';
  return new Date(epochSeconds * 1000).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * A coarse relative reading of an epoch-seconds instant: `in 3h`, `12m ago`.
 * Deliberately coarse — schedules only ever need the order of magnitude.
 */
export function formatRelative(epochSeconds: number | null | undefined, now = Date.now()): string {
  if (epochSeconds === null || epochSeconds === undefined) return '—';
  const deltaSeconds = epochSeconds - now / 1000;
  const ahead = deltaSeconds >= 0;
  const magnitude = Math.abs(deltaSeconds);

  let reading: string;
  if (magnitude < 45) reading = 'moments';
  else if (magnitude < 3600) reading = `${Math.round(magnitude / 60)}m`;
  else if (magnitude < 86_400) reading = `${Math.round(magnitude / 3600)}h`;
  else reading = `${Math.round(magnitude / 86_400)}d`;

  if (reading === 'moments') return ahead ? 'in moments' : 'just now';
  return ahead ? `in ${reading}` : `${reading} ago`;
}

/** Formats a token count compactly: `940`, `12.4k`. */
export function formatTokens(count: number): string {
  if (count < 1000) return String(count);
  return `${(count / 1000).toFixed(1)}k`;
}
