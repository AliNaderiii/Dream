/** Debounces a rapidly-changing value (search boxes, sliders). */

import { useEffect, useState } from 'react';

/**
 * Returns `value` delayed by `delayMs`. The timer resets on every change, so
 * the debounced value settles only once the input has been quiet.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
