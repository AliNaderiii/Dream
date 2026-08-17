# How to build and sign installers

Installer builds are driven by `.github/workflows/desktop-release.yml`, which
triggers on any `v*` tag. It produces, for macOS (universal `.dmg`/`.app`),
Windows (NSIS `.exe`), and Linux (`.deb`/`.rpm`/AppImage):

- signed artefacts when the signing secrets are present,
- unsigned artefacts otherwise (so forks and PR validation stay green).

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

## Release checklist

1. Bump the version in **all four** places:
   `dream/__init__.py`, `apps/desktop/package.json`,
   `apps/desktop/src-tauri/Cargo.toml`, `apps/desktop/src-tauri/tauri.conf.json`.
2. Update `CHANGELOG.md` and `docs/STATUS.md`.
3. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`.
4. The workflow publishes a **draft** GitHub release with checksums; a human
   sanity-checks the artefacts and publishes it.

## Checksums

The release workflow computes SHA-256 checksums for every artefact and attaches
them to the draft release (see the `sha256sum` step in
`.github/workflows/desktop-release.yml`).
