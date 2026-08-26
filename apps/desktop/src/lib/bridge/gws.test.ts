import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { resetEchoGws } from './echo-gws';
import { gwsDisconnect, gwsOauthBegin, gwsOauthComplete, gwsStatus } from './gws';

describe('gws wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoGws();
  });

  it('connects on loopback and refuses a WAN redirect paste', async () => {
    const client = getBridgeClient();
    const started = await gwsOauthBegin(client);
    expect(started.redirect_uri.startsWith('http://127.0.0.1:')).toBe(true);
    await gwsOauthComplete(client, started.state, 'code-ok');
    expect((await gwsStatus(client)).connected).toBe(true);
    await expect(
      gwsOauthComplete(client, started.state, 'https://evil.example/callback?code=x'),
    ).rejects.toThrow(/loopback/);
    await gwsDisconnect(client);
    expect((await gwsStatus(client)).connected).toBe(false);
  });
});
