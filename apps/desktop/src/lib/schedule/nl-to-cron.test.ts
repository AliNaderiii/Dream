import { describe, expect, it } from 'vitest';

import { validateCron } from '@/lib/schedule/cron';
import { normalizeFa } from '@/lib/schedule/normalize-fa';
import { NL_EXAMPLES, nlToCron, ScheduleParseError } from '@/lib/schedule/nl-to-cron';

/**
 * The table below is `NL_CASES` from `tests/test_scheduler.py`, copied
 * verbatim. Gate G7 asks for 20+ phrases including Persian, and the preview
 * this file guards is only useful if it agrees with the sidecar on every one
 * of them — so both suites assert against the same rows.
 */
const NL_CASES: ReadonlyArray<readonly [string, string]> = [
  // --- the six patterns named in the specification ---
  ['every day at 9 AM', '0 9 * * *'],
  ['every weekday at 6 PM', '0 18 * * 1-5'],
  ['every monday at 10:30', '30 10 * * 1'],
  ['every 2 hours', '0 */2 * * *'],
  ['every first day of month', '0 0 1 * *'],
  ['every 15 minutes', '*/15 * * * *'],
  // --- further English coverage ---
  ['every day at 9am', '0 9 * * *'],
  ['daily at midnight', '0 0 * * *'],
  ['every day at noon', '0 12 * * *'],
  ['every hour', '0 * * * *'],
  ['every 30 minutes', '*/30 * * * *'],
  ['every 5 minutes', '*/5 * * * *'],
  ['every 12 hours', '0 */12 * * *'],
  ['every 3 days at 7:15', '15 7 */3 * *'],
  ['every friday at noon', '0 12 * * 5'],
  ['every weekend at 8 AM', '0 8 * * 0,6'],
  ['every saturday at 11 PM', '0 23 * * 6'],
  ['every monday and thursday at 9', '0 9 * * 1,4'],
  ['every month on the 15th day', '0 0 15 * *'],
  ['every month on the 3rd day at 8 AM', '0 8 3 * *'],
  ['weekly at 5 PM', '0 17 * * 1'],
  ['every year', '0 0 1 1 *'],
  ['every business day at 07:45', '45 7 * * 1-5'],
  ['every day at 12 AM', '0 0 * * *'],
  ['every day at 12 PM', '0 12 * * *'],
  // --- Persian ---
  [
    '\u0647\u0631 \u0631\u0648\u0632 \u0633\u0627\u0639\u062a \u06f9 \u0635\u0628\u062d',
    '0 9 * * *',
  ],
  [
    '\u0647\u0631 \u0631\u0648\u0632 \u0633\u0627\u0639\u062a \u06f6 \u0639\u0635\u0631',
    '0 18 * * *',
  ],
  [
    '\u0647\u0631 \u062f\u0648\u0634\u0646\u0628\u0647 \u0633\u0627\u0639\u062a \u06f1\u06f0:\u06f3\u06f0',
    '30 10 * * 1',
  ],
  [
    '\u0647\u0631 \u0634\u0646\u0628\u0647 \u0633\u0627\u0639\u062a \u06f8 \u0635\u0628\u062d',
    '0 8 * * 6',
  ],
  ['\u0647\u0631 \u06f1\u06f5 \u062f\u0642\u06cc\u0642\u0647', '*/15 * * * *'],
  ['\u0647\u0631 \u06f2 \u0633\u0627\u0639\u062a', '0 */2 * * *'],
  [
    '\u0647\u0631 \u0631\u0648\u0632\u0647\u0627\u06cc \u06a9\u0627\u0631\u06cc \u0633\u0627\u0639\u062a \u06f9',
    '0 9 * * 6,0,1,2,3',
  ],
  ['\u0647\u0631 \u0627\u0648\u0644 \u0645\u0627\u0647', '0 0 1 * *'],
  ['\u0647\u0631 \u062c\u0645\u0639\u0647 \u0638\u0647\u0631', '0 12 * * 5'],
  ['\u0647\u0631 \u0646\u06cc\u0645\u0647 \u0634\u0628', '0 0 * * *'],
  ['\u0647\u0631 \u0633\u0627\u0639\u062a', '0 * * * *'],
  ['\u0647\u0631 \u0647\u0641\u062a\u0647', '0 0 * * 1'],
];

describe('nlToCron', () => {
  it.each(NL_CASES)('parses %j as %s', (text, expected) => {
    expect(nlToCron(text)).toBe(expected);
  });

  it('meets the gate: 20+ cases, 10+ of them Persian', () => {
    expect(NL_CASES.length).toBeGreaterThanOrEqual(20);
    const persian = NL_CASES.filter(([text]) => /[\u0600-\u06ff]/.test(text));
    expect(persian.length).toBeGreaterThanOrEqual(10);
  });

  it('emits only expressions the cron engine accepts', () => {
    for (const [text] of NL_CASES) {
      expect(() => validateCron(nlToCron(text))).not.toThrow();
    }
  });

  it('agrees with the documented examples', () => {
    for (const [text, expected] of NL_EXAMPLES) {
      expect(nlToCron(text)).toBe(expected);
    }
  });

  it('reads Persian and ASCII digits identically', () => {
    // Gloss: هر ۱۵ دقیقه — every 15 minutes.
    const persian = '\u0647\u0631 \u06f1\u06f5 \u062f\u0642\u06cc\u0642\u0647';
    expect(nlToCron(persian)).toBe(nlToCron('every 15 minutes'));
  });

  it('passes a bare cron expression straight through', () => {
    expect(nlToCron('0 9 * * *')).toBe('0 9 * * *');
    expect(nlToCron('*/10 * * * *')).toBe('*/10 * * * *');
  });

  it.each([
    [''],
    ['   '],
    ['sometime soon'],
    ['when I feel like it'],
    // Gloss: بعدا — later.
    ['\u0628\u0639\u062f\u0627'],
  ])('refuses to guess at %j', (text) => {
    expect(() => nlToCron(text)).toThrow(ScheduleParseError);
  });

  it('rejects out-of-range intervals', () => {
    expect(() => nlToCron('every 90 minutes')).toThrow(/between 1 and 59/);
    expect(() => nlToCron('every 40 hours')).toThrow(/between 1 and 23/);
  });

  it('rejects an impossible clock time', () => {
    expect(() => nlToCron('every day at 25:00')).toThrow(/invalid clock time/);
  });
});

describe('normalizeFa', () => {
  it('folds Persian and Arabic digits to ASCII', () => {
    expect(normalizeFa('\u06f1\u06f2\u06f3')).toBe('123');
    expect(normalizeFa('\u0660\u0661\u0662')).toBe('012');
  });

  it('unifies Arabic letter forms onto their Persian counterparts', () => {
    // Arabic yeh and kaf -> Farsi yeh and keheh.
    expect(normalizeFa('\u064a\u0643')).toBe('\u06cc\u06a9');
  });

  it('strips diacritics and turns ZWNJ into a space', () => {
    // Gloss: نیمه‌شب (midnight) with a ZWNJ, plus a fatha.
    expect(normalizeFa('\u0646\u06cc\u0645\u0647\u200c\u0634\u0628')).toBe(
      '\u0646\u06cc\u0645\u0647 \u0634\u0628',
    );
    expect(normalizeFa('\u0645\u064e\u0627\u0647')).toBe('\u0645\u0627\u0647');
  });

  it('collapses whitespace and trims', () => {
    expect(normalizeFa('  a   b  ')).toBe('a b');
    expect(normalizeFa('')).toBe('');
  });
});
