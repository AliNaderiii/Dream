import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Progress } from './progress';

describe('Progress', () => {
  it('exposes progressbar semantics', () => {
    render(<Progress value={50} label="Loading" />);
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toHaveAttribute(
      'aria-valuenow',
      '50',
    );
  });
});
