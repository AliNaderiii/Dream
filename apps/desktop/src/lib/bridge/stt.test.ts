import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { sttTranscribe } from './stt';

describe('stt bridge client (echo transport)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('returns an honestly-flagged demo result in the browser preview', async () => {
    const client = getBridgeClient();
    expect(client.transportKind).toBe('echo');
    const result = await sttTranscribe(client, 'C:\\Users\\alina\\voice.oga');
    expect(result.demo).toBe(true);
    expect(result.success).toBe(true);
    expect(result.available).toBe(false);
    expect(result.engine).toBeNull();
    expect(result.note).toContain('faster-whisper');
  });

  it('rejects an empty file path before touching the transport', async () => {
    const client = getBridgeClient();
    await expect(sttTranscribe(client, '   ')).rejects.toThrow('file path must not be empty');
  });

  it('carries the requested language through the demo result', async () => {
    const client = getBridgeClient();
    const result = await sttTranscribe(client, 'voice.oga', 'en');
    expect(result.language).toBe('en');
  });
});
