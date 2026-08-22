/**
 * Tests for the ToolCard component (S07).
 *
 * Covers the four card states: ok, error, blocked, pending.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ToolCard } from '@/components/chat/tool-card';
import type { ToolCardEntry } from '@/types';

function makeCard(overrides: Partial<ToolCardEntry> = {}): ToolCardEntry {
  return {
    id: 'tc-1',
    name: 'calculate',
    argsSummary: '{"expression": "2+2"}',
    status: 'ok',
    resultExcerpt: '4',
    ...overrides,
  };
}

describe('ToolCard', () => {
  it('renders ok status with check icon and result excerpt', () => {
    render(<ToolCard card={makeCard({ status: 'ok', resultExcerpt: 'Result is 42' })} />);
    const card = screen.getByRole('article');
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'calculate — OK');
    expect(card).toHaveTextContent('calculate');
    expect(card).toHaveTextContent('OK');
    expect(card).toHaveTextContent('Result is 42');
  });

  it('renders error status with error label', () => {
    render(<ToolCard card={makeCard({ status: 'error', resultExcerpt: '' })} />);
    const card = screen.getByRole('article');
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'calculate — Error');
    expect(card).toHaveTextContent('Error');
  });

  it('renders blocked status with warning message', () => {
    render(<ToolCard card={makeCard({ status: 'blocked' })} />);
    const card = screen.getByRole('article');
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'calculate — Blocked');
    expect(card).toHaveTextContent('Blocked');
    expect(card).toHaveTextContent('Waiting for approval…');
  });

  it('renders pending status with running label', () => {
    render(<ToolCard card={makeCard({ status: 'pending' })} />);
    const card = screen.getByRole('article');
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'calculate — Running…');
    expect(card).toHaveTextContent('Running…');
  });

  it('renders args summary', () => {
    render(<ToolCard card={makeCard()} />);
    expect(screen.getByText('{"expression": "2+2"}')).toBeDefined();
  });

  it('does not render result excerpt for blocked status', () => {
    render(<ToolCard card={makeCard({ status: 'blocked', resultExcerpt: 'should not appear' })} />);
    expect(screen.queryByText('should not appear')).toBeNull();
  });

  it('exposes and toggles localized disclosure semantics', async () => {
    const user = userEvent.setup();
    render(<ToolCard card={makeCard()} />);
    const disclosure = screen.getByRole('button', { name: 'Hide details for calculate' });
    expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    expect(disclosure).toHaveAttribute('aria-controls', 'tool-tc-1-details');
    await user.click(disclosure);
    expect(screen.getByRole('button', { name: 'Show details for calculate' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.queryByText('{"expression": "2+2"}')).not.toBeInTheDocument();
  });
});
