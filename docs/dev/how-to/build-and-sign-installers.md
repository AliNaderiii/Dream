# How to build and sign installers

Installer builds are driven by `.github/workflows/desktop-release.yml`, which
triggers on any `v*` tag. It produces, for Windows (NSIS `.exe`) and Linux
(`.deb` / `.rpm` / AppImage):

- signed artefacts when the signing secrets are present,
- unsigned artefacts otherwise (so forks and PR validation stay green).

macOS is excluded until Apple Developer ID secrets are configured.

## What the artefacts actually contain

- **Windows NSIS** (`Dream_<version>_x64-setup.exe`): `tauri build` runs
  `scripts/bundle-sidecar.mjs`, which downloads pinned CPython 3.12.10
  (SHA-256 verified), installs Dream **non-editable**, and ships
  `python/python.exe` next to the app. A Release-only Windows user does not
  need a separate `pip install`. The installer is unsigned unless
  Authenticode secrets are set — SmartScreen will warn.
- **Linux** (`.deb` / `.rpm` / AppImage): UI shell only. The sidecar uses
  system Python 3.10+ with Dream installed (`pip install -e .` from the
  repository root).

## Signing secrets (repo-configured)

| Secret | Purpose |
| --- | --- |
| `APPLE_CERTIFICATE` / `APPLE_SIGNING_IDENTITY` / `APPLE_TEAM_ID` / `APPLE_ID` / `APPLE_PASSWORD` | macOS Developer ID signing + notarisation |
| `WINDOWS_CERTIFICATE` / `WINDOWS_CERTIFICATE_PASSWORD` | Windows Authenticode |
| `TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | updater artefacts |

## Local build (Linux)

```bash
cd apps/desktop
npm ci
npm run tauri build   # emits target/release/bundle/**/*.{deb,rpm,AppImage}
```

Requires `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `patchelf`, and `rpm`.
`bundle-sidecar.mjs` no-ops on non-Windows hosts.

## Release checklist

1. Bump the version in **all five** places, keeping them identical:
   `dream/__init__.py`, `pyproject.toml`, `apps/desktop/package.json`
   (and the matching `package-lock.json` `version` fields),
   `apps/desktop/src-tauri/Cargo.toml`, `apps/desktop/src-tauri/tauri.conf.json`.
   Do not bump `dream/bridge/__init__.py` — that is the sidecar protocol
   version, not the product version.
2. Update `CHANGELOG.md` and prepend a short note to `docs/STATUS.md`.
3. Land the bump on `main` through a pull request. Then tag **that** commit:
   `git tag v0.4.6 && git push origin v0.4.6`.
4. The workflow publishes a **public** GitHub Release (not a draft) and
   attaches the installers. Each runner also uploads a `SHA256SUMS-*.txt`
   asset. A human still sanity-checks the artefacts before daily use.

## Checksums

The release workflow computes SHA-256 checksums for every installer artefact
on that runner and attaches `SHA256SUMS-<target>.txt` to the GitHub Release.
