import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { echoWorkroomCreate, resetEchoWorkroom } from './echo-workroom';
import { workroomAddSeat, workroomApprove, workroomCreate, workroomDraft } from './workroom';

describe('workroom wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoWorkroom();
  });

  it('creates a company room that never sends and refuses YOLO', async () => {
    const client = getBridgeClient();
    expect(() => echoWorkroomCreate('Chaos', true)).toThrow(/YOLO/);
    const room = await workroomCreate(client, 'Studio Co');
    expect(room.mode).toBe('company');
    expect(room.sends).toBe(false);
    expect(room.yolo).toBe(false);
    expect(room.chrome_profile).toBe(false);
    expect(room.computer_use).toBe(false);
    const seat = await workroomAddSeat(client, room.room_id, 'Leila', 'manager', true);
    expect(seat.vip).toBe(true);
    expect(seat.can_send).toBe(false);
    const draft = await workroomDraft(client, room.room_id, 'Weekly note');
    const ready = await workroomApprove(client, draft.draft_id);
    expect(ready.status).toBe('ready');
    expect(ready.sent).toBe(false);
  });
});
