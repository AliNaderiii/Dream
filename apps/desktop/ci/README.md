# CI workflows (pending installation)

These two workflows belong in `.github/workflows/`, but the agent's GitHub token
lacks the `workflows` permission, so they could not be pushed there:

```
refusing to allow a GitHub App to create or update workflow
`.github/workflows/desktop-ci.yml` without `workflows` permission
```

## Install

```bash
git mv apps/desktop/ci/desktop-ci.yml      .github/workflows/desktop-ci.yml
git mv apps/desktop/ci/desktop-release.yml .github/workflows/desktop-release.yml
git rm apps/desktop/ci/README.md
git commit -m "ci(desktop): add desktop build workflows"
git push
```

## What they do

**`desktop-ci.yml`** — on push/PR touching `apps/desktop/**`:
- `frontend` job (ubuntu): typecheck, lint, format check, Vitest.
- `rust` job (matrix: ubuntu-22.04, windows-latest, macos-latest):
  `cargo fmt --check`, `cargo clippy -D warnings`, `cargo build`, `cargo test`.
  This is the **G1** gate.

**`desktop-release.yml`** — on `v*` tags or manual dispatch. Builds
dmg/app · nsis · deb/rpm/AppImage via `tauri-action`, uploads installers, and
opens a draft release. This is the **G7** gate.

### Secrets (all optional)

Signing is secret-gated: with none of these set, CI still produces **unsigned**
installers and stays green.

| Secret | Purpose |
| --- | --- |
| `TAURI_SIGNING_PRIVATE_KEY` | Updater signature. Public counterpart is already in `tauri.conf.json`. |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Password for the above (empty if unset). |
| `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` | macOS Developer ID signing + notarization. |
| `WINDOWS_CERTIFICATE`, `WINDOWS_CERTIFICATE_PASSWORD` | Windows Authenticode. |

The updater **private key** generated during development was deliberately not
committed. Generate a fresh pair with `npm run tauri signer generate`, put the
private key in `TAURI_SIGNING_PRIVATE_KEY`, and replace `plugins.updater.pubkey`
in `tauri.conf.json` with the public half.
