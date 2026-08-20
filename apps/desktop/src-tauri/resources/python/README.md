# Bundled CPython runtime (Windows)

This directory is intentionally **empty in the repository**. At `tauri build`
time on Windows, `scripts/bundle-sidecar.mjs` downloads the pinned CPython
3.12.10 Windows embeddable amd64 package from python.org (SHA-256 verified),
unpacks it here, bootstraps pip, and installs the Dream kernel non-editable.

The resulting tree is shipped by NSIS (`bundle.resources` →
`resources/python/**`) so a bare Release download can start the sidecar
(`python -u -m dream.bridge`) without a separate `pip install`.

Everything except this README and `.gitkeep` is git-ignored — the runtime is a
build artifact, never committed. On Linux/macOS this directory stays empty and
the shell uses the system Python.
