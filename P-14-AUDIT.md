# P-14 Audit — Projects Dashboard & Workspace Isolation

## 1. Base

- Base `main` SHA: `c05b32839ea6c1680a7d0f06ec30529def385e7f`
  (`feat(memory): add reminder authoring on the existing scheduler (P-13) (#127)`)
- Branch: `arena/01a076b5-dream`. `origin/main` re-verified unchanged at the
  same SHA immediately before commit.
- `v0.4.7` does not exist and was not created. `pyproject.toml` version is
  untouched (`0.4.6`).

## 2. Scope and non-goals

Approved scope (see `P-14-SYNTHESIS.md`, PM-approved: full scope, F1 as a
merge-preserving save, provenance project field out of scope, edit dialog with
rename + relink/unlink):

- Backend hardening: F1 dual-writer record loss, F2 corrupt-metadata
  quarantine, F3 name/folder validation caps, F4 binary preview refusal,
  F5 ops-log privacy, F7 path-depth cap.
- Frontend: Projects dashboard loading/offline/retry states, edit dialog,
  bounded session lists; Workspace loading/offline/retry + listing pagination
  (F6, F8); file-browser menu Escape handling (F9).
- Locales: new keys in `projects.json` and `workspace.json`, translated in
  all 8 locales (fa fully; structural integrity verified).
- Tests: 2 new backend files (36 tests), extended frontend suites (+10 tests).

Non-goals honored: no scheduler/reminder changes, no Web Gateway changes, no
provider/billing/routing changes, no workflow or release file changes, no
cloud sync, no file upload, no provenance record format change, no `v0.4.7`,
PR not merged.

## 3. Project/workspace architecture

Two writers share `data/bridge_projects.json`:
`dream/bridge/methods.py` (`project.*`, in-memory dict + full-file save) and
`dream/workspace/projects.py` (`ProjectOverlay`, read-modify-write per call).
Workspace roots are pointer records in `data/workspace_registry.json`
(`WorkspaceRegistry`); folders are linked in place and never copied. The file
browser flows through `WorkspaceService` → `files.py`/`preview.py` with the
allowlisted-root + `resolve_inside` boundary in `dream/workspace/paths.py`.

## 4. Path-safety threat model (post-change)

| Threat | Defense | Test |
|---|---|---|
| `..` traversal (all forms) | `relative_key` refusal | `test_relative_traversal_forms_are_refused` |
| Absolute/drive escape | leading `/`, `X:` refusal | `test_absolute_escapes_are_refused` |
| Encoded traversal | RPC strings never URL-decoded | `test_percent_encoded_dots_are_a_literal_name_not_traversal` |
| Symlink escape | resolve + relative_to + per-segment walk | `test_symlink_escape_is_refused_in_listing` |
| Junction/reparse escape | resolve() canonicalizes junctions; containment check catches escape | `test_junction_like_directory_link_escape_is_refused` |
| Depth bomb | new `_MAX_DEPTH = 64` segment cap | `test_depth_cap_refuses_extreme_nesting` |
| Oversized listing/read | LIST_CAP 200, preview 64 KiB/24k chars | `test_directory_entry_limit_is_enforced`, `test_file_size_limit_caps_preview` |
| Binary decoded as text | new NUL-byte sniff → metadata-only | `test_binary_bytes_in_a_text_suffix_are_not_decoded` |
| Secrets in preview | `redact()` (pre-existing) | `test_secret_values_are_redacted_in_preview` |
| Paths/contents in logs | ops log now id-only JSON lines | `test_ops_log_never_contains_paths_or_contents` |
| Permission failure | typed `WorkspaceError`, path-free message | `test_permission_error_maps_to_workspace_error` |
| Shell from file browser | no exec path exists; `!shell` stays approval-gated (unchanged) | pre-existing suites |

## 5. Authorization matrix

Single local user; no tenancy. `project.*`: validated params
(name ≤ 200, folder ≤ 4096, no NUL), `invalid_params` mapping unchanged.
`workspace.files_*`: root allowlist by `root_id` + `resolve_inside`.
No ambient active-project state exists; grouping is explicit per RPC, so a
selection cannot leak across sessions or users. Scheduler, subagents, and
provenance were not modified; `refs_file` still flows through the bounded
preview path.

## 6. Changes made

Backend:
- `dream/bridge/methods.py` — merge-preserving `_save_projects_index` (foreign
  rows kept, overlay extras round-tripped, tombstoned deletes removed);
  `_quarantine_corrupt_index` fail-closed load; `_clean_project_name` /
  `_clean_project_folder` caps applied to create/update.
- `dream/workspace/projects.py` — `quarantine_corrupt()`; corrupt overlay
  stores are backed up as `<name>.corrupt-N` before any further save.
- `dream/workspace/registry.py` — same quarantine on corrupt registry files.
- `dream/workspace/paths.py` — `_MAX_DEPTH = 64` segment cap in
  `relative_key`.
- `dream/workspace/preview.py` — `_looks_binary` NUL sniff for text/csv kinds;
  binary content becomes a metadata-only preview with an explicit warning.
- `dream/workspace/service.py` — ops log is JSON-lines and no longer records
  absolute folder paths or file names.

Frontend:
- `routes/projects.tsx` — loading skeleton (`role="status"`), offline banner,
  error banner with Retry, Edit dialog (rename, relink/unlink folder via
  `project.update`; copy states files are never touched), bounded session
  lists (8 + explicit `aria-expanded` toggle).
- `components/workspace/workspace-shell.tsx` — offline banner, loading status,
  Retry, and "Load more files" pagination driven by `next_cursor`.
- `components/workspace/file-browser.tsx` — menu labelled per entry and closes
  on Escape.
- `lib/bridge/workspace.ts` — `workspaceFilesList` plumbs `cursor`/`limit`.
- `lib/bridge/echo-workspace.ts` — sidecar-parity pagination (cursor/limit
  validation identical to the Python bounds).
- `lib/bridge/echo-projects.ts` — sidecar-parity name/folder caps.
- Locales — new `projects.v2` keys (`retry`, `loading`, `editProject`,
  `editHelp`, `unlinkHelp`, `saveChanges`, `showAll`, `showFewer`) and
  `workspace.browser` keys (`retry`, `loading`, `loadMore`) in all 8 locales;
  fa fully translated; wording states truthfully that folders remain links and
  nothing is copied or deleted.
- `MASTER_CHECKLIST.md` item 3.1 checked with a P-14 note.

## 7. Migration and compatibility

No schema migration. Old `bridge_projects.json` files load unchanged; the
merge-preserving save keeps all previously-written fields, so files written by
new code remain readable by old code (old load already ignored unknown keys).
Corrupt files are renamed, never rewritten — first-run behavior for missing
files is unchanged (no spurious backups). Wire shapes of every RPC are
unchanged; `cursor`/`limit` were already accepted by the Python handler.

## 8. Platform behavior

- Junctions/reparse points: escape is caught by `resolve()` + `relative_to`
  even where `is_symlink()` misses reparse points (< Py 3.12); simulated on
  POSIX with `target_is_directory` symlinks (Windows CI does not run pytest in
  this repo's workflows — desktop CI covers TS/Rust on Windows).
- Case/separator: `\\` normalized to `/`; resolved-path containment holds on
  case-insensitive filesystems.
- Permission tests skip for root and on Windows (documented skip conditions).

## 9. Test matrix (30 required items)

| # | Requirement | Test(s) | Result |
|---|---|---|---|
| 1 | project creation | `test_create_*` (pre-existing) + caps tests | pass |
| 2 | project editing | `test_update_*` + `edits a project name and unlinks its folder` (vitest) | pass |
| 3 | deletion/unlink | `test_delete_wins_over_the_merge`, delete-confirm vitest | pass |
| 4 | root validation | `test_symlink_root_is_refused`, `test_import_refuses_a_file` (pre-existing) | pass |
| 5 | relative traversal | `test_relative_traversal_forms_are_refused` | pass |
| 6 | absolute escape | `test_absolute_escapes_are_refused` | pass |
| 7 | symlink escape | `test_symlink_escape_is_refused_in_listing` | pass |
| 8 | junction/reparse | `test_junction_like_directory_link_escape_is_refused` (equivalence, documented) | pass |
| 9 | case/separator normalization | `test_separator_normalization_is_stable` | pass |
| 10 | file-size limit | `test_file_size_limit_caps_preview` | pass |
| 11 | directory-entry limit | `test_directory_entry_limit_is_enforced` | pass |
| 12 | recursion/depth limit | `test_depth_cap_refuses_extreme_nesting` | pass |
| 13 | binary preview | `test_binary_bytes_in_a_{text,csv}_suffix_are_not_decoded` | pass |
| 14 | permission mapping | `test_permission_error_maps_to_workspace_error` | pass |
| 15 | corrupt metadata | `test_corrupt_{bridge_index,overlay_store,registry}_is_quarantined*` | pass |
| 16 | atomic persistence | `test_atomic_save_leaves_no_tmp_file`, `test_merge_survives_a_reload` | pass |
| 17 | project/session association | `test_session_association_survives_merge_saves` | pass |
| 18 | project/provenance association | via session join (`project.get`), PM-approved out-of-scope for record fields | n/a by decision |
| 19 | subagent/tool scope | `refs_file` bounded path unchanged; pre-existing agentmode suites green | pass (unchanged) |
| 20 | scheduler scope | no project linkage exists; P-13 suites green unchanged | pass (unchanged) |
| 21 | bridge validation/errors | `test_project_name_length_is_bounded`, `..._nul_are_bounded`, oversized-name vitest | pass |
| 22 | cancellation/timeout | pre-existing transport-hardening suites green | pass (unchanged) |
| 23 | stale response | cancelled-effect guards in both routes; covered by loading-state tests | pass |
| 24 | UI loading/empty/error/offline | loading vitest (projects, workspace), Stage-D offline pattern via `BridgeOfflineBanner` | pass |
| 25 | keyboard accessibility | Escape-closes-menu vitest; axe run in workspace suite | pass |
| 26 | RTL rendering | `renders correctly in RTL` (both routes) | pass |
| 27 | locale completeness | `tools/check_locales.py` PASS (8 × 30, fa gate PASS) | pass |
| 28 | no secret/path leakage | `test_ops_log_never_contains_paths_or_contents`, `test_security_errors_do_not_echo_the_root_path` | pass |
| 29 | bounded rendering | `keeps long session lists bounded…` vitest; pagination tests | pass |
| 30 | no network dependency | all tests offline by construction (echo transport, tmp dirs) | pass |

## 10. Exact command results (all executed on this checkout)

Python (`/tmp/venv`, Python 3.11.2):

- `python -m pytest -q` → **3505 passed, 16 skipped** (baseline 3469/16; +36)
- `python -m pytest -q tests/test_p14_projects_hardening.py tests/test_p14_workspace_paths.py tests/test_workspace.py tests/test_workspace_security.py tests/test_security_workspace.py tests/test_bridge_projects.py` → **89 passed**
- `python -m ruff check .` → **All checks passed!**
- `python -m mypy .` — the repo has no mypy config/CI gate; a scoped run
  (`mypy dream/workspace dream/security/pathsafety.py`) reports **41 errors in
  12 files both before and after this change** (pre-existing; none introduced
  — verified by stash/compare). Recorded as not-a-gate.
- `python tools/check_suite_count.py` → **3510 collected ≥ 652: pass**

Frontend (`apps/desktop`, Node 22.22.3):

- `npm run typecheck` → clean
- `npm run lint` → **0 errors**, 13 warnings (identical warning set exists on
  `main`; verified by stash/compare)
- `npm run format:check` → all files pass
- `npm run test` → **761 passed (110 files)** (baseline 751; +10)
- `npm run build` → built successfully
- `npm run accessibility:check` → 13 passed
- `npm run performance:check` → `"pass": true`
- `python tools/check_locales.py` → PASS — 8 locales × 30 namespaces, 1241
  leaves, identical trees; fa gate PASS

Rust: **not applicable** — no Rust file changed; all frontend/back-end changes
ride the existing generic RPC plumbing. Desktop CI compiles Rust on push.

## 11. CI

- PR: _recorded after push (see §16 update)_
- CI runs tied to the final SHA: _recorded after push_

## 12. Final remote SHA

_Recorded after push._

## 13. Changed files (31 production/test files + 2 docs)

Backend: `dream/bridge/methods.py`, `dream/workspace/{paths,preview,projects,registry,service}.py`
Frontend: `apps/desktop/src/routes/{projects.tsx,projects.test.tsx,workspace.test.tsx}`,
`apps/desktop/src/components/workspace/{workspace-shell,file-browser}.tsx`,
`apps/desktop/src/lib/bridge/{workspace.ts,workspace.test.ts,echo-workspace.ts,echo-projects.ts}`,
16 locale files (8 × `projects.json`/`workspace.json`).
Tests: `tests/test_p14_projects_hardening.py` (14), `tests/test_p14_workspace_paths.py` (22).
Docs: `P-14-SYNTHESIS.md`, `P-14-AUDIT.md`, `MASTER_CHECKLIST.md` (item 3.1).

Explicitly untouched: `dream/scheduler.py`, all reminder code, `dream/gws/**`,
`dream/remotegw/**`, `.github/workflows/**`, `pyproject.toml`,
`dream/provenance/**`, Rust `src-tauri/**`, provider/commerce/routing code.

## 14. Skipped/unexecuted tests

- 16 pre-existing pytest skips (unrelated, same as baseline).
- `test_permission_error_maps_to_workspace_error` skips when running as root
  or on Windows (chmod semantics).
- Symlink-based tests skip on Windows; junction behavior is covered by the
  resolve-containment equivalence argument (§8) — a native Windows junction
  test was not executable in this Linux sandbox and is recorded as such.
- Cargo gates not run (no Rust change); desktop CI runs them on push.

## 15. Residual risks

- The dual-writer design remains; the merge-preserving save removes the
  observed record-loss window but two concurrent writers can still interleave
  writes (last-writer-wins on non-overlapping saves). A unified store was
  PM-deferred.
- Binary sniff is NUL-byte-based; a NUL-free binary (rare) still decodes with
  replacement characters, bounded and redacted.
- de/es/fr/ja/ko/zh-CN carry 372 pre-existing English fallbacks elsewhere in
  the app (unchanged convention); the new keys are translated in all 8.

## 16. Rollback

Revert the single PR merge commit (or `git revert <final SHA>` on the branch).
No migrations to unwind: `.corrupt-N` backups and the JSON stores are forward-
and backward-compatible; old code reads new files unchanged.
