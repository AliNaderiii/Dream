/**
 * Cron parsing, matching and human-readable rendering.
 *
 * A faithful TypeScript mirror of `dream/cron.py`: five fields only
 * (star, step, range and comma lists), no seconds, no `@aliases`, no
 * `L`/`W`/`#` extensions.
 * The Python sidecar remains the source of truth for schedules that actually
 * fire; this port exists so the UI can validate input, render a live preview
 * and show the next fire time without a round trip on every keystroke.
 */

/** `[name, minimum, maximum]` per field, in wire order. */
export const CRON_FIELDS = [
  ['minute', 0, 59],
  ['hour', 0, 23],
  ['day', 1, 31],
  ['month', 1, 12],
  ['weekday', 0, 6],
] as const;

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

const WEEKDAY_NAMES = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
] as const;

/**
 * Four years of days bounds the forward walk in {@link nextRunAfter}: enough
 * for 29 February, finite for an impossible expression such as `0 0 30 2 *`.
 */
const SEARCH_LIMIT_DAYS = 366 * 4;

/** A parsed cron expression as five sets of permitted values. */
export interface CronExpression {
  expression: string;
  minutes: ReadonlySet<number>;
  hours: ReadonlySet<number>;
  days: ReadonlySet<number>;
  months: ReadonlySet<number>;
  weekdays: ReadonlySet<number>;
  dayRestricted: boolean;
  weekdayRestricted: boolean;
}

/** Raised for any malformed expression. */
export class CronError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CronError';
  }
}

function toInt(text: string, field: string): number {
  const trimmed = text.trim();
  if (!/^-?\d+$/.test(trimmed)) {
    throw new CronError(`cron ${field} value must be an integer, got '${trimmed}'`);
  }
  return Number.parseInt(trimmed, 10);
}

/** Expands one field to its value set and whether it is restricted. */
function parseField(raw: string, name: string, low: number, high: number): [Set<number>, boolean] {
  const field = raw.trim();
  if (!field) throw new CronError(`cron ${name} field is empty`);

  const values = new Set<number>();
  let restricted = false;

  for (const item of field.split(',')) {
    let part = item.trim();
    if (!part) throw new CronError(`cron ${name} field has an empty list item`);

    let step = 1;
    const slash = part.indexOf('/');
    if (slash !== -1) {
      const stepText = part.slice(slash + 1);
      part = part.slice(0, slash);
      if (!/^\d+$/.test(stepText.trim())) {
        throw new CronError(`cron ${name} step must be an integer, got '${stepText}'`);
      }
      step = Number.parseInt(stepText, 10);
      if (step < 1) throw new CronError(`cron ${name} step must be positive, got ${step}`);
    }

    let start: number;
    let end: number;
    if (part === '*' || part === '') {
      start = low;
      end = high;
      if (step !== 1) restricted = true;
    } else if (part.replace(/^-+/, '').includes('-')) {
      const dash = part.indexOf('-');
      start = toInt(part.slice(0, dash), name);
      end = toInt(part.slice(dash + 1), name);
      restricted = true;
    } else {
      start = end = toInt(part, name);
      restricted = true;
    }

    if (name === 'weekday') {
      // Both 0 and 7 mean Sunday in every cron dialect worth matching.
      if (start === 7) start = 0;
      if (end === 7) end = 0;
      if (end < start) {
        // A wrapping range such as fri-mon (5-1).
        for (let v = start; v <= 6; v += step) values.add(v);
        for (let v = 0; v <= end; v += step) values.add(v);
        continue;
      }
    }

    if (start < low || end > high || end < start) {
      throw new CronError(`cron ${name} value out of range [${low}, ${high}]: '${part}'`);
    }
    for (let v = start; v <= end; v += step) values.add(v);
  }

  if (values.size === 0) throw new CronError(`cron ${name} field matches nothing: '${field}'`);
  return [values, restricted];
}

/** Parses a five-field cron expression, throwing {@link CronError} if invalid. */
export function parseCron(expression: string): CronExpression {
  if (typeof expression !== 'string') throw new CronError('cron expression must be a string');
  const fields = expression.trim().split(/\s+/).filter(Boolean);
  if (fields.length !== 5) {
    throw new CronError(
      `cron expression must have 5 fields (minute hour day month weekday), ` +
        `got ${fields.length}: '${expression}'`,
    );
  }
  const sets: Set<number>[] = [];
  const restrictions: boolean[] = [];
  fields.forEach((raw, index) => {
    const [name, low, high] = CRON_FIELDS[index];
    const [values, restricted] = parseField(raw, name, low, high);
    sets.push(values);
    restrictions.push(restricted);
  });
  return {
    expression: fields.join(' '),
    minutes: sets[0],
    hours: sets[1],
    days: sets[2],
    months: sets[3],
    weekdays: sets[4],
    dayRestricted: restrictions[2],
    weekdayRestricted: restrictions[4],
  };
}

/** Returns the normalised expression, or throws. */
export function validateCron(expression: string): string {
  return parseCron(expression).expression;
}

/** Whether a cron expression fires at `moment` (to the minute). */
export function cronMatches(expression: string | CronExpression, moment: Date): boolean {
  const parsed = typeof expression === 'string' ? parseCron(expression) : expression;
  if (!parsed.minutes.has(moment.getMinutes())) return false;
  if (!parsed.hours.has(moment.getHours())) return false;
  if (!parsed.months.has(moment.getMonth() + 1)) return false;
  // Vixie cron: when both day-of-month and day-of-week are restricted the
  // expression fires on either, not on their intersection.
  const dayOk = parsed.days.has(moment.getDate());
  const weekdayOk = parsed.weekdays.has(moment.getDay());
  if (parsed.dayRestricted && parsed.weekdayRestricted) return dayOk || weekdayOk;
  return dayOk && weekdayOk;
}

function dateCouldMatch(parsed: CronExpression, moment: Date): boolean {
  if (!parsed.months.has(moment.getMonth() + 1)) return false;
  const dayOk = parsed.days.has(moment.getDate());
  const weekdayOk = parsed.weekdays.has(moment.getDay());
  if (parsed.dayRestricted && parsed.weekdayRestricted) return dayOk || weekdayOk;
  return dayOk && weekdayOk;
}

/**
 * The first minute strictly after `after` at which the expression fires.
 *
 * Walks forward a minute at a time, skipping whole days whose date fields
 * cannot match, which keeps even a yearly schedule well under a millisecond.
 */
export function nextRunAfter(expression: string | CronExpression, after: Date): Date {
  const parsed = typeof expression === 'string' ? parseCron(expression) : expression;
  const moment = new Date(after.getTime() + 60_000);
  moment.setSeconds(0, 0);
  const limit = after.getTime() + SEARCH_LIMIT_DAYS * 86_400_000;

  while (moment.getTime() <= limit) {
    if (!dateCouldMatch(parsed, moment)) {
      moment.setDate(moment.getDate() + 1);
      moment.setHours(0, 0, 0, 0);
      continue;
    }
    if (cronMatches(parsed, moment)) return moment;
    moment.setTime(moment.getTime() + 60_000);
  }
  throw new CronError(`cron expression never fires: '${parsed.expression}'`);
}

/** The next `count` fire times after `after`. */
export function upcomingRuns(
  expression: string | CronExpression,
  count = 3,
  after: Date = new Date(),
): Date[] {
  const parsed = typeof expression === 'string' ? parseCron(expression) : expression;
  const out: Date[] = [];
  let cursor = after;
  for (let i = 0; i < count; i += 1) {
    cursor = nextRunAfter(parsed, cursor);
    out.push(cursor);
  }
  return out;
}

// --------------------------------------------------------------------------- //
// Human-readable rendering
// --------------------------------------------------------------------------- //

function ordinal(n: number): string {
  if (n % 100 >= 11 && n % 100 <= 13) return `${n}th`;
  return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'}`;
}

/** Renders `13:05` as `1:05 PM`. */
export function clockLabel(hour: number, minute: number): string {
  const suffix = hour < 12 ? 'AM' : 'PM';
  const display = hour % 12 || 12;
  return `${display}:${String(minute).padStart(2, '0')} ${suffix}`;
}

function stepOf(field: string): number | null {
  if (!field.startsWith('*/')) return null;
  const step = Number.parseInt(field.slice(2), 10);
  return Number.isNaN(step) ? null : step;
}

function weekdayPhrase(field: string, weekdays: ReadonlySet<number>): string {
  if (field === '1-5') return 'every weekday';
  if (['0,6', '6,0', '6,7', '0,6,7'].includes(field)) return 'every weekend day';
  if (field === '6,0,1,2,3') return 'every Iranian working day (Sat–Wed)';
  const names = [...weekdays].sort((a, b) => a - b).map((d) => WEEKDAY_NAMES[d]);
  if (names.length === 1) return `every ${names[0]}`;
  return `every ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * Renders a cron expression as an English sentence for the UI.
 *
 * Covers every shape {@link nlToCron} can emit precisely, and degrades to a
 * literal reading for anything hand-written.
 */
export function describeCron(expression: string): string {
  const parsed = parseCron(expression);
  const [minuteF, hourF, dayF, monthF, weekdayF] = parsed.expression.split(' ') as [
    string,
    string,
    string,
    string,
    string,
  ];

  const minuteStep = stepOf(minuteF);
  if (minuteStep && hourF === '*' && dayF === '*' && monthF === '*' && weekdayF === '*') {
    return `every ${minuteStep} ${minuteStep === 1 ? 'minute' : 'minutes'}`;
  }

  const hourStep = stepOf(hourF);
  if (hourStep && dayF === '*' && monthF === '*' && weekdayF === '*') {
    const minutes = [...parsed.minutes].sort((a, b) => a - b);
    const at = minutes.length === 1 && minutes[0] === 0 ? '' : ` at ${minutes[0]} past`;
    return `every ${hourStep} ${hourStep === 1 ? 'hour' : 'hours'}${at}`;
  }

  const dayStep = stepOf(dayF);
  if (dayStep && monthF === '*' && weekdayF === '*' && parsed.hours.size === 1) {
    const hour = [...parsed.hours][0];
    const minute = Math.min(...parsed.minutes);
    return `every ${dayStep} ${dayStep === 1 ? 'day' : 'days'} at ${clockLabel(hour, minute)}`;
  }

  if (minuteF === '*' && hourF === '*') return 'every minute';

  if (parsed.hours.size !== 1 || parsed.minutes.size !== 1) {
    return `at cron schedule ${parsed.expression}`;
  }

  const at = clockLabel([...parsed.hours][0], [...parsed.minutes][0]);

  let when: string;
  if (weekdayF !== '*') {
    when = weekdayPhrase(weekdayF, parsed.weekdays);
  } else if (dayF !== '*') {
    const days = [...parsed.days]
      .sort((a, b) => a - b)
      .map(ordinal)
      .join(' and ');
    when = `on the ${days}`;
  } else {
    when = 'every day';
  }

  if (monthF !== '*') {
    const months = [...parsed.months]
      .sort((a, b) => a - b)
      .map((m) => MONTH_NAMES[m - 1])
      .join(' and ');
    when = `${when} in ${months}`;
  }

  return `${when} at ${at}`;
}
