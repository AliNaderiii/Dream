import { act, fireEvent, render, screen } from '@testing-library/react';
import axe from 'axe-core';
import { beforeEach, describe, expect, it } from 'vitest';

import { VoiceStudio } from '@/components/live/voice-studio';
import { resetBridgeClient } from '@/lib/bridge/client';

describe('VoiceStudio component', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders voice studio with accessible headings and buttons', async () => {
    const { container } = render(<VoiceStudio />);
    expect(screen.getByRole('heading', { name: /استودیوی صوتی دوبلکس زنده/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /شروع مکالمه زنده/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /قطع آنی دستی/i })).toBeDisabled();

    const report = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(report.violations).toEqual([]);
  });

  it('handles start, mute toggle, barge-in, export transcript, and stop', async () => {
    render(<VoiceStudio />);

    const startBtn = screen.getByRole('button', { name: /شروع مکالمه زنده/i });
    act(() => {
      fireEvent.click(startBtn);
    });

    expect(await screen.findByRole('button', { name: /قطع تماس صوتی/i })).toBeInTheDocument();

    const muteBtn = screen.getByRole('button', { name: /میکروفون فعال/i });
    act(() => {
      fireEvent.click(muteBtn);
    });
    expect(screen.getByRole('button', { name: /میکروفون قطع است/i })).toBeInTheDocument();

    const bargeInBtn = screen.getByRole('button', { name: /قطع آنی دستی/i });
    act(() => {
      fireEvent.click(bargeInBtn);
    });

    const transcriptBtn = screen.getByRole('button', { name: /متن مکالمه/i });
    act(() => {
      fireEvent.click(transcriptBtn);
    });

    expect(await screen.findByText(/گزارش مکالمه صوتی زنده/i)).toBeInTheDocument();

    const stopBtn = screen.getByRole('button', { name: /قطع تماس صوتی/i });
    act(() => {
      fireEvent.click(stopBtn);
    });

    expect(await screen.findByRole('button', { name: /شروع مکالمه زنده/i })).toBeInTheDocument();
  });
});
