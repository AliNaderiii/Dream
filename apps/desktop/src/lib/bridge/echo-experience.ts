/** Deterministic echo runtime for experience.* */

export interface ExperienceDraft {
  draft_id: string;
  bot_id: string;
  name: string;
  status: 'APPROVAL_PENDING' | 'created' | 'denied';
  yolo: false;
}

const drafts: ExperienceDraft[] = [];

export function echoExperienceCapture(botId: string, _question: string, yolo = false) {
  if (yolo) throw new Error('YOLO cannot auto-write skills from experience');
  const draft: ExperienceDraft = {
    draft_id: `exp_echo_${drafts.length + 1}`,
    bot_id: botId,
    name: 'scribe',
    status: 'APPROVAL_PENDING',
    yolo: false,
  };
  drafts.push(draft);
  return draft;
}

export function echoExperienceList(botId?: string) {
  const rows = botId ? drafts.filter((row) => row.bot_id === botId) : drafts;
  return { drafts: rows, count: rows.length };
}

export function echoExperienceApprove(draftId: string, approved = false) {
  if (!approved) throw new Error('missing approver — refuse');
  const index = drafts.findIndex((row) => row.draft_id === draftId);
  if (index < 0) throw new Error('no experience draft');
  const [row] = drafts.splice(index, 1);
  return { applied: true, draft_id: draftId, name: row.name, status: 'created' };
}

export function echoExperienceDeny(draftId: string) {
  const index = drafts.findIndex((row) => row.draft_id === draftId);
  if (index < 0) throw new Error('no experience draft');
  const [row] = drafts.splice(index, 1);
  return { applied: false, draft_id: draftId, name: row.name, status: 'denied' };
}

export function resetEchoExperience(): void {
  drafts.length = 0;
}
