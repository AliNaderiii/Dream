import { describe, expect, it } from 'vitest';

import {
  fuzzyScore,
  normalizeCommandText,
  searchCommands,
} from '@/components/shared/command-search';
import type { CommandItem } from '@/hooks/use-keyboard-shortcuts';

const commands: CommandItem[] = [
  { id: 'settings', description: 'Open Settings', category: 'Navigation', run: () => undefined },
  { id: 'memory', description: 'بازکردن حافظه', category: 'پیمایش', run: () => undefined },
  { id: 'session', description: 'Research notes', category: 'Sessions', run: () => undefined },
];

describe('command fuzzy search', () => {
  it('normalizes Persian presentation variants and diacritics', () => {
    expect(normalizeCommandText('يادگِيري')).toBe('یادگیری');
  });

  it('ranks exact substrings before loose subsequences', () => {
    expect(searchCommands(commands, 'settings').map((item) => item.id)).toEqual(['settings']);
    expect(fuzzyScore('rsn', 'research notes')).toBeLessThan(Number.POSITIVE_INFINITY);
  });

  it('searches Persian commands', () => {
    expect(searchCommands(commands, 'حافظه')[0]?.id).toBe('memory');
  });

  it('filters a thousand local commands under the interaction budget', () => {
    const fixture = Array.from({ length: 1000 }, (_, index): CommandItem => ({
      id: `command-${index}`,
      description: `Open local session ${index}`,
      category: 'Sessions',
      run: () => undefined,
    }));
    const started = performance.now();
    const result = searchCommands(fixture, 'session 999');
    const elapsed = performance.now() - started;
    expect(result[0]?.id).toBe('command-999');
    expect(elapsed).toBeLessThan(50);
  });
});
