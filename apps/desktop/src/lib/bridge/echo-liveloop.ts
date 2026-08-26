/** Deterministic echo runtime for liveloop.* */

export interface RouteSnapshot {
  bar_provider: string;
  pane_provider: string | null;
  pane_model: string | null;
  echo_bar: boolean;
  mismatch: boolean;
  honest: boolean;
  note_en: string;
  note_fa: string;
}

export function echoRouteSnapshot(bar = 'echo', pane?: string, model?: string): RouteSnapshot {
  const echoBar = bar.toLowerCase().includes('echo');
  const mismatch = Boolean(pane && pane.toLowerCase() !== bar.toLowerCase() && echoBar);
  return {
    bar_provider: bar,
    pane_provider: pane ?? null,
    pane_model: model ?? null,
    echo_bar: echoBar,
    mismatch,
    honest: !mismatch,
    note_en: mismatch
      ? 'The status bar follows Settings → active provider. A chat pane can use another model. This bar is not the pane.'
      : 'Status bar and the declared pane agree, or no pane was declared.',
    note_fa: mismatch
      ? 'نوار وضعیت از ارائه‌دهندهٔ تنظیمات پیروی می‌کند. پنل چت می‌تواند مدل دیگری باشد.'
      : 'نوار وضعیت و پنل اعلام‌شده هم‌خوان‌اند، یا پنلی اعلام نشده.',
  };
}

export function echoArmDraft(draftId: string, approved = false) {
  if (!approved) throw new Error('missing approver — refuse');
  if (!draftId.trim()) throw new Error('draft_id must be a non-empty string');
  if (draftId.includes('danger')) throw new Error('dangerous shell drafts are never scheduled');
  return {
    draft_id: draftId,
    armed: true,
    spawned: false,
    require_approval: true,
    schedule: {
      schedule_id: 'sch_echo_live',
      cron_expression: '0 9 * * *',
      require_approval: true,
      enabled: true,
    },
  };
}

export function echoRoleTurn(spaceId: string, roleId: string, question: string, live = false) {
  if (live) throw new Error('live role turns need DREAM_ALLOW_NETWORK and a configured key');
  if (!question.trim())
    throw new Error('question must be a non-empty string of at most 4000 characters');
  return {
    space_id: spaceId,
    role: { role_id: roleId, effective_ceiling: 'safe' },
    question,
    hosted: false,
    live: false,
    live_reason: 'local briefing; live hosted turn was not requested',
    answer: `${roleId}: ${question}\nStay local. Never send mail.`,
  };
}

export function resetEchoLiveloop(): void {
  /* echo helpers are stateless */
}
