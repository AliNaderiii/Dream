import { describe, expect, it } from 'vitest';

import {
  clockLabel,
  CronError,
  cronMatches,
  describeCron,
  nextRunAfter,
  parseCron,
  upcomingRuns,
  validateCron,
} from '@/lib/schedule/cron';

/** Local-time construction, matching the naive datetimes the sidecar uses. */
const at = (year: number, month: number, day: number, hour = 0, minute = 0): Date =>
  new Date(year, month - 1, day, hour, minute, 0, 0);

const sorted = (values: ReadonlySet<number>): number[] => [...values].sort((a, b) => a - b);

describe('parseCron', () => {
  it('expands every field to its value set', () => {
    const parsed = parseCron('*/15 9-17 * * 1-5');
    expect(sorted(parsed.minutes)).toEqual([0, 15, 30, 45]);
    expect(sorted(parsed.hours)).toEqual([9, 10, 11, 12, 13, 14, 15, 16, 17]);
    expect(sorted(parsed.weekdays)).toEqual([1, 2, 3, 4, 5]);
  });

  it('accepts both Sunday encodings', () => {
    expect(sorted(parseCron('0 0 * * 0').weekdays)).toEqual(
      sorted(parseCron('0 0 * * 7').weekdays),
    );
  });

  it('handles a wrapping weekday range', () => {
    expect(sorted(parseCron('0 0 * * 5-1').weekdays)).toEqual([0, 1, 5, 6]);
  });

  it('normalises surrounding whitespace', () => {
    expect(validateCron('  0   9 * * *  ')).toBe('0 9 * * *');
  });

  it.each([
    ['', 'no fields'],
    ['0 9 * *', 'too few fields'],
    ['0 9 * * * *', 'too many fields'],
    ['60 9 * * *', 'minute out of range'],
    ['0 24 * * *', 'hour out of range'],
    ['0 9 32 * *', 'day out of range'],
    ['0 9 * 13 *', 'month out of range'],
    ['0 9 * * 8', 'weekday out of range'],
    ['abc 9 * * *', 'non-numeric'],
    ['0 9 * * 1-', 'dangling range'],
    ['*/0 * * * *', 'zero step'],
    ['0 9 5-2 * *', 'reversed range'],
  ])('rejects %j (%s)', (expression) => {
    expect(() => parseCron(expression)).toThrow(CronError);
  });
});

describe('cronMatches', () => {
  it('matches only the configured minute', () => {
    expect(cronMatches('30 10 * * *', at(2026, 3, 4, 10, 30))).toBe(true);
    expect(cronMatches('30 10 * * *', at(2026, 3, 4, 10, 31))).toBe(false);
  });

  it('applies the Vixie OR rule when day and weekday are both restricted', () => {
    // 2026-03-01 is a Sunday; 2026-03-02 is a Monday.
    expect(cronMatches('0 0 1 * 1', at(2026, 3, 1))).toBe(true); // day matches
    expect(cronMatches('0 0 1 * 1', at(2026, 3, 2))).toBe(true); // weekday matches
    expect(cronMatches('0 0 1 * 1', at(2026, 3, 3))).toBe(false); // neither
  });

  it('ANDs day and weekday when only one is restricted', () => {
    expect(cronMatches('0 0 2 * *', at(2026, 3, 2))).toBe(true);
    expect(cronMatches('0 0 2 * *', at(2026, 3, 3))).toBe(false);
  });
});

describe('nextRunAfter', () => {
  it('is strictly after the reference instant', () => {
    const next = nextRunAfter('0 9 * * *', at(2026, 3, 4, 9, 0));
    expect(next).toEqual(at(2026, 3, 5, 9, 0));
  });

  it('rolls into the next day', () => {
    expect(nextRunAfter('0 9 * * *', at(2026, 3, 4, 10, 0))).toEqual(at(2026, 3, 5, 9, 0));
  });

  it('finds the next weekday occurrence', () => {
    // Saturday 2026-03-07 → Monday 2026-03-09.
    expect(nextRunAfter('0 18 * * 1-5', at(2026, 3, 7, 12, 0))).toEqual(at(2026, 3, 9, 18, 0));
  });

  it('crosses a year boundary for a yearly schedule', () => {
    expect(nextRunAfter('0 0 1 1 *', at(2026, 6, 1, 0, 0))).toEqual(at(2027, 1, 1, 0, 0));
  });

  it('throws for an expression that never fires', () => {
    expect(() => nextRunAfter('0 0 30 2 *', at(2026, 1, 1))).toThrow(/never fires/);
  });

  it('returns ascending, distinct upcoming runs', () => {
    const runs = upcomingRuns('0 */6 * * *', 4, at(2026, 3, 4, 1, 0));
    expect(runs).toEqual([
      at(2026, 3, 4, 6, 0),
      at(2026, 3, 4, 12, 0),
      at(2026, 3, 4, 18, 0),
      at(2026, 3, 5, 0, 0),
    ]);
  });
});

describe('clockLabel', () => {
  it.each([
    [0, 0, '12:00 AM'],
    [9, 0, '9:00 AM'],
    [12, 0, '12:00 PM'],
    [13, 5, '1:05 PM'],
    [23, 59, '11:59 PM'],
  ])('renders %i:%i as %s', (hour, minute, expected) => {
    expect(clockLabel(hour, minute)).toBe(expected);
  });
});

describe('describeCron', () => {
  // These readings must agree with `dream.cron.describe_cron`, which produces
  // the `human` field the sidecar returns for the same expressions.
  it.each([
    ['0 9 * * *', 'every day at 9:00 AM'],
    ['0 18 * * 1-5', 'every weekday at 6:00 PM'],
    ['30 10 * * 1', 'every Monday at 10:30 AM'],
    ['0 */2 * * *', 'every 2 hours'],
    ['0 0 1 * *', 'on the 1st at 12:00 AM'],
    ['*/15 * * * *', 'every 15 minutes'],
    ['0 8 * * 0,6', 'every weekend day at 8:00 AM'],
    ['0 9 * * 6,0,1,2,3', 'every Iranian working day (Sat–Wed) at 9:00 AM'],
    ['15 7 */3 * *', 'every 3 days at 7:15 AM'],
    ['0 0 1 1 *', 'on the 1st in January at 12:00 AM'],
    ['* * * * *', 'every minute'],
    ['0 9 * * 1,4', 'every Monday and Thursday at 9:00 AM'],
  ])('describes %s as %j', (expression, expected) => {
    expect(describeCron(expression)).toBe(expected);
  });

  it('falls back to a literal reading for expressions it cannot phrase', () => {
    expect(describeCron('0 9-17 * * *')).toBe('at cron schedule 0 9-17 * * *');
  });
});
