# MEM-C — Stage C: Skills v2 runtime (in-place upgrade)

**Date:** 2026-08-22
**Branch:** `arena/01a02a8d-dream` (base `c664d54`, the PR-1 squash of Stages A+B)
**Scope:** PR-2 (skills + learn), first half. Gate evidence: [`MEM-GATES.md`](./MEM-GATES.md) §Gate C.
**Owner architect:** MNEMOSYNE · **Implementation:** SA-2 DAEDALUS (runtime) with SA-5 VERITAS (tests)

## What was built

| Piece | File | Notes |
| --- | --- | --- |
| SKILL.md parser + templates | `dream/skills/format.py` | agentskills.io frontmatter, house 60-char description, EN/FA templates |
| Cached bounded registry | `dream/skills/registry.py` | scans `skills/*.txt` and `skills/<name>/SKILL.md`; dirty + mtime cache |
| Version / use ledger | `dream/skills/store.py` | SQLite, `BEGIN IMMEDIATE` + RLock + `busy_timeout`; `DREAM_SKILLS_DB` |
| Slash stacking | `dream/skills/slash.py` | up to 5 leading skill tokens; path-like args never swallowed |
| In-place wiring | `dream/skills/__init__.py` | `load_skills` now uses the registry; v1 `save_skill` preserved |
| Tools | `dream/tools.py` | `skill_view` (safe), `edit_skill` / `delete_skill` (guarded) |
| Agent / CLI | `dream/agent.py`, `cli.py` | catalog in system prompt; slash through `Dream.run` and CLI |
| Tests | `tests/test_skills_v2.py` (23) | Gate C properties; zero edits to existing tests |

## Integration honesty — preserved, extended, migrated

Stage C upgrades the existing skills system **in place**. A second parallel
runtime was treated as a defect and was not built.

### Preserved (byte-compatible)

- **v1 file format.** `save_skill` still writes `skills/<name>.txt` with
  `name:` / `description:` / `steps:` (Latin labels).
  `test_saved_skill_file_is_human_readable` is unmodified and still pins the
  exact file text.
- **v1 overwrite-as-correction.** Saving the same `.txt` name updates the
  current file (`test_saving_the_same_name_updates_the_file`). The new rule
  "no automatic overwrites" applies to the *version ledger* (append-only
  rows) and to v2 `save_skill_md` (refuses if the SKILL.md already exists
  unless `edit_skill` / `replace=True`).
- **Matching.** `find_skill` / `score_skills` / `use_skill` still match on
  name+description through `normalize_fa`, the stemmer, and the synonym
  index. Steps are still not part of the matching surface.
- **`SkillPromptProvider.contribute_prompt`.** Still returns exactly
  `SKILLS_USAGE` (or empty when over budget).
  `test_skill_prompt_provider_honours_the_budget` is unmodified.
- **Save-claim guard, reserved names, step coercion, teaching transcript.**
  Untouched.
- **Risk tiers.** `save_skill` stays `guarded` and is still auto-approved by
  the default `ApprovalPolicy`. Denial is available through the existing
  policy (`always_ask` includes `guarded`) and fails closed.
- **Bridge protocol.** Untouched (Stage F wires `skills.*`).

### Extended

- **`Skill` dataclass.** Three optional fields (`body`, `slash`, `kind`) with
  defaults, so every existing `Skill(name, description, steps, filename)`
  construction still works.
- **`load_skills`.** Same `(skills, problems)` contract; now also returns
  valid `SKILL.md` directories and reports their failures as `SkillProblem`
  (bilingual). One broken file still never drops the others.
- **Cache.** The module docstring used to say "nothing is cached". The
  registry is now cached and bounded, but a hand edit still takes effect on
  the next use: the cache key is `(path, mtime_ns, size)` and writers mark
  dirty. `test_hand_edit_takes_effect_on_next_use` (v1) and
  `test_hand_edit_still_busts_the_registry_cache` (v2) pin this.
- **System prompt.** After the unchanged `SKILLS_USAGE` line, Dream appends a
  **catalog** of `/{slash} — {description}` under
  `SKILL_CATALOG_BUDGET_CHARS` (8,000). Bodies never enter that catalog.
- **CLI / `Dream.run`.** A leading stack of installed skill slashes is
  parsed by one function and forwarded into the agent turn (bridge
  `conversation.send` already calls `Dream.run`). Reserved commands
  (`/skill`, `/help`, …) keep their existing meaning.

### Migrated

Nothing was deleted or renamed. v1 `.txt` skills remain first-class. v2
`SKILL.md` skills sit beside them in the same `skills/` directory.

### RF-4

**No existing test was edited or deleted.** The 23 new tests live in a new
file. Suite only grows.

## Design decisions

### 1. House description cap is 60, not 1024

The public spec allows 1,024 characters. The catalog is name+description for
every installed skill, so Dream enforces 60 with a bilingual, actionable
error. Documented here so it is not mistaken for a parser bug.

### 2. Name rules are format-specific

v2 `name` is agentskills.io hyphen-case (`^[a-z0-9]+(?:-[a-z0-9]+)*$`, ≤ 64,
must match the parent folder). v1 names stay as they are (Persian allowed);
their slash token is a hyphenated fold of the name so every installed skill
is still a slash command.

### 3. Progressive disclosure

- System catalog: name + description only.
- `skill_view` (safe) returns the body on demand.
- Slash invocation injects bodies into the **user** turn, never the system
  prompt, so a scripted session can prove the body is absent from every
  system prompt until `skill_view` (and remains absent from the system
  prompt even after a slash).

### 4. Version / use store

`data/dream-skills.db` (`DREAM_SKILLS_DB`). Same serialization as Stages A/B.
`record_version` inserts a new `(name, version)` row; identical content is a
no-op, never an UPDATE. Use rows are append-only (`invoked` / `success` /
`error` / `deleted`).

**Ledger lifecycle (hang root cause and fix).** An early draft kept a
process-global `SkillLedger` singleton so every `get_ledger()` returned the
same live `sqlite3` connection. Pytest workers that use `multiprocessing`
inherit that connection after fork; the child then contends for the same
SQLite file lock the parent still holds, and the full suite hangs. The
shipped API returns a **fresh** `SkillLedger.from_env()` on every
`get_ledger()` call. Product call sites open it as a short-lived context
manager (`with get_ledger() as ledger:`) so `__exit__` closes the
connection immediately. `reset_ledger_for_tests()` is a no-op kept only so
existing fixtures still import it. Callers that need several operations on
one handle construct `SkillLedger` themselves and close it.

### 5. Write approval

`save_skill`, `edit_skill`, and `delete_skill` are `guarded`. The existing
`ApprovalPolicy` is the gate. A policy that puts `guarded` in `always_ask`
and whose `ask` returns false blocks the write; the file is not created
(`test_write_approval_denial_fails_closed`).

## Guardrail compliance

- Zero new runtime dependencies (stdlib YAML-subset parser, sqlite3).
- Single normalizer: `dream.skills.registry.normalize_fa is dream.memory.normalize_fa`.
- Persian literals in product code are `\u` escapes.
- No asserts inside `if` in `test_*` functions.
- Bridge protocol and desktop untouched.
- No telemetry.

## Not in Stage C

- `/learn` pipeline and post-task proposals — Stage D.
- Bridge `skills.*` RPCs and desktop UI — Stage F.
