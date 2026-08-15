fn main() {
    tauri_build::build();

    // Workaround for https://github.com/tauri-apps/tauri/issues/13419 :
    // `tauri-winres` embeds the Windows application manifest only into the main
    // binary, not into test binaries. Without the manifest, a test EXE loads the
    // wrong ComCtl32 (v5 instead of v6) and fails to start with
    // STATUS_ENTRYPOINT_NOT_FOUND (0xc0000139) when running `cargo test` on Windows.
    //
    // `cargo:rustc-link-arg-tests` restricts the manifest to test targets only,
    // so the main app binary is unaffected (tauri-winres already embeds one).
    #[cfg(target_os = "windows")]
    {
        let manifest = concat!(env!("CARGO_MANIFEST_DIR"), "/windows-app-manifest.xml");
        println!("cargo:rerun-if-changed={manifest}");
        println!("cargo:rustc-link-arg-tests=/MANIFEST:EMBED");
        println!("cargo:rustc-link-arg-tests=/MANIFESTINPUT:{manifest}");
    }
}
