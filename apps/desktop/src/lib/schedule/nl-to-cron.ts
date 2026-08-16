/**
 * Turn everyday English or Persian phrasing into a cron expression.
 *
 * A TypeScript mirror of `dream/nl_schedule.py`, kept structurally identical so
 * the two stay in step: input is normalised once, then independent readers pull
 * out the interval, the time of day and the day scope. Gate G7 requires pure
 * pattern matching — no model call — so a phrase parses the same offline, in
 * CI, and in the packaged app.
 *
 * The sidecar re-parses whatever the user submits, so this port is only ever
 * used for the live preview; when the two disagree the sidecar wins. Every case
 * in `NL_CASES` (`tests/test_scheduler.py`) is exercised against this file by
 * `nl-to-cron.test.ts`, which is what keeps the disagreement set empty.
 */

import { validateCron } from './cron';
import { normalizeFa } from './normalize-fa';

/** Thrown when no pattern matches — the caller must not guess. */
export class ScheduleParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ScheduleParseError';
  }
}

// --------------------------------------------------------------------------- //
// Vocabulary
// --------------------------------------------------------------------------- //

/**
 * Cron numbers Sunday as 0. The Persian week begins on Saturday, so the Persian
 * names are mapped by their own order, not by translating the English list.
 */
const WEEKDAYS = new Map<string, number>([
  ['sunday', 0],
  ['sun', 0],
  ['monday', 1],
  ['mon', 1],
  ['tuesday', 2],
  ['tue', 2],
  ['tues', 2],
  ['wednesday', 3],
  ['wed', 3],
  ['thursday', 4],
  ['thu', 4],
  ['thur', 4],
  ['thurs', 4],
  ['friday', 5],
  ['fri', 5],
  ['saturday', 6],
  ['sat', 6],
  // Gloss: یکشنبه Sunday, دوشنبه Monday, سه شنبه Tuesday, چهارشنبه Wednesday,
  // پنجشنبه Thursday, جمعه Friday, شنبه Saturday.
  ['\u06cc\u06a9\u0634\u0646\u0628\u0647', 0],
  ['\u062f\u0648\u0634\u0646\u0628\u0647', 1],
  ['\u0633\u0647 \u0634\u0646\u0628\u0647', 2],
  ['\u0633\u0647\u0634\u0646\u0628\u0647', 2],
  ['\u0686\u0647\u0627\u0631\u0634\u0646\u0628\u0647', 3],
  ['\u067e\u0646\u062c\u0634\u0646\u0628\u0647', 4],
  ['\u067e\u0646\u062c \u0634\u0646\u0628\u0647', 4],
  ['\u062c\u0645\u0639\u0647', 5],
  ['\u0634\u0646\u0628\u0647', 6],
]);

/** Longest first: "سه شنبه" must be tried before the "شنبه" it contains. */
const WEEKDAY_ORDER = [...WEEKDAYS.keys()].sort((a, b) => b.length - a.length);

const ENGLISH_ABBREVIATIONS = new Set(['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']);

const MONTH_WORDS = ['month', 'monthly', '\u0645\u0627\u0647'] as const; // Gloss: ماه month
const WEEK_WORDS = ['week', 'weekly', '\u0647\u0641\u062a\u0647'] as const; // Gloss: هفته week
const DAY_WORDS = ['day', 'daily', '\u0631\u0648\u0632'] as const; // Gloss: روز day
const HOUR_WORDS = ['hour', 'hourly', '\u0633\u0627\u0639\u062a'] as const; // Gloss: ساعت hour
const MINUTE_WORDS = ['minute', 'min', '\u062f\u0642\u06cc\u0642\u0647'] as const; // Gloss: دقیقه minute
const YEAR_WORDS = ['year', 'yearly', 'annually', '\u0633\u0627\u0644'] as const; // Gloss: سال year

// Gloss: هر every, روزهای کاری weekdays, آخر هفته weekend.
const EVERY = ['every', 'each', '\u0647\u0631'] as const;

const WEEKDAY_SCOPE = [
  'weekday',
  'weekdays',
  'week day',
  'week days',
  'business day',
  'business days',
  'working day',
  'working days',
  '\u0631\u0648\u0632\u0647\u0627\u06cc \u06a9\u0627\u0631\u06cc',
  '\u0631\u0648\u0632 \u06a9\u0627\u0631\u06cc',
] as const;

const WEEKEND_SCOPE = [
  'weekend',
  'weekends',
  '\u0622\u062e\u0631 \u0647\u0641\u062a\u0647',
  '\u0627\u062e\u0631 \u0647\u0641\u062a\u0647',
  '\u067e\u0627\u06cc\u0627\u0646 \u0647\u0641\u062a\u0647',
] as const;

/**
 * The Iranian working week runs Saturday to Wednesday; Thursday and Friday are
 * the weekend. A Persian "روزهای کاری" therefore cannot mean the ISO `1-5`.
 */
const IRANIAN_WORKDAYS = '6,0,1,2,3';
const IRANIAN_WEEKEND = '4,5';

// Gloss: صبح morning, ظهر noon, بعدازظهر/عصر afternoon, شب night, نیمه شب midnight.
const MORNING = ['am', 'a.m', 'morning', '\u0635\u0628\u062d'] as const;
const AFTERNOON = [
  'pm',
  'p.m',
  'afternoon',
  'evening',
  'night',
  '\u0628\u0639\u062f\u0627\u0632\u0638\u0647\u0631',
  '\u0628\u0639\u062f \u0627\u0632 \u0638\u0647\u0631',
  '\u0639\u0635\u0631',
  '\u0634\u0628',
] as const;
const NOON = ['noon', 'midday', '\u0638\u0647\u0631'] as const;
const MIDNIGHT = [
  'midnight',
  '\u0646\u06cc\u0645\u0647 \u0634\u0628',
  '\u0646\u06cc\u0645\u0647\u200c\u0634\u0628',
] as const;

const NUMBER_WORDS = new Map<string, number>([
  ['one', 1],
  ['two', 2],
  ['three', 3],
  ['four', 4],
  ['five', 5],
  ['six', 6],
  ['seven', 7],
  ['eight', 8],
  ['nine', 9],
  ['ten', 10],
  ['twelve', 12],
  ['fifteen', 15],
  ['twenty', 20],
  ['thirty', 30],
  ['half an', 30],
  // Gloss: یک 1, دو 2, سه 3, چهار 4, پنج 5, شش 6, ده 10, پانزده 15, سی 30.
  ['\u06cc\u06a9', 1],
  ['\u062f\u0648', 2],
  ['\u0633\u0647', 3],
  ['\u0686\u0647\u0627\u0631', 4],
  ['\u067e\u0646\u062c', 5],
  ['\u0634\u0634', 6],
  ['\u062f\u0647', 10],
  ['\u067e\u0627\u0646\u0632\u062f\u0647', 15],
  ['\u0633\u06cc', 30],
]);

const ORDINALS = new Map<string, number>([
  ['first', 1],
  ['1st', 1],
  ['second', 2],
  ['2nd', 2],
  ['third', 3],
  ['3rd', 3],
  ['fourth', 4],
  ['4th', 4],
  ['fifth', 5],
  ['5th', 5],
  ['last', 28],
  // Gloss: اول first, دوم second, سوم third, آخر last.
  ['\u0627\u0648\u0644', 1],
  ['\u062f\u0648\u0645', 2],
  ['\u0633\u0648\u0645', 3],
  ['\u0622\u062e\u0631', 28],
]);

/**
 * JavaScript's `\b` is ASCII-only, so a Persian word followed by a space is not
 * a boundary the way it is in Python. This lookahead restores the Python
 * meaning for the trailing edge of a match.
 */
const WORD_END = '(?![0-9A-Za-z_\\u0600-\\u06ff])';
const LETTER = 'a-z\\u0600-\\u06ff';

function escapeRe(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

interface Parsed {
  minute: string;
  hour: string;
  day: string;
  month: string;
  weekday: string;
}

function emptyParsed(): Parsed {
  return { minute: '0', hour: '0', day: '*', month: '*', weekday: '*' };
}

function toCron(parsed: Parsed): string {
  return `${parsed.minute} ${parsed.hour} ${parsed.day} ${parsed.month} ${parsed.weekday}`;
}

/** Folds digits and scripts, then collapses punctuation and whitespace. */
function normalise(text: string): string {
  let folded = normalizeFa(text || '');
  folded = folded.replace(/\u060c/g, ' ').replace(/,/g, ' ');
  folded = folded.replace(/[.\u061f?!]+/g, ' ');
  return folded.replace(/\s+/g, ' ').trim().toLowerCase();
}

/**
 * Reads "every N <unit>", including spelled-out numbers. The Persian
 * equivalent is "هر N <unit>".
 */
function findCount(text: string, units: readonly string[]): number | null {
  for (const unit of units) {
    // The count is optional ("every hour") and the unit may be plural ("every
    // 15 minutes"); Persian units take no plural suffix, so the trailing `s?`
    // is simply never used on that path.
    const pattern = new RegExp(
      `(?:${EVERY.join('|')})\\s+(\\d+|[${LETTER} ]+?)?\\s*${escapeRe(unit)}s?${WORD_END}`,
    );
    const match = pattern.exec(text);
    if (!match) continue;
    const raw = (match[1] ?? '').trim();
    if (/^\d+$/.test(raw)) return Number.parseInt(raw, 10);
    for (const [word, value] of NUMBER_WORDS) {
      if (raw.endsWith(word)) return value;
    }
    return 1; // bare "every hour"
  }
  return null;
}

/** Extracts an explicit clock time, returning `[hour, minute]`. */
function readTime(text: string): [number, number] | null {
  if (MIDNIGHT.some((word) => text.includes(word))) return [0, 0];
  // "12:30 noon" is a time with a qualifier, so only treat noon as 12:00 when
  // no digits accompany it.
  if (NOON.some((word) => text.includes(word)) && !/\d/.test(text)) return [12, 0];

  let hour: number;
  let minute: number;
  const match =
    /(\d{1,2})\s*[:\u06f1]\s*(\d{2})/.exec(text) ?? /(\d{1,2})\s*:\s*(\d{2})/.exec(text);
  if (match) {
    hour = Number.parseInt(match[1], 10);
    minute = Number.parseInt(match[2], 10);
  } else {
    // A bare hour needs a marker so "every 15 minutes" is not read as 15:00.
    const anchored =
      /(?:at|@|\u0633\u0627\u0639\u062a)\s*(\d{1,2})(?!\s*\d)/.exec(text) ??
      /\b(\d{1,2})\s*(?:am|pm|a\.m|p\.m)\b/.exec(text);
    if (!anchored) return null;
    hour = Number.parseInt(anchored[1], 10);
    minute = 0;
  }

  if (hour > 23 || minute > 59) {
    throw new ScheduleParseError(
      `invalid clock time in schedule: ${hour}:${String(minute).padStart(2, '0')}`,
    );
  }

  // 12-hour disambiguation. Persian day-part words behave exactly as am/pm.
  const mentions = (words: readonly string[]) =>
    words.some((word) => new RegExp(`(?<![a-z])${escapeRe(word)}`).test(text));

  if (hour <= 12) {
    if (mentions(AFTERNOON)) {
      if (hour !== 12) hour += 12;
    } else if (mentions(MORNING)) {
      if (hour === 12) hour = 0;
    }
    // A bare "noon" at 12 is already 12:00, so nothing to adjust.
  }
  return [hour, minute];
}

function isPersian(text: string): boolean {
  return /[\u0600-\u06ff]/.test(text);
}

/** Extracts a day-of-week field, if the text names one. */
function readWeekday(text: string): string | null {
  const persian = isPersian(text);
  if (WEEKDAY_SCOPE.some((scope) => text.includes(scope))) {
    return persian ? IRANIAN_WORKDAYS : '1-5';
  }
  if (WEEKEND_SCOPE.some((scope) => text.includes(scope))) {
    return persian ? IRANIAN_WEEKEND : '0,6';
  }

  let remaining = text;
  const found: number[] = [];
  for (const name of WEEKDAY_ORDER) {
    const hit = ENGLISH_ABBREVIATIONS.has(name)
      ? new RegExp(`\\b${name}\\b`).test(remaining)
      : remaining.includes(name);
    const value = WEEKDAYS.get(name)!;
    if (hit && !found.includes(value)) {
      // Strip the match so "sunday" is not also counted as "sun".
      remaining = remaining.replaceAll(name, ' ');
      found.push(value);
    }
  }
  if (found.length === 0) return null;
  return found.sort((a, b) => a - b).join(',');
}

/** Extracts a day-of-month field from "first day of month" style phrasing. */
function readMonthDay(text: string): string | null {
  if (!MONTH_WORDS.some((word) => text.includes(word))) return null;

  let match = /\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:day|\u0631\u0648\u0632)/.exec(text);
  if (match && Number.parseInt(match[1], 10) >= 1 && Number.parseInt(match[1], 10) <= 31) {
    return match[1];
  }
  match = /(?:day|\u0631\u0648\u0632)\s+(\d{1,2})/.exec(text);
  if (match && Number.parseInt(match[1], 10) >= 1 && Number.parseInt(match[1], 10) <= 31) {
    return match[1];
  }
  for (const [word, value] of ORDINALS) {
    if (new RegExp(`(?<![${LETTER}])${escapeRe(word)}(?![${LETTER}])`).test(text)) {
      return String(value);
    }
  }
  return '1'; // "every month" alone means the first of the month
}

/**
 * Translates a natural-language schedule into a cron expression.
 *
 * @throws {ScheduleParseError} when nothing matches. Guessing is worse than
 * refusing: a schedule that fires at the wrong time is harder to notice than
 * one that was never created.
 */
export function nlToCron(input: string): string {
  const original = input;
  const text = normalise(input);
  if (!text) throw new ScheduleParseError('schedule text is empty');

  // A bare cron expression passes straight through, so one input box can take
  // either form without the user choosing a mode first.
  if (/^[\d*/,\- ]+$/.test(text) && text.split(' ').filter(Boolean).length === 5) {
    return validateCron(text);
  }

  const parsed = emptyParsed();
  const clock = readTime(text);

  // 1. Sub-daily intervals. These own the minute and hour fields outright.
  const minutes = findCount(text, MINUTE_WORDS);
  if (minutes !== null) {
    if (minutes < 1 || minutes > 59) {
      throw new ScheduleParseError(`minute interval must be between 1 and 59, got ${minutes}`);
    }
    return toCron({
      ...emptyParsed(),
      minute: minutes > 1 ? `*/${minutes}` : '*',
      hour: '*',
    });
  }

  const hours = findCount(text, HOUR_WORDS);
  // "every hour"/"هر ساعت" is an interval, but "هر روز ساعت ۹" uses ساعت as the
  // word "o'clock", so a clock reading wins over a bare hour interval.
  if (hours !== null && !(clock !== null && hours === 1)) {
    if (hours < 1 || hours > 23) {
      throw new ScheduleParseError(`hour interval must be between 1 and 23, got ${hours}`);
    }
    return toCron({
      ...emptyParsed(),
      minute: clock ? String(clock[1]) : '0',
      hour: hours > 1 ? `*/${hours}` : '*',
    });
  }

  // 2. Everything below fires at a specific time of day, defaulting to 00:00.
  if (clock !== null) {
    parsed.hour = String(clock[0]);
    parsed.minute = String(clock[1]);
  }

  // 3. Day scope, from most specific to least.
  const weekday = readWeekday(text);
  const monthDay = readMonthDay(text);
  const dayInterval = findCount(text, DAY_WORDS);

  if (weekday !== null) {
    parsed.weekday = weekday;
  } else if (monthDay !== null) {
    parsed.day = monthDay;
    if (YEAR_WORDS.some((word) => text.includes(word))) parsed.month = '1';
  } else if (YEAR_WORDS.some((word) => text.includes(word))) {
    parsed.day = '1';
    parsed.month = '1';
  } else if (WEEK_WORDS.some((word) => text.includes(word))) {
    parsed.weekday = '1'; // "weekly" with no named day means Monday
  } else if (dayInterval !== null && dayInterval > 1) {
    parsed.day = `*/${dayInterval}`;
  } else if (dayInterval !== null || clock !== null) {
    // daily at the given time
  } else {
    throw new ScheduleParseError(
      `could not understand schedule: '${original.trim()}'. ` +
        "Try phrasing such as 'every day at 9 AM' or 'every 15 minutes'.",
    );
  }

  return toCron(parsed);
}

/**
 * Documented examples, shown in the UI as placeholder hints and exercised
 * verbatim by the test suite. Mirrors `dream.nl_schedule.NL_EXAMPLES`.
 */
export const NL_EXAMPLES: ReadonlyArray<readonly [string, string]> = [
  ['every day at 9 AM', '0 9 * * *'],
  ['every weekday at 6 PM', '0 18 * * 1-5'],
  ['every monday at 10:30', '30 10 * * 1'],
  ['every 2 hours', '0 */2 * * *'],
  ['every first day of month', '0 0 1 * *'],
  ['every 15 minutes', '*/15 * * * *'],
  // Gloss: هر روز ساعت ۹ صبح — every day at 9 AM.
  [
    '\u0647\u0631 \u0631\u0648\u0632 \u0633\u0627\u0639\u062a \u06f9 \u0635\u0628\u062d',
    '0 9 * * *',
  ],
] as const;
