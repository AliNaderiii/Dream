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
  writeFileSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
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
 * Enable `site` in the embeddable distribution's `python312._pth` and make the
 * `Lib/site-packages` directory (where pip installs land) importable.
 */
function patchPth() {
  const pth = join(PYTHON_DIR, `python${PYTHON_VERSION.replace(/\D/g, '')}._pth`);
  if (!existsSync(pth)) fail(`missing ${pth} — unexpected embeddable layout`);

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
    console.log(`[bundle-sidecar] skipping — Windows-only CPython bundle (platform ${process.platform})`);
    return;
  }

  // Idempotency: a working interpreter + kernel means there is nothing to do.
  if (existsSync(PYTHON_EXE) && runStatus(PYTHON_EXE, ['-c', 'import dream.bridge']) === 0) {
    console.log('[bundle-sidecar] bundled interpreter + Dream kernel already present — skipping');
    return;
  }

  console.log(`[bundle-sidecar] downloading CPython ${PYTHON_VERSION} embeddable amd64`);
  const zipBuf = await download(EMBED_ZIP_URL);
  const actual = sha256(zipBuf);
  if (actual !== EMBED_ZIP_SHA256) {
    fail(
      `SHA-256 mismatch for ${EMBED_ZIP_URL} (expected ${EMBED_ZIP_SHA256}, got ${actual})`,
    );
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

  // Non-editable install from the repository root. NEVER `-e` — an editable
  // install would point at this build machine's path and be dead on the user's
  // PC. `--no-build-isolation` uses the setuptools get-pip.py just installed
  // (the embeddable distribution ships no ensurepip, so an isolated build
  // cannot bootstrap itself).
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

  console.log('[bundle-sidecar] bundled CPython + Dream kernel ready');
}

main();
