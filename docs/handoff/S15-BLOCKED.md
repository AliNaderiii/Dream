# S15 — Single-instance plugin blocked

`tauri-plugin-single-instance` was removed after its integration continued to fail the
Rust Clippy job on Ubuntu, macOS, and Windows despite replacing the side-effecting
`Option::map`, handling window-operation errors, and restoring the existing desktop
platform gate. The failure could not be reproduced locally because Cargo is absent
from this environment. `close_to_tray` remains `false`, so closing the main window
quits Dream rather than leaving another tray-resident process; the crash fix, Echo
fallback, and version 0.3.2 remain intact.
