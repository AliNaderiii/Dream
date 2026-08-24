/**
 * SEC Stage B — echo-transport pin (no mocks): `security.status` is a real
 * wire method of the echo runtime and answers the safe default posture, so
 * the indicators stay hidden in browser-only mode.
 */

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { SecurityOffBanner } from '@/components/security/security-off-banner';
import { SecurityStatusIndicator } from '@/components/security/security-status-indicator';
import { getBridgeClient, resetBridgeClient } from '@/lib/bridge/client';

describe('security.status over the echo transport', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('answers the manual-mode default posture', async () => {
    const status = await getBridgeClient().call<Record<string, unknown>>('security.status');
    expect(status.mode).toBe('manual');
    expect(status.off_active).toBe(false);
    expect(status.floor).toBe('always-on');
  });

  it('keeps both indicators hidden in echo mode', async () => {
    const banner = render(<SecurityOffBanner />);
    const chip = render(<SecurityStatusIndicator />);
    // Give the effect one macrotask to fetch and settle on off_active=false.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(banner.container).toBeEmptyDOMElement();
    expect(chip.container).toBeEmptyDOMElement();
  });
});
