import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoDialectic } from '@/lib/bridge/echo-dialectic';
import { resetEchoResearch } from '@/lib/bridge/echo-research';
import ResearchRoute from '@/routes/research';
import { useResearchStore } from '@/stores/research-store';

describe('Research & Dialectic Studio Route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoResearch();
    resetEchoDialectic();
    useResearchStore.setState({ view: 'list' });
  });

  it('renders research workbench and passes axe accessibility audit', async () => {
    const { container } = render(<ResearchRoute />);
    expect(await screen.findByRole('heading', { name: 'Research & Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sessions' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dialectic Studio' })).toBeInTheDocument();

    const report = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(report.violations).toEqual([]);
  });

  it('switches to Dialectic Studio view and performs a dialectic debate turn', async () => {
    const { container } = render(<ResearchRoute />);
    fireEvent.click(screen.getByRole('button', { name: 'Dialectic Studio' }));

    expect(
      await screen.findByRole('heading', { name: '3-Agent Dialectic Studio' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Detected Contradictions & Tensions' }),
    ).toBeInTheDocument();

    // Fill debate topic
    const topicInput = screen.getByLabelText('Debate Topic / Proposition');
    fireEvent.change(topicInput, { target: { value: 'Hybrid LLM Semantic Routing' } });

    const debateButton = screen.getByRole('button', { name: 'Run Dialectic Debate' });
    fireEvent.click(debateButton);

    expect(await screen.findByText(/Thesis \(Agent 1\)/i)).toBeInTheDocument();
    expect(await screen.findByText(/Antithesis \(Agent 2\)/i)).toBeInTheDocument();
    expect(await screen.findByText(/Synthesis \(Agent 3\)/i)).toBeInTheDocument();

    const report = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(report.violations).toEqual([]);
  });

  it('resets dialectic memory graph', async () => {
    render(<ResearchRoute />);
    fireEvent.click(screen.getByRole('button', { name: 'Dialectic Studio' }));

    const resetButton = await screen.findByRole('button', { name: 'Reset Dialectic Memory' });
    fireEvent.click(resetButton);

    expect(
      await screen.findByText('No beliefs recorded yet. Start a dialectic debate above.'),
    ).toBeInTheDocument();
  });
});
