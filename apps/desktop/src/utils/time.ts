/**
 * Time formatting helpers.
 *
 * Every timestamp Dream stores is unix **seconds**. Formatting goes through
 * `Intl`, which respects the document locale (and therefore renders Persian
 * digits and the Persian calendar when the shell is switched to `fa`).
 */

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

/** The document's current language tag, falling back to English. */
function activeLocale(): string {
  if (typeof document === 'undefined') return 'en';
  return document.documentElement.lang || 'en';
}

/**
 * Relative time such as "3 days ago". Uses `Intl.RelativeTimeFormat` so the
 * Persian locale reads naturally instead of being string-concatenated.
 */
export function relativeTime(seconds: number, now = Date.now() / 1000): string {
  const delta = seconds - now;
  const abs = Math.abs(delta);
  const rtf = new Intl.RelativeTimeFormat(activeLocale(), { numeric: 'auto' });
  if (abs < MINUTE) return rtf.format(Math.round(delta), 'second');
  if (abs < HOUR) return rtf.format(Math.round(delta / MINUTE), 'minute');
  if (abs < DAY) return rtf.format(Math.round(delta / HOUR), 'hour');
  if (abs < WEEK) return rtf.format(Math.round(delta / DAY), 'day');
  if (abs < MONTH) return rtf.format(Math.round(delta / WEEK), 'week');
  if (abs < YEAR) return rtf.format(Math.round(delta / MONTH), 'month');
  return rtf.format(Math.round(delta / YEAR), 'year');
}

/** Absolute date and time, e.g. "12 Aug 2026, 14:03". */
export function absoluteTime(seconds: number): string {
  if (!seconds) return '—';
  return new Intl.DateTimeFormat(activeLocale(), {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(seconds * 1000));
}

/** Date only, e.g. "12 Aug 2026". */
export function absoluteDate(seconds: number): string {
  if (!seconds) return '—';
  return new Intl.DateTimeFormat(activeLocale(), { dateStyle: 'medium' }).format(
    new Date(seconds * 1000),
  );
}

/** Zoom levels for the memory timeline. */
export type TimelineZoom = 'day' | 'week' | 'month';

/**
 * Stable bucket key for a timestamp at the given zoom. Keys sort
 * lexicographically in chronological order, so grouping needs no comparator.
 */
export function bucketKey(seconds: number, zoom: TimelineZoom): string {
  const date = new Date(seconds * 1000);
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  if (zoom === 'month') return `${year}-${month}`;
  if (zoom === 'week') {
    // Bucket by the Monday that starts the week.
    const monday = new Date(date);
    const weekday = (monday.getDay() + 6) % 7;
    monday.setDate(monday.getDate() - weekday);
    monday.setHours(0, 0, 0, 0);
    return `${monday.getFullYear()}-${`${monday.getMonth() + 1}`.padStart(2, '0')}-${`${monday.getDate()}`.padStart(2, '0')}`;
  }
  return `${year}-${month}-${`${date.getDate()}`.padStart(2, '0')}`;
}

/** Human label for a bucket key produced by {@link bucketKey}. */
export function bucketLabel(key: string, zoom: TimelineZoom): string {
  const locale = activeLocale();
  if (zoom === 'month') {
    const [year, month] = key.split('-').map(Number);
    return new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(
      new Date(year, (month ?? 1) - 1, 1),
    );
  }
  const [year, month, day] = key.split('-').map(Number);
  const date = new Date(year, (month ?? 1) - 1, day ?? 1);
  const formatted = new Intl.DateTimeFormat(locale, { dateStyle: 'full' }).format(date);
  return zoom === 'week' ? `Week of ${formatted}` : formatted;
}

/** Convert a `<input type="date">` value to unix seconds at local midnight. */
export function dateInputToSeconds(value: string, endOfDay = false): number | null {
  if (!value) return null;
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return null;
  const date = endOfDay
    ? new Date(year, month - 1, day, 23, 59, 59)
    : new Date(year, month - 1, day, 0, 0, 0);
  return Math.floor(date.getTime() / 1000);
}

/** Convert unix seconds to a `<input type="date">` value (`YYYY-MM-DD`). */
export function secondsToDateInput(seconds: number | null): string {
  if (!seconds) return '';
  const date = new Date(seconds * 1000);
  return `${date.getFullYear()}-${`${date.getMonth() + 1}`.padStart(2, '0')}-${`${date.getDate()}`.padStart(2, '0')}`;
}
