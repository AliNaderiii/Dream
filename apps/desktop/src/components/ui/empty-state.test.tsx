import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EmptyState } from './empty-state';

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(<EmptyState title="Nothing here" description="Try a different filter." />);
    expect(screen.getByRole('region', { name: 'Nothing here' })).toBeInTheDocument();
    expect(screen.getByText('Try a different filter.')).toBeInTheDocument();
  });
});
