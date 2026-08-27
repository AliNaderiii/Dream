/** Deterministic echo runtime for bots.* */

export interface BotAvatar {
  shape: 'hex' | 'circle' | 'diamond' | 'square' | 'triangle';
  hue: 'teal' | 'amber' | 'rose' | 'slate' | 'violet';
}

export interface BotRecord {
  bot_id: string;
  space_id: string;
  name: string;
  role_id: string;
  model: string;
  avatar: BotAvatar;
  instruction: { text: string } | null;
  memory_user: string;
  yolo: false;
  archived: boolean;
}

const bots: BotRecord[] = [];

export function echoBotsCreate(
  spaceId: string,
  name: string,
  roleId = 'secretary',
  model = 'echo',
  yolo = false,
) {
  if (yolo) throw new Error('YOLO and Always Allow are refused for Space bots');
  if (model.includes('://')) throw new Error('model must be a short local id, not a URL');
  const bot_id = `bot_echo_${bots.length + 1}`;
  const record: BotRecord = {
    bot_id,
    space_id: spaceId,
    name,
    role_id: roleId,
    model,
    avatar: { shape: 'hex', hue: 'teal' },
    instruction: null,
    memory_user: `bot:${bot_id}`,
    yolo: false,
    archived: false,
  };
  bots.push(record);
  return record;
}

export function echoBotsList(spaceId: string) {
  const rows = bots.filter((row) => row.space_id === spaceId);
  return { bots: rows, count: rows.length, shapes: ['hex'], hues: ['teal'] };
}

export function resetEchoBots(): void {
  bots.length = 0;
}
