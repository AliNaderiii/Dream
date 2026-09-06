# P-14 Synthesis Report — Projects Dashboard & Workspace Isolation

> Status: **awaiting PM approval**. No production file has been edited. This
> report is the synthesis-gate artifact required before implementation.

- Base main SHA: `c05b32839ea6c1680a7d0f06ec30529def385e7f`
  (`feat(memory): add reminder authoring on the existing scheduler (P-13) (#127)`)
- Working branch `arena/01a076b5-dream` is clean and identical to `origin/main`
  at that SHA (verified via `git fetch` + `git rev-parse origin/main`).
- Verified baselines on this checkout (all executed, none assumed):
  - `python -m pytest -q` → **3469 passed, 16 skipped**
  - `python -m ruff check .` → **All checks passed**
  - `npm run typecheck` → clean
  - `npm run test` → **751 passed (110 files)**
  - `tools/check_locales.py` → PASS (8 locales × 30 namespaces, fa gate PASS)
- `v0.4.7` does not exist and will not be created.

---

## 1. Current project architecture (Agent A)

Two independent project stores exist, **both writing the same file by default**
(`data/bridge_projects.json`, override `DREAM_PROJECTS_PATH`):

```
S06 surface (authoritative CRUD)                Projects 2.0 overlay
dream/bridge/methods.py                          dream/workspace/projects.py
  project.create/list/get/update/delete            ProjectOverlay.adopt()
  project.add_session/remove_session               .settings() .move_session()
  in-memory dict + _save_projects_index()          read-modify-write per call
  atomic tmp+os.replace, best-effort               atomic tmp+os.replace,
                                                   best-effort
```

- A project = `{id, name, folder, session_ids, created_at, updated_at}`;
  folder is a **path reference only** — nothing is ever copied
  (`imported_in_place: true, copied: false` overlay fields).
- Delete ungroups sessions; it never deletes conversations or files.
- One-project-per-session is enforced on `project.add_session`.
- Workspace roots live separately in `dream/workspace/registry.py`
  (`data/workspace_registry.json`), also pointer-only, atomic writes.
- Sessions: `session.list`/`session.create` in `methods.py`; grouping only via
  `project.session_ids`. No tenancy — single local user by design.

### Data-flow / state machine

```
React routes/projects.tsx ── lib/bridge/projects.ts ── project.*  ──► methods.py dict ──► bridge_projects.json
React workspace-shell.tsx ── lib/bridge/workspace.ts ── workspace.* ─► WorkspaceService ─► registry / overlay / files
(echo transports mirror both families deterministically for dev/vitest)
```

## 2. Project / session / memory / provenance relationships

- Session ↔ project: via `session_ids`; sessions are never mutated.
- Provenance (`dream/provenance/models.py`) has **no project field**; records
  reach a project only transitively through the session grouping. Adding a
  project_id to the sealed, hash-chained `ProvenanceRecord` would break the
  chain format → **explicitly out of scope** (architecture does not support it
  without a migration; documented as a PM decision, see §12).
- Memory has no project scoping today; project settings (`default_mode`,
  `language`) exist only in the overlay.

## 3. Workspace & path-safety threat model (Agent B)

Enforced today in `dream/workspace/paths.py` + `files.py` + `preview.py`:

| Threat | Defense | Status |
|---|---|---|
| `..` traversal | `relative_key` rejects any `..` segment | tested |
| Absolute / drive escape | leading `/` or `X:` refused | tested |
| Encoded traversal | JSON-RPC delivers literal text; `%2e%2e` is a plain name, never decoded | safe by construction |
| Symlink root | `normalize_root` refuses symlink roots | tested |
| Symlink escape inside root | `resolve()` + `relative_to` + per-segment symlink walk | tested |
| Windows junctions | `resolve()` follows junctions → `relative_to` check catches escape even where `is_symlink()` misses reparse points (< Py 3.12) | covered, untested |
| Null bytes / oversize path | refused (`\x00`, > 4096 chars) | tested |
| Unbounded listing | `LIST_CAP = 200`, cursor pagination | tested |
| Unbounded read | preview capped 64 KiB / 24 000 chars; notebooks 128 KiB | tested |
| Recursion | listings are single-level; only path length bounds segment depth | **gap: no explicit segment cap** |
| Binary decoded as text | only whitelisted suffixes decoded; **gap:** a binary file named `.txt` is decoded with `errors="replace"` | gap |
| HTML/script execution | previews sanitized, `executed: false` always | tested |
| Secrets in preview | `redact()` regex on text/csv/notebook previews | tested |
| Shell from file browser | impossible — preview path has no exec; `!shell` is separately approval-gated | verified |

## 4. Authorization matrix (Agent D)

Single-user local sidecar; every RPC is same-user. The relevant boundaries:

| Method family | Validation | Boundary |
|---|---|---|
| `project.*` (7) | `invalid_params` typing; **gap: no length cap on `name`, no validation at all on `folder`** | in-memory dict, atomic save |
| `workspace.roots_*` | `normalize_root` (must exist, dir, non-symlink) | registry allowlist |
| `workspace.files_*` | root allowlist by `root_id` + `resolve_inside` | workspace root |
| `workspace.project_*` | overlay validation (mode/language enums) | same JSON file |
| `workspace.shell_*` | propose/approve two-step (unchanged) | agentmodes |
| scheduler / reminders | no project linkage exists (P-13 semantics untouched) | n/a |
| subagents / tools | no project context exists; `refs_file` goes through the bounded preview path | n/a |

Cross-session/user leakage: none found — there is no ambient "active project"
that other sessions inherit; grouping is explicit per RPC call.

## 5. File-browser limits & preview policy

- List: cap 200 entries/page, symlinks skipped, hidden filtered by default.
- Preview: whitelist of 15 kinds; pdf/image/video/unknown are metadata-only;
  office/zip members capped; nothing is ever executed; HTML sanitized.
- UI (`workspace-shell.tsx`) ignores `next_cursor`/`has_more` → **gap: no
  "load more"**, users silently see only the first page.

## 6. Platform differences

- Case sensitivity: `Path.resolve()` canonicalizes on case-insensitive
  filesystems (macOS/Windows); containment checks run on resolved paths.
- Junctions: escape is still caught by resolve+relative_to (see §3); the
  explicit `is_symlink` walk additionally covers symlinks on all platforms.
- `\\` separators are normalized to `/` in `relative_key`; UNC (`//x`) becomes
  a relative segment chain, not a share access (and roots must exist locally).

## 7. Findings and severity

| # | Severity | Finding |
|---|---|---|
| F1 | **High** | **Dual-writer record loss.** `methods.py` holds projects in memory and rewrites the whole file on every mutation, while `ProjectOverlay` (workspace.* RPCs) appends/edits rows in the same file at runtime. A project adopted via `workspace.project_adopt` after sidecar start is **silently deleted** by the next `project.*` save; overlay-only fields (`settings`, `imported_in_place`, `copied`) are always dropped because `_project_to_dict` never round-trips them. |
| F2 | **High** | **Corrupt metadata fails open.** All three stores (`_load_projects_index`, overlay `_load_projects`, registry `_load`) treat unparseable JSON as an empty store; the next save then **overwrites the corrupt file**, silently destroying records. Requirement: fail closed, never silently delete. |
| F3 | Medium | `project.create/update` accept unbounded `name` and completely unvalidated `folder` (no length cap, no NUL check). |
| F4 | Medium | Binary content in a text-suffixed file (`.txt`, `.md`, …) is decoded as text; no binary sniff → mojibake preview instead of a truthful "binary" refusal. |
| F5 | Medium | `WorkspaceService._log` writes the **absolute workspace path** to `data/workspace_ops.jsonl` (privacy: private paths in logs), and writes `str(dict)` rather than JSON lines. |
| F6 | Medium | Projects route has **no loading state, no offline banner, no retry**, and **no edit/rename UI** although `project.update` exists; session lists per card are unbounded. Workspace route has no loading/offline/retry and no pagination UI. |
| F7 | Low | No explicit segment-depth cap on relative paths (bounded only by 4096-char cap). |
| F8 | Low | TS wrapper `workspaceFilesList` does not plumb `cursor`/`limit`. |
| F9 | Low | File-browser action menu lacks Escape/arrow keyboard handling. |
| F10 | Low | Delete-project dialog copy exists, but recent-activity/status on cards is limited to per-session relative time. |

## 8. Exact files in scope (proposed)

Backend:
- `dream/bridge/methods.py` — **surgical edits confined to the `project.*`
  section + `_write_json` callers**: F1 merge-preserving save (extras and
  runtime-adopted rows survive, tracked deletions still remove), F2 corrupt
  index backed up to `<path>.corrupt-<n>` before first save, F3 caps
  (name ≤ 200 chars, folder ≤ 4096 chars, NUL refused).
- `dream/workspace/projects.py` — F2 corrupt backup; keep unknown row fields.
- `dream/workspace/registry.py` — F2 corrupt backup.
- `dream/workspace/preview.py` — F4 NUL-byte binary sniff → metadata-only.
- `dream/workspace/paths.py` — F7 segment cap (64).
- `dream/workspace/service.py` — F5 ops log drops absolute paths, JSON lines.

Frontend:
- `apps/desktop/src/routes/projects.tsx` — loading skeleton, offline banner +
  retry, edit dialog (rename / relink / unlink folder via `project.update`),
  bounded session list (slice + show-all toggle), project recent-activity.
- `apps/desktop/src/components/workspace/workspace-shell.tsx` — loading /
  offline / retry states; "load more" pagination.
- `apps/desktop/src/lib/bridge/workspace.ts`, `echo-workspace.ts` — F8 plumb
  cursor/limit (echo parity).
- `apps/desktop/src/components/workspace/file-browser.tsx` — F9 Escape close.
- Locales: `en`/`fa` `projects.json`, `workspace.json`, `common.json`
  additions; other 6 locales regenerated structurally (existing English-
  fallback convention, fa fully translated).

Tests:
- New `tests/test_p14_projects_hardening.py`, `tests/test_p14_workspace_paths.py`.
- Extended `apps/desktop/src/routes/projects.test.tsx`, `workspace.test.tsx`.

Docs: `P-14-AUDIT.md` (after implementation), this synthesis.

## 9. Files explicitly out of scope

`dream/scheduler.py`, reminder code, `dream/gws/**`, `dream/remotegw/**`,
provider/commerce/routing code, `.github/workflows/**`, release files,
`dream/provenance/**` (see §2), subagent execution (`dream/agentmodes`
semantics unchanged — only additive tests), `pyproject.toml` version,
Rust `src-tauri` (no contract change required — all changes ride existing
generic RPC plumbing; `cargo` gates therefore N/A unless CI shows otherwise).

## 10. Migration & compatibility risks

- No schema migration: F1/F2 fixes are read/write-behavior only; wire shapes
  of `project.*` and `workspace.*` are unchanged (extras are persisted but not
  exposed). Old files load unchanged; new files remain readable by old code
  (unknown keys were already tolerated on load).
- Echo runtimes updated in lockstep where wrappers change (F8) — vitest pins
  parity.
- `tools/check_suite_count.py` floor (652) — only additive tests, safe.

## 11. Deterministic test plan (30 required items → mapping)

Backend (pytest, tmp_path, no sleeps, no network): project CRUD caps (1–3),
root validation (4), traversal/absolute/symlink escape re-pinned + segment cap
(5–7, 12), junction simulation via resolve-escape equivalence (8), case/
separator normalization (9), size/entry limits re-pinned (10–11), binary
preview (13), permission-error mapping via chmod 000 dir (14), corrupt backup
fail-closed (15), atomic persistence + dual-writer merge (16), session assoc
(17), provenance-via-session documented + tested read path (18), subagent
`refs_file` boundedness (19), scheduler non-access unchanged (20 — assert no
project linkage appears), bridge validation/error mapping (21), stale/cancel
(22–23, frontend), UI states (24), keyboard (25), RTL (26), locale
completeness via `check_locales.py` (27), no-leak assertions on ops log and
error strings (28), bounded rendering (29), no-network (30 — all tests offline
by construction; echo transport).

## 12. Unresolved PM decisions

1. **F1 fix location**: merge-preserving save inside `methods.py` (proposed)
   vs. routing overlay writes through the bridge store (larger refactor).
2. **Provenance project field**: keep out of scope (proposed) — hash-chained
   records make it a migration; project→session→provenance join already works.
3. **Edit dialog scope**: rename + folder relink/unlink (proposed) vs. rename
   only.
4. Locale fallback convention for de/es/fr/ja/ko/zh-CN (structural English
   fallback, as every prior phase did) — confirm acceptable.
