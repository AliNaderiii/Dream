# Space

A **Space** is a bounded room on this machine: a name, a folder linked **in
place** (never copied), an instruction document, and specialized agents that
each have one job.

## What v1 does

- Create, list, open, and archive spaces.
- Attach an existing folder through the workspace importer. `..` and symlink
  roots are refused.
- Five named roles: Secretary, Research, Data, Desk, Security. A role cannot
  raise its risk ceiling above the Space ceiling (`safe` or `guarded`).
- An instruction markdown file (or pasted text) becomes the role's how-to.
  Web URLs are refused while `DREAM_ALLOW_NETWORK` is off. Injection-shaped
  docs are quarantined and never become instructions.
- A natural-language rule (English or Persian) becomes an
  `APPROVAL_PENDING` draft. Nothing schedules, shells, or sends mail until
  you approve. Deny leaves the draft idle. Dangerous `!shell` never reaches
  a subprocess, even if you later approve.

Asking a role in v1 returns a **local briefing** from the instruction doc.
It does not call Aval, Earth Runtime, or any hosted model.

## What v1 does not claim

- Visual pipeline deploy, WisdomAI sirens, live eval trees.
- Wiring approved drafts into the live scheduler (`dream.cron`) — stored
  only.
- Computer-use or cloud VMs. Those stay out of Dream.

## Open the page

In the desktop app, open **Space** from the workspace group (`/space`).
Offline echo shows a seed Studio space so the page works without the
sidecar.
