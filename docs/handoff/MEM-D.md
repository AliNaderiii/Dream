# MEM-D — Stage D: /learn pipeline and autonomous proposals

**Date:** 2026-08-22
**Branch:** `arena/01a02a8d-dream` (on top of Gate C)
**Scope:** PR-2 (skills + learn), second half. Gate evidence: [`MEM-GATES.md`](./MEM-GATES.md) §Gate D.

## What was built

| Piece | File | Notes |
| --- | --- | --- |
| /learn kernel | `dream/skills/learn.py` | classify + load source; compose a normal-turn prompt; merge + KB bundle |
| Proposals | `dream/skills/propose.py` | opt-in, rate-limited, never in `--demo`; apply/discard |
| Tools | `dream/tools.py` | `save_skill_bundle`, `apply_skill_proposal` (guarded), `discard_skill_proposal` (safe) |
| Agent / CLI | `dream/agent.py`, `cli.py` | `/learn` is a normal turn; `Dream(demo=True)` for `--demo` |
| Tests | `tests/test_skills_learn.py` (11) | every source type, merge, KB split, proposals |

## Distillation honesty

`/learn` does **not** run a private ingestion model. It loads the source
(offline for path / conversation / notes; URL only when
`DREAM_ALLOW_NETWORK` is on), composes a standards-guided prompt
(templates, 60-char description, section order, merge instruction, KB
framing for large sources), and hands that string to `Dream.run` as the
user turn. The skill is written only when the model calls `edit_skill` or
`save_skill_bundle`, which are the Stage C approved write path.

## Sources

- **path** — workspace-relative file via `_safe_path`.
- **corpus** — directory of `.md`/`.txt` files; framed as a knowledge-base
  skill (`references/` + glossary when the bundle tool is used).
- **notes** — the rest of the `/learn` argument.
- **conversation** — current `Dream.history` user/assistant text.
- **url** — `read_page` after the network gate. Offline: bilingual
  fail-closed refusal; DNS and sockets are not touched.

## Merge-on-re-learn

`install_skill_bundle` / `save_skill_bundle` on an existing name folds the
new body under `## Updates` and records a new version. One skill remains.

## Proposals

- Opt-in: `DREAM_SKILL_PROPOSALS=1` (off by default).
- `Dream(demo=True)` and `DREAM_DEMO=1` never propose. `cli.run_demo`
  constructs `Dream(..., demo=True)`.
- Rate limit: one proposal per hour of process time.
- Complex turn: ≥ 2 tool calls or a message ≥ 400 characters. `/learn`
  turns are excluded.
- Apply is `guarded` (`apply_skill_proposal`); deny via policy or
  `discard_skill_proposal`. Nothing is written without approval.

## RF-4

No existing test edited. Suite only grows.

## Not in Stage D

Bridge `skills.*` RPCs and desktop UI remain Stage F.
