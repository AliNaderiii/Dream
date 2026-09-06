/**
 * Reminder authoring helpers (P-13) — pure, deterministic unit tests.
 */

import { describe, expect, it } from 'vitest';

import {
  MAX_REMINDER_CHARS,
  isOneOff,
  oneOffCron,
  oneOffParts,
  reminderPrompt,
  validateOneOff,
  validateReminderText,
} from './reminder-model';

describe('oneOffCron', () => {
  it('compiles a date and time into a cron expression', () => {
    expect(oneOffCron('2027-03-20', '09:30')).toBe('30 9 20 3 *');
    expect(oneOffCron('2027-12-01', '00:00')).toBe('0 0 1 12 *');
    expect(oneOffCron('2027-01-31', '23:59')).toBe('59 23 31 1 *');
  });

  it('refuses malformed input instead of guessing', () => {
    expect(() => oneOffCron('', '09:30')).toThrow();
    expect(() => oneOffCron('2027-03-20', '')).toThrow();
    expect(() => oneOffCron('next tuesday', '09:30')).toThrow();
  });
});

describe('oneOffParts', () => {
  it('round-trips a compiled one-off back into date and time fields', () => {
    const parts = oneOffParts('30 9 20 3 *');
    expect(parts).not.toBeNull();
    expect(parts?.time).toBe('09:30');
    expect(parts?.date.endsWith('-03-20')).toBe(true);
  });

  it('returns null for expressions that are not a plain one-off', () => {
    expect(oneOffParts('0 9 * * *')).toBeNull();
    expect(oneOffParts('*/15 * * * *')).toBeNull();
    expect(oneOffParts('0 9 1,15 * *')).toBeNull();
    expect(oneOffParts('')).toBeNull();
  });
});

describe('isOneOff', () => {
  it('requires both max_runs = 1 and a one-off cron shape', () => {
    expect(isOneOff(1, '30 9 20 3 *')).toBe(true);
    expect(isOneOff(null, '30 9 20 3 *')).toBe(false);
    expect(isOneOff(1, '0 9 * * *')).toBe(false);
  });
});

describe('validateOneOff', () => {
  it('accepts a future moment', () => {
    const now = new Date(2027, 2, 19, 12, 0); // 2027-03-19
    expect(validateOneOff('2027-03-20', '09:30', now)).toBeNull();
  });

  it('rejects a past moment before anything is persisted', () => {
    const now = new Date(2027, 2, 19, 12, 0);
    expect(validateOneOff('2027-03-19', '09:30', now)).toBe('previewInvalidDate');
    // The same clock time one day earlier is equally past.
    expect(validateOneOff('2026-01-01', '00:00', now)).toBe('previewInvalidDate');
  });

  it('rejects malformed values', () => {
    const now = new Date(2027, 2, 19, 12, 0);
    expect(validateOneOff('20/03/2027', '09:30', now)).toBe('previewInvalidDate');
    expect(validateOneOff('2027-03-20', '9:30', now)).toBe('previewInvalidDate');
    expect(validateOneOff('2027-13-40', '09:30', now)).toBe('previewInvalidDate');
  });
});

describe('validateReminderText', () => {
  it('requires a non-empty, bounded text', () => {
    expect(validateReminderText('renew the insurance')).toBe(true);
    expect(validateReminderText('   ')).toBe(false);
    expect(validateReminderText('x'.repeat(MAX_REMINDER_CHARS + 1))).toBe(false);
    expect(validateReminderText('x'.repeat(MAX_REMINDER_CHARS))).toBe(true);
  });
});

describe('reminderPrompt', () => {
  it('prefixes the text in the active language', () => {
    expect(reminderPrompt('renew', 'en')).toBe('Reminder: renew');
    expect(reminderPrompt('تمدید بیمه', 'fa')).toBe('یادآوری: تمدید بیمه');
  });

  it('trims the text so the stored prompt is clean', () => {
    expect(reminderPrompt('  spaced  ', 'en')).toBe('Reminder: spaced');
  });
});
