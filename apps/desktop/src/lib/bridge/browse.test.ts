import { beforeEach, describe, expect, it } from 'vitest';

import { browseApprove, browseDeny, browsePropose } from './browse';
import { getBridgeClient, resetBridgeClient } from './client';
import { echoBrowsePropose, resetEchoBrowse } from './echo-browse';

describe('browse wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoBrowse();
  });

  it('keeps a URL pending until allow once and refuses YOLO', async () => {
    const client = getBridgeClient();
    expect(() => echoBrowsePropose('https://example.com/', true)).toThrow(/YOLO/);
    expect(() => echoBrowsePropose('http://127.0.0.1/secret')).toThrow(/localhost|internal/);
    const draft = await browsePropose(client, 'https://example.com/notes');
    expect(draft.status).toBe('APPROVAL_PENDING');
    expect(draft.hosted_fetch).toBe(false);
    expect(draft.chrome_profile).toBe(false);
    expect(draft.computer_use).toBe(false);
    await browseDeny(client, draft.draft_id);
    const again = await browsePropose(client, 'https://example.com/notes');
    const fetched = await browseApprove(client, again.draft_id);
    expect(fetched.status).toBe('fetched');
    expect(fetched.hosted_fetch).toBe(false);
  });
});
