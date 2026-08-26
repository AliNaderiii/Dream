import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { resetEchoRemote } from './echo-remotegw';
import { remotegwIssueToken, remotegwPreview, remotegwStatus } from './remotegw';

describe('remotegw wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoRemote();
  });

  it('uses echo and refuses WAN preview', async () => {
    const client = getBridgeClient();
    expect(client.transportKind).toBe('echo');
    const status = await remotegwStatus(client);
    expect(status.auth).toBe('bearer');
    expect(status.query_tokens).toBe(false);
    const preview = await remotegwPreview(client);
    expect(preview.token_in_qr).toBe(false);
    await expect(remotegwPreview(client, '8.8.8.8', true)).rejects.toThrow(/WAN/);
    const issued = await remotegwIssueToken(client, 'read', 'Phone');
    expect(issued.token).toBe('drm_EXAMPLE_not_a_real_key');
  });
});
