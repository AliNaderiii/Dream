/**
 * Reminder authoring helpers (P-13).
 *
 * A reminder is a schedule of `kind: 'reminder'` executed by the one existing
 * scheduler daemon. These helpers are the only place that translate between
 * the authoring form and the scheduler contract:
 *
 * - a **one-off** reminder compiles a date + time into the cron field
 *   `M H D Mon *` and sets `max_runs: 1`, so it fires exactly once and then
 *   finishes;
 * - a **repeating** reminder passes the phrase straight to `schedule.preview`
 *   / `schedule.create`, exactly like the scheduler page does.
 *
 * Everything here is pure and deterministic — the sidecar re-parses whatever
 * we submit and its verdict wins.
 */

/** Cron built from an `<input type="date">` + `<input type="time">` pair. */
const ONE_OFF_CRON_RE = /^(\d{1,2}) (\d{1,2}) (\d{1,2}) (\d{1,2}) \*$/;

/** Longest reminder text accepted client-side (mirrors the store's feel). */
export const MAX_REMINDER_CHARS = 500;

export type ReminderMode = 'once' | 'repeat';

/** Annotated authoring draft shared by the create and edit dialogs. */
export interface ReminderDraft {
  text: string;
  mode: ReminderMode;
  /** `YYYY-MM-DD` from a date input, used when mode is `once`. */
  date: string;
  /** `HH:MM` from a time input, used when mode is `once`. */
  time: string;
  /** Natural-language rhythm or raw cron, used when mode is `repeat`. */
  rhythm: string;
}

export const EMPTY_REMINDER_DRAFT: ReminderDraft = {
  text: '',
  mode: 'once',
  date: '',
  time: '',
  rhythm: '',
};

/**
 * The prompt a reminder runs when it fires. The prefix names what the run is
 * so the reply in the history is recognisable; Persian uses «یادآوری».
 */
export function reminderPrompt(text: string, locale: string): string {
  const prefix = locale === 'fa' ? 'یادآوری:' : 'Reminder:';
  return `${prefix} ${text.trim()}`;
}

/** Compile a one-off date + time into a cron expression (`M H D Mon *`). */
export function oneOffCron(date: string, time: string): string {
  const [year, month, day] = date.split('-').map((part) => Number(part));
  const [hour, minute] = time.split(':').map((part) => Number(part));
  if (!year || !month || !day || !Number.isInteger(hour) || !Number.isInteger(minute)) {
    throw new Error('one-off reminder needs a valid date and time');
  }
  return `${minute} ${hour} ${day} ${month} *`;
}

/**
 * Split a one-off cron back into `{ date, time }` for the edit form, or
 * `null` when the expression is not a plain one-off (ranges, lists, foreign
 * rhythms). Only used to prefill the form; the server stays the authority.
 */
export function oneOffParts(cron: string): { date: string; time: string } | null {
  const match = ONE_OFF_CRON_RE.exec(cron.trim());
  if (!match) return null;
  const minute = Number(match[1]);
  const hour = Number(match[2]);
  const day = Number(match[3]);
  const month = Number(match[4]);
  if (minute > 59 || hour > 23 || day < 1 || day > 31 || month < 1 || month > 12) return null;
  const pad = (value: number, width = 2): string => String(value).padStart(width, '0');
  // The year is not part of the cron; the form only needs a future date, so
  // the next occurrence of that month/day is what the prefill suggests.
  const now = new Date();
  let year = now.getFullYear();
  if (month < now.getMonth() + 1 || (month === now.getMonth() + 1 && day < now.getDate())) {
    year += 1;
  }
  return { date: `${year}-${pad(month)}-${pad(day)}`, time: `${pad(hour)}:${pad(minute)}` };
}

/** True when the schedule looks like a one-off reminder (fires once, done). */
export function isOneOff(maxRuns: number | null, cron: string): boolean {
  return maxRuns === 1 && ONE_OFF_CRON_RE.test(cron.trim());
}

/**
 * Validate the one-off fields. Returns an error message key suffix, or
 * `null` when the fire moment is a real, future date. Malformed strings are
 * rejected, and so is a syntactically clean but impossible date (month 13,
 * day 40) that JavaScript would silently roll over into the next season —
 * the components of the parsed date must equal the input. A past date would
 * produce a cron that never fires, so it is refused here, before anything is
 * persisted.
 */
export function validateOneOff(date: string, time: string, now: Date): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) {
    return 'previewInvalidDate';
  }
  const [year, month, day] = date.split('-').map(Number);
  const [hour, minute] = time.split(':').map(Number);
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) {
    return 'previewInvalidDate';
  }
  const fire = new Date(year, month - 1, day, hour, minute);
  if (
    Number.isNaN(fire.getTime()) ||
    fire.getFullYear() !== year ||
    fire.getMonth() !== month - 1 ||
    fire.getDate() !== day
  ) {
    return 'previewInvalidDate'; // rolled over (e.g. 2027-02-31) — not the chosen day
  }
  if (fire.getTime() <= now.getTime()) return 'previewInvalidDate';
  return null;
}

/** Reminder text validation — trimmed, non-empty, bounded. */
export function validateReminderText(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.length > 0 && trimmed.length <= MAX_REMINDER_CHARS;
}
