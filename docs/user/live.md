# Live loops

After you **approve** a Space draft, Live can **arm** it onto Dream's
scheduler. That is the Grok/monday idea of skill ≠ routine: the rule is
not a job until you say so.

## Rules

- Unapproved drafts are not armed.
- Dangerous `!shell` drafts are never scheduled, even if approved.
- Armed schedules keep `require_approval=True`. Every later fire waits
  for you. An unattended tick is denied.
- Role turns default to a **local briefing** from the instruction doc.
  A live hosted completion without `DREAM_ALLOW_NETWORK` and a real key
  is refused.
- The status bar follows **Settings → active provider**. A chat pane can
  still be Earth Runtime while the bar says Echo. The Live page and the
  bar chip say so out loud.

Open **Live** (`/live`) in the desktop app.
