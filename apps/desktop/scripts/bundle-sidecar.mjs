#!/usr/bin/env node
/**
 * Bundle a Windows CPython + Dream kernel into the app's resources at
 * `tauri build` time, so a bare GitHub Release download can start the sidecar
 * (`python -u -m dream.bridge`) with no separate `pip install`.
 *
 * Behaviour:
 * - On any non-Windows platform, or when `DREAM_SKIP_SIDECAR_BUNDLE=1`, print a
 *   one-line skip and exit 0 (Linux/macOS release jobs and local POSIX builds
 *   must never fail).
 * - On Windows: download the pinned CPython 3.12.10 Windows embeddable amd64
 *   package from python.org, verify its SHA-256, unpack it into
 *   `src-tauri/resources/python/`, enable `site` in `python312._pth`, bootstrap
 *   pip, and `pip install` the Dream package (non-editable) from the repo root.
 * - Idempotent: if `python/python.exe` can already `import dream.bridge`, skip.
 * - `--full` (or `DREAM_SIDECAR_STT=1`): additionally install the `stt` and
 *   `tts` extras and download the pinned Whisper `base` model AND the pinned
 *   offline Persian Piper voice into `<python>/models/`, so the *full* Windows
 *   installer transcribes AND speaks fully offline.
 *   (faster-whisper) and download the pinned Whisper `base` model into
 *   `<python>/models/faster-whisper-base/`, so the *full* Windows installer
 *   transcribes voice notes fully offline. In full mode the idempotency check
 *   also requires `import faster_whisper` and the model file — a slim bundle
 *   never masquerades as a full one.
 *
 * Run from `apps/desktop` (the Tauri `beforeBuildCommand` cwd); paths are
 * resolved from this file's location, not the process cwd, so it is safe to
 * invoke from anywhere. The script fails loud on checksum / import errors so a
 * bad Windows release job goes red instead of shipping an empty kernel.
 */
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { inflateRawSync } from 'node:zlib';

// ---------------------------------------------------------------------------
// Pinned inputs
// ---------------------------------------------------------------------------

const PYTHON_VERSION = '3.12.10';
const EMBED_ZIP_URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`;
// SHA-256 of python-3.12.10-embed-amd64.zip, from the official python.org SPDX
// SBOM (…/python-3.12.10-embed-amd64.zip.spdx.json). MD5 (cross-check, also
// published by python.org): fe8ef205f2e9c3ba44d0cf9954e1abd3.
const EMBED_ZIP_SHA256 = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3';
const GET_PIP_URL = 'https://bootstrap.pypa.io/get-pip.py';

// Full-installer additions: the `stt` extra plus a pinned Whisper model
// downloaded next to the embedded interpreter. The revision is pinned to the
// Systran/faster-whisper-base HEAD at pin time (2023-11-23) so release builds
// stay reproducible; the model is ~148 MB (model.bin ~145 MB).
const STT_MODEL_ID = 'base';
const STT_MODEL_REPO = 'Systran/faster-whisper-base';
const STT_MODEL_REVISION = 'ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66';
const STT_MODEL_MIN_BYTES = 100_000_000; // sanity floor for model.bin (~145 MB)

// Full-installer additions for SPEECH: the `tts` extra (edge-tts + piper-tts)
// plus the pinned offline Persian Piper voice downloaded next to the embedded
// interpreter. The revision is pinned to the rhasspy/piper-voices HEAD at pin
// time (2026-09-23) so release builds stay reproducible; the voice is ~63 MB.
const TTS_VOICE_REPO = 'rhasspy/piper-voices';
const TTS_VOICE_REVISION = 'c10ece1aade47bb51c153c893d14e5bf8e5b7117';
const TTS_VOICE_SPEAKER = 'reza_ibrahim';
const TTS_VOICE_QUALITY = 'medium';
const TTS_VOICE_STEM = 'fa_IR-reza_ibrahim-medium'; // <file>.onnx / <file>.onnx.json
const TTS_VOICE_REPO_PATH = `fa/fa_IR/${TTS_VOICE_SPEAKER}/${TTS_VOICE_QUALITY}`;
const TTS_VOICE_MIN_BYTES = 60_000_000; // sanity floor for the .onnx (~63 MB)

// ---------------------------------------------------------------------------
// Resolved paths (relative to this file, never the process cwd)
// ---------------------------------------------------------------------------

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url)); // apps/desktop/scripts
const DESKTOP_DIR = resolve(SCRIPT_DIR, '..'); // apps/desktop
const REPO_ROOT = resolve(DESKTOP_DIR, '..', '..'); // repository root
const RESOURCE_DIR = resolve(DESKTOP_DIR, 'src-tauri', 'resources');
const PYTHON_DIR = join(RESOURCE_DIR, 'python');
const PYTHON_EXE = join(PYTHON_DIR, 'python.exe');

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function fail(message) {
  console.error(`[bundle-sidecar] ERROR: ${message}`);
  process.exit(1);
}

/** Run a command, streaming its output; throws on spawn error or non-zero exit. */
function runOrThrow(cmd, args) {
  const res = spawnSync(cmd, args, { stdio: 'inherit', encoding: 'utf8' });
  if (res.error) {
    fail(`could not run ${cmd}: ${res.error.message}`);
  }
  if (res.status !== 0) {
    fail(`${cmd} ${args.join(' ')} exited with code ${res.status}`);
  }
}

/** Run a command quietly and return its exit status (null on spawn failure). */
function runStatus(cmd, args) {
  const res = spawnSync(cmd, args, { stdio: 'ignore', encoding: 'utf8' });
  if (res.error) return null;
  return res.status;
}

async function download(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180_000);
  try {
    const res = await fetch(url, { redirect: 'follow', signal: controller.signal });
    if (!res.ok) {
      fail(`download failed: ${url} (HTTP ${res.status} ${res.statusText})`);
    }
    return Buffer.from(await res.arrayBuffer());
  } catch (err) {
    fail(`download failed: ${url} (${err.message})`);
  } finally {
    clearTimeout(timer);
  }
}

function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex');
}

/**
 * Minimal, dependency-free ZIP extractor (stored + deflate entries), built on
 * Node's `zlib.inflateRawSync`. The archive is SHA-256 pinned before we ever
 * get here, so this only needs to unpack a trusted, well-formed zip.
 */
function extractZip(buf, destDir) {
  const EOCD_SIG = 0x06054b50;
  let eocd = -1;
  for (let i = buf.length - 22; i >= 0; i -= 1) {
    if (buf.readUInt32LE(i) === EOCD_SIG) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) fail('zip: end-of-central-directory record not found');

  const totalEntries = buf.readUInt16LE(eocd + 10);
  const cdOffset = buf.readUInt32LE(eocd + 16);
  let offset = cdOffset;

  for (let i = 0; i < totalEntries; i += 1) {
    if (buf.readUInt32LE(offset) !== 0x02014b50) {
      fail(`zip: malformed central directory at entry ${i}`);
    }
    const method = buf.readUInt16LE(offset + 10);
    const compressedSize = buf.readUInt32LE(offset + 20);
    const uncompressedSize = buf.readUInt32LE(offset + 24);
    const nameLen = buf.readUInt16LE(offset + 28);
    const extraLen = buf.readUInt16LE(offset + 30);
    const commentLen = buf.readUInt16LE(offset + 32);
    const localOffset = buf.readUInt32LE(offset + 42);
    const name = buf.toString('utf8', offset + 46, offset + 46 + nameLen);

    offset += 46 + nameLen + extraLen + commentLen;

    const safeName = name.replace(/\\/g, '/');
    if (safeName.split('/').includes('..')) {
      fail(`zip: refusing unsafe entry path "${name}"`);
    }
    if (safeName.endsWith('/')) continue; // directory entry

    if (buf.readUInt32LE(localOffset) !== 0x04034b50) {
      fail(`zip: malformed local header for "${name}"`);
    }
    const localNameLen = buf.readUInt16LE(localOffset + 26);
    const localExtraLen = buf.readUInt16LE(localOffset + 28);
    const dataStart = localOffset + 30 + localNameLen + localExtraLen;
    const compressed = buf.subarray(dataStart, dataStart + compressedSize);

    let data;
    if (method === 0) {
      data = compressed;
    } else if (method === 8) {
      data = inflateRawSync(compressed);
    } else {
      fail(`zip: unsupported compression method ${method} for "${name}"`);
    }
    if (data.length !== uncompressedSize) {
      fail(`zip: uncompressed size mismatch for "${name}"`);
    }

    const outPath = join(destDir, safeName);
    mkdirSync(dirname(outPath), { recursive: true });
    writeFileSync(outPath, data);
  }
}

/**
 * Pick the embeddable distribution's `._pth` file from a directory listing.
 *
 * The official python.org embeddable zip names it `python<major><minor>._pth`
 * (e.g. `python312._pth` for CPython 3.12.10) — NOT `python31210._pth`, which
 * is what stripping every non-digit from the full version string produces.
 * Match real file names against `/^python3\d+\._pth$/i` and prefer the
 * canonical `python312._pth` when it is present. Returns null when nothing
 * matches so the caller can fail loud with the full listing.
 */
export function findPthName(names) {
  const matches = names.filter((name) => /^python3\d+\._pth$/i.test(name));
  if (matches.length === 0) return null;
  return matches.includes('python312._pth') ? 'python312._pth' : matches[0];
}

/**
 * Whether this invocation should build the FULL sidecar (stt extra + bundled
 * Whisper model). Pure so a unit test can drive it without Windows.
 */
export function wantsFullStt(argv = process.argv, env = process.env) {
  return argv.includes('--full') || env.DREAM_SIDECAR_STT === '1';
}

/** The pip requirement that adds the full-mode extras to a local repo install. */
export function fullPipSpec(repoRoot = REPO_ROOT) {
  return `${repoRoot}[stt,tts]`;
}

/** Backwards-compatible alias — full mode has always meant "the heavy extras". */
export const sttPipSpec = fullPipSpec;

/** Where the pinned Whisper model lives inside the bundled interpreter. */
export function sttModelDir(pythonDir = PYTHON_DIR) {
  return join(pythonDir, 'models', `faster-whisper-${STT_MODEL_ID}`);
}

/** Where the pinned offline Piper voices live inside the bundled interpreter. */
export function ttsVoiceDir(pythonDir = PYTHON_DIR) {
  return join(pythonDir, 'models', 'piper-voices');
}

/**
 * The Python snippet (run with the bundled interpreter) that downloads the
 * pinned model into `modelDir`. `JSON.stringify` produces a valid Python
 * string literal for any path, backslashes included.
 */
export function sttModelDownloadPython(modelDir) {
  return [
    'from huggingface_hub import snapshot_download',
    'snapshot_download(',
    `    repo_id=${JSON.stringify(STT_MODEL_REPO)},`,
    `    revision=${JSON.stringify(STT_MODEL_REVISION)},`,
    `    local_dir=${JSON.stringify(String(modelDir))},`,
    ')',
  ].join('\n');
}

/**
 * The Python snippet (run with the bundled interpreter) that downloads the
 * pinned offline Piper voice into `voiceDir`, mirroring the HF repo layout
 * (`fa/fa_IR/<speaker>/<quality>/…`) that `dream/speech/tts.py` expects.
 */
export function ttsVoiceDownloadPython(voiceDir) {
  return [
    'from huggingface_hub import hf_hub_download',
    `hf_hub_download(`,
    `    repo_id=${JSON.stringify(TTS_VOICE_REPO)},`,
    `    revision=${JSON.stringify(TTS_VOICE_REVISION)},`,
    `    filename=${JSON.stringify(`${TTS_VOICE_REPO_PATH}/${TTS_VOICE_STEM}.onnx`)},`,
    `    local_dir=${JSON.stringify(String(voiceDir))},`,
    ')',
    `hf_hub_download(`,
    `    repo_id=${JSON.stringify(TTS_VOICE_REPO)},`,
    `    revision=${JSON.stringify(TTS_VOICE_REVISION)},`,
    `    filename=${JSON.stringify(`${TTS_VOICE_REPO_PATH}/${TTS_VOICE_STEM}.onnx.json`)},`,
    `    local_dir=${JSON.stringify(String(voiceDir))},`,
    ')',
  ].join('\n');
}

/**
 * Enable `site` in the embeddable distribution's `._pth` file and make the
 * `Lib/site-packages` directory (where pip installs land) importable.
 */
function patchPth() {
  const names = readdirSync(PYTHON_DIR);
  const pthName = findPthName(names);
  if (!pthName) {
    fail(
      `no \`python3XX._pth\` file in ${PYTHON_DIR} — unexpected embeddable layout (directory contents: ${names.sort().join(', ') || '<empty>'})`,
    );
  }
  const pth = join(PYTHON_DIR, pthName);

  let lines = readFileSync(pth, 'utf8').split(/\r?\n/);
  lines = lines.map((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('#import site') || trimmed.startsWith('# import site')) {
      return 'import site';
    }
    return line;
  });
  if (!lines.some((line) => line.trim() === 'import site')) {
    lines.push('import site');
  }
  if (!lines.some((line) => line.trim() === 'Lib/site-packages')) {
    const dotIndex = lines.findIndex((line) => line.trim() === '.');
    const insertAt = dotIndex >= 0 ? dotIndex + 1 : 1;
    lines.splice(insertAt, 0, 'Lib/site-packages');
  }
  writeFileSync(pth, `${lines.join('\n')}\n`, 'utf8');
  console.log(`[bundle-sidecar] patched ${pth} to enable site + Lib/site-packages`);
}

/** Is the bundled interpreter usable — and, in full mode, complete? */
function sidecarReady(fullStt) {
  const kernelOk =
    runStatus(PYTHON_EXE, [
      '-c',
      "import dream.bridge; from zoneinfo import ZoneInfo; ZoneInfo('Asia/Tehran')",
    ]) === 0;
  if (!kernelOk) return false;
  if (!fullStt) return true;
  const sttOk = runStatus(PYTHON_EXE, ['-c', 'import faster_whisper']) === 0;
  const modelOk = existsSync(join(sttModelDir(), 'model.bin'));
  const ttsOk = runStatus(PYTHON_EXE, ['-c', 'import piper, edge_tts']) === 0;
  const voiceOk = existsSync(join(ttsVoiceDir(), TTS_VOICE_REPO_PATH, `${TTS_VOICE_STEM}.onnx`));
  return sttOk && modelOk && ttsOk && voiceOk;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  // Non-Windows builds and explicit opt-outs must never fail the build.
  if (process.env.DREAM_SKIP_SIDECAR_BUNDLE === '1') {
    console.log('[bundle-sidecar] skipping — DREAM_SKIP_SIDECAR_BUNDLE is set');
    return;
  }
  if (process.platform !== 'win32') {
    console.log(
      `[bundle-sidecar] skipping — Windows-only CPython bundle (platform ${process.platform})`,
    );
    return;
  }

  // Idempotency: a working interpreter + kernel means there is nothing to
  // do. In full mode the check additionally requires faster-whisper and the
  // bundled model file, so a slim bundle is upgraded rather than reused.
  const fullStt = wantsFullStt();
  if (existsSync(PYTHON_EXE) && sidecarReady(fullStt)) {
    console.log(
      fullStt
        ? '[bundle-sidecar] full bundle (kernel + faster-whisper + model) already present — skipping'
        : '[bundle-sidecar] bundled interpreter + Dream kernel already present — skipping',
    );
    return;
  }

  console.log(`[bundle-sidecar] downloading CPython ${PYTHON_VERSION} embeddable amd64`);
  const zipBuf = await download(EMBED_ZIP_URL);
  const actual = sha256(zipBuf);
  if (actual !== EMBED_ZIP_SHA256) {
    fail(`SHA-256 mismatch for ${EMBED_ZIP_URL} (expected ${EMBED_ZIP_SHA256}, got ${actual})`);
  }
  console.log(`[bundle-sidecar] SHA-256 verified (${actual.slice(0, 16)}…)`);

  mkdirSync(PYTHON_DIR, { recursive: true });
  extractZip(zipBuf, PYTHON_DIR);
  patchPth();

  console.log('[bundle-sidecar] bootstrapping pip via get-pip.py');
  const getPipBuf = await download(GET_PIP_URL);
  const getPipPath = join(tmpdir(), 'dream-get-pip.py');
  writeFileSync(getPipPath, getPipBuf);
  try {
    runOrThrow(PYTHON_EXE, [getPipPath, '--no-warn-script-location']);
  } finally {
    rmSync(getPipPath, { force: true });
  }

  // The current get-pip.py bootstrap installs pip only. Install the build
  // backend and wheel explicitly before disabling build isolation below.
  console.log('[bundle-sidecar] installing build dependencies: setuptools + wheel');
  runOrThrow(PYTHON_EXE, [
    '-m',
    'pip',
    'install',
    '--no-warn-script-location',
    'setuptools',
    'wheel',
  ]);

  // Non-editable install from the repository root. NEVER `-e` — an editable
  // install would point at this build machine's path and be dead on the user's
  // PC. `--no-build-isolation` uses the setuptools and wheel packages
  // installed explicitly above (the embeddable distribution ships no
  // ensurepip, so an isolated build cannot bootstrap itself).
  console.log(`[bundle-sidecar] installing Dream (non-editable) from ${REPO_ROOT}`);
  runOrThrow(PYTHON_EXE, [
    '-m',
    'pip',
    'install',
    '--no-warn-script-location',
    '--no-build-isolation',
    REPO_ROOT,
  ]);

  // Smoke: the kernel must import or the release job must go red.
  console.log('[bundle-sidecar] smoke test: import dream.bridge');
  if (runStatus(PYTHON_EXE, ['-c', 'import dream.bridge']) !== 0) {
    fail('smoke test failed: `import dream.bridge` did not exit 0');
  }

  if (fullStt) {
    console.log(
      '[bundle-sidecar] full mode: installing the stt + tts extras (faster-whisper, piper, edge-tts)',
    );
    runOrThrow(PYTHON_EXE, [
      '-m',
      'pip',
      'install',
      '--no-warn-script-location',
      '--no-build-isolation',
      fullPipSpec(),
    ]);

    console.log(
      '[bundle-sidecar] full mode: smoke test: import dream.bridge + faster_whisper + piper + edge_tts',
    );
    if (
      runStatus(PYTHON_EXE, ['-c', 'import dream.bridge, faster_whisper, piper, edge_tts']) !== 0
    ) {
      fail(
        'smoke test failed: `import dream.bridge, faster_whisper, piper, edge_tts` did not exit 0',
      );
    }

    const modelDir = sttModelDir();
    console.log(
      `[bundle-sidecar] full mode: downloading Whisper model '${STT_MODEL_ID}' ` +
        `(~148 MB, pinned revision ${STT_MODEL_REVISION.slice(0, 8)}…)`,
    );
    runOrThrow(PYTHON_EXE, ['-c', sttModelDownloadPython(modelDir)]);

    const modelBin = join(modelDir, 'model.bin');
    if (!existsSync(modelBin) || statSync(modelBin).size < STT_MODEL_MIN_BYTES) {
      fail(
        `bundled model incomplete: ${modelBin} is missing or under ${STT_MODEL_MIN_BYTES} bytes`,
      );
    }
    console.log(
      `[bundle-sidecar] full mode: model ready (${(statSync(modelBin).size / 1e6).toFixed(1)} MB)`,
    );

    const voiceDir = ttsVoiceDir();
    console.log(
      `[bundle-sidecar] full mode: downloading offline Piper voice '${TTS_VOICE_STEM}' ` +
        `(~63 MB, pinned revision ${TTS_VOICE_REVISION.slice(0, 8)}…)`,
    );
    runOrThrow(PYTHON_EXE, ['-c', ttsVoiceDownloadPython(voiceDir)]);

    const voiceOnnx = join(voiceDir, TTS_VOICE_REPO_PATH, `${TTS_VOICE_STEM}.onnx`);
    const voiceJson = join(voiceDir, TTS_VOICE_REPO_PATH, `${TTS_VOICE_STEM}.onnx.json`);
    if (
      !existsSync(voiceOnnx) ||
      statSync(voiceOnnx).size < TTS_VOICE_MIN_BYTES ||
      !existsSync(voiceJson)
    ) {
      fail(
        `bundled voice incomplete: ${voiceOnnx} (or its .onnx.json) is missing or under ` +
          `${TTS_VOICE_MIN_BYTES} bytes`,
      );
    }
    console.log(
      `[bundle-sidecar] full mode: offline voice ready (${(statSync(voiceOnnx).size / 1e6).toFixed(1)} MB)`,
    );
  }

  console.log(
    fullStt
      ? '[bundle-sidecar] full bundle ready: CPython + kernel + faster-whisper + model + piper voice'
      : '[bundle-sidecar] bundled CPython + Dream kernel ready',
  );
}

// Run only when executed directly (`node ./scripts/bundle-sidecar.mjs`), not
// when imported — e.g. by a unit test of the pure `findPthName` helper.
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main();
}
