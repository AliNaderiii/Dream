import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { reportbotStart, reportbotStatus, reportbotStop } from './reportbot';

describe('reportbot bridge client (echo transport)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('start returns an honestly-flagged demo state in the browser preview', async () => {
    const client = getBridgeClient();
    expect(client.transportKind).toBe('echo');
    const status = await reportbotStart(client, '123456789:AAFakeEchoDemoToken_-abc123XYZ');
    expect(status.demo).toBe(true);
    expect(status.running).toBe(true);
    expect(status.token_fingerprint).toBe('…3XYZ');
    expect(status.events.map((e) => e.kind)).toContain('photo_report');
  });

  it('stop returns a stopped demo state with a stopped event', async () => {
    const client = getBridgeClient();
    const status = await reportbotStop(client);
    expect(status.demo).toBe(true);
    expect(status.running).toBe(false);
    expect(status.events.at(-1)?.kind).toBe('stopped');
  });

  it('status reports the idle demo state without inventing activity', async () => {
    const client = getBridgeClient();
    const status = await reportbotStatus(client);
    expect(status.demo).toBe(true);
    expect(status.running).toBe(false);
    expect(status.updates_processed).toBe(0);
    expect(status.events).toEqual([]);
  });

  it('demo events carry the full pipeline kinds (photo, voice, text)', async () => {
    const client = getBridgeClient();
    const status = await reportbotStart(client, '123456789:AAFakeEchoDemoToken_-abc123XYZ');
    const kinds = status.events.map((e) => e.kind);
    expect(kinds).toEqual(expect.arrayContaining(['photo_report', 'voice_report', 'text_report']));
  });
});
