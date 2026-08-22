import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MATRIX_SIZE, ThemeMatrix } from '@/stories/theme-matrix';

describe('Ladle theme matrix', () => {
  it('covers three themes, two directions, and two densities', () => {
    render(
      <ThemeMatrix>
        <button type="button">Control</button>
      </ThemeMatrix>,
    );

    const cells = screen.getAllByTestId('theme-cell');
    expect(cells).toHaveLength(MATRIX_SIZE);
    expect(new Set(cells.map((cell) => cell.dataset['theme']))).toEqual(
      new Set(['light', 'warm', 'dark']),
    );
    expect(new Set(cells.map((cell) => cell.dir))).toEqual(new Set(['ltr', 'rtl']));
    expect(new Set(cells.map((cell) => cell.dataset['density']))).toEqual(
      new Set(['comfortable', 'dense']),
    );
  });
});
