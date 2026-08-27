/** Deterministic echo runtime for groups.* */

export interface GroupTurn {
  round: number;
  bot_id: string;
  name: string;
  answer: string;
  hosted: false;
}

export interface GroupRun {
  group_id: string;
  space_id: string;
  bot_ids: string[];
  question: string;
  rounds: number;
  cap: 3;
  stopped: 'round_cap' | 'repeat';
  yolo: false;
  hosted: false;
  transcript: GroupTurn[];
}

const runs: GroupRun[] = [];

function requireIds(botIds: string[]): string[] {
  const cleaned = botIds.map((item) => item.trim()).filter(Boolean);
  if (cleaned.length < 2 || cleaned.length > 6) {
    throw new Error('bot_ids must be a list of 2 to 6 bot ids');
  }
  if (new Set(cleaned).size !== cleaned.length) {
    throw new Error('duplicate bot ids are refused');
  }
  return cleaned;
}

export function echoGroupsStart(spaceId: string, botIds: string[], question: string, yolo = false) {
  if (yolo) throw new Error('YOLO cannot run a bot group');
  const ids = requireIds(botIds);
  const prompt = question.trim();
  if (!prompt) throw new Error('question must be a non-empty string of at most 4000 characters');
  const transcript: GroupTurn[] = [];
  for (let round = 1; round <= 3; round += 1) {
    for (const botId of ids) {
      transcript.push({
        round,
        bot_id: botId,
        name: botId,
        answer: `Round ${round} · ${botId} · ${prompt.slice(0, 40)}`,
        hosted: false,
      });
    }
  }
  const run: GroupRun = {
    group_id: `grp_echo_${runs.length + 1}`,
    space_id: spaceId,
    bot_ids: ids,
    question: prompt,
    rounds: 3,
    cap: 3,
    stopped: 'round_cap',
    yolo: false,
    hosted: false,
    transcript,
  };
  runs.push(run);
  return run;
}

export function echoGroupsGet(groupId: string) {
  const row = runs.find((item) => item.group_id === groupId);
  if (!row) throw new Error('no group run');
  return row;
}

export function echoGroupsList(spaceId: string) {
  const rows = runs.filter((row) => row.space_id === spaceId);
  return {
    groups: rows.map((row) => ({
      group_id: row.group_id,
      space_id: row.space_id,
      bot_ids: row.bot_ids,
      question: row.question,
      rounds: row.rounds,
      cap: row.cap,
      stopped: row.stopped,
      yolo: row.yolo,
      hosted: row.hosted,
    })),
    count: rows.length,
  };
}

export function resetEchoGroups(): void {
  runs.length = 0;
}
