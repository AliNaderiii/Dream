import { beforeEach, describe, expect, it } from 'vitest';

import { botsCreate, botsList } from './bots';
import { getBridgeClient, resetBridgeClient } from './client';
import { resetEchoBots } from './echo-bots';

describe('bots wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoBots();
  });

  it('creates a named bot without YOLO', async () => {
    const client = getBridgeClient();
    const bot = await botsCreate(client, 'spc_1', 'Scribe');
    expect(bot.yolo).toBe(false);
    expect(bot.avatar.hue).not.toBe('blue');
    const listed = await botsList(client, 'spc_1');
    expect(listed.count).toBe(1);
  });
});
