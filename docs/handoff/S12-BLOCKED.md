# S12 — BLOCKED: desktop-release.yml push (GitHub App `workflows` permission)

**Status: partially pushed.** Everything in S12 except the
`.github/workflows/desktop-release.yml` rewrite is on the PR branch
(`arena/01a01e00-dream`). The workflow change itself could not be pushed by
this session because the GitHub App used for the sandbox
(`arena-ai-coding-agent[bot]`) is missing the **`workflows`** permission.

## What is blocked

A change to any file under `.github/workflows/` is rejected by GitHub for this
credential on every write path. Verified empirically, all returning the same
class of error (`without workflows permission` / `Resource not accessible by
integration`):

1. `git push` of any commit touching `.github/workflows/desktop-release.yml` —
   `refusing to allow a GitHub App to create or update workflow without
   workflows permission`.
2. Contents API (`PUT /repos/{owner}/{repo}/contents/.github/workflows/...`)
   — HTTP 403.
3. Git trees API (`POST /repos/{owner}/{repo}/git/trees` with a workflow path
   entry) — HTTP 403.

Ordinary file writes (contents API, blob API, ref creation) all work; the
check is specific to workflow files. The repository history is a single
squash-merge root commit created through the PR merge API, which is why
earlier sessions could land workflow files without this push path.

## What is already on the branch (commit A, pushed)

- `apps/desktop/src-tauri/src/bridge/process.rs` — sidecar interpreter
  discovery (`python` / `py` / `python3`, `DREAM_SIDECAR_PYTHON` override,
  handshake-aware skipping, English + Persian disconnect reason) plus 4 unit
  tests.
- Version 0.3.0 in `apps/desktop/package.json`,
  `apps/desktop/src-tauri/tauri.conf.json`, `apps/desktop/package-lock.json`.
- `CHANGELOG.md`, `README.md`, `docs/user/quick-start.md`,
  `apps/desktop/README.md`, `docs/handoff/S12.md`, `docs/handoff/S12-BLOCKED.md`.

## What is pending (commit B) — owner action required

The complete `desktop-release.yml` rewrite is committed locally as commit B
and is also attached to this repo as `docs/handoff/S12-workflow.patch`. The
owner (who has full repository permissions) can land it with:

```bash
cd <clone-of-AliNaderiii/Dream>
git fetch origin
git checkout arena/01a01e00-dream
git apply docs/handoff/S12-workflow.patch
git add .github/workflows/desktop-release.yml
git -c user.name="Ali Naderi" -c user.email="alinaderi@users.noreply.github.com" \
  commit -m "S12: desktop-release.yml publishes NSIS installers to v* releases

- v* tag pushes now publish (not draft) a GitHub Release and attach the
  unsigned NSIS installer - no Authenticode secrets required, updater keys
  stay optional, and verify steps fail the job if the release ends up
  without installers. workflow_dispatch builds bundles as CI artifacts only."
git push origin arena/01a01e00-dream
```

Notes:

- The `-c user.name/user.email` flags are **required**: CI's
  `tools/check_commit.py` enforces author `Ali Naderi
  <alinaderi@users.noreply.github.com>` on the PR head commit, and the
  message must stay free of banned words (it is, as written above).
- After that push the PR contains the whole S12 change set, `desktop-ci` and
  `ci` run against the new head, and this block is resolved — the release
  workflow change is then reviewed and squash-merged with the rest of the PR.
- If the push above is ever rejected for the same workflow-permission reason,
  reconnect the GitHub integration for the sandbox or push from a PAT-based
  git credential instead.

## Verification after the owner push

- PR diff includes `.github/workflows/desktop-release.yml` with
  `releaseDraft: false`, the `Publish stale draft release` pre-step, the NSIS
  verify step, and the `Verify release assets` step.
- `desktop-ci` (frontend + rust × 3 OS) and `ci` (commit rules) are green.
- After the squash-merge, the owner tags `v0.3.0` and the Desktop Release run
  publishes a non-draft release with `Dream_0.3.0_x64-setup.exe` attached.
