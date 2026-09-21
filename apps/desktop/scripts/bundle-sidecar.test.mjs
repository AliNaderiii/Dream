import { describe, expect, it } from 'vitest';
import { join } from 'node:path';
import {
  findPthName,
  sttModelDir,
  sttModelDownloadPython,
  sttPipSpec,
  wantsFullStt,
} from './bundle-sidecar.mjs';

describe('findPthName', () => {
  it('prefers the canonical python312._pth', () => {
    expect(findPthName(['DLLs', 'python.exe', 'python312._pth'])).toBe('python312._pth');
  });

  it('accepts any python3XX._pth when the canonical name is absent', () => {
    expect(findPthName(['python313._pth', 'python.exe'])).toBe('python313._pth');
  });

  it('returns null when no ._pth file matches', () => {
    expect(findPthName(['DLLs', 'python.exe', 'README.txt'])).toBeNull();
  });
});

describe('wantsFullStt', () => {
  it('defaults to a slim bundle', () => {
    expect(wantsFullStt([], {})).toBe(false);
    expect(wantsFullStt(['node', 'bundle-sidecar.mjs'], { DREAM_SIDECAR_STT: '0' })).toBe(false);
  });

  it('is enabled by --full', () => {
    expect(wantsFullStt(['node', 'bundle-sidecar.mjs', '--full'], {})).toBe(true);
  });

  it('is enabled by DREAM_SIDECAR_STT=1', () => {
    expect(wantsFullStt([], { DREAM_SIDECAR_STT: '1' })).toBe(true);
  });
});

describe('sttPipSpec', () => {
  it('appends the stt extra to the repository root path', () => {
    expect(sttPipSpec('C:\\repo\\Dream')).toBe('C:\\repo\\Dream[stt]');
  });
});

describe('sttModelDir', () => {
  it('nests the pinned base model under <python>/models', () => {
    const pythonDir = join('C:', 'app', 'python');
    expect(sttModelDir(pythonDir)).toBe(join(pythonDir, 'models', 'faster-whisper-base'));
  });
});

describe('sttModelDownloadPython', () => {
  it('pins the repo, revision, and an escaped local_dir', () => {
    const modelDir = join('C:', 'app', 'python', 'models', 'faster-whisper-base');
    const code = sttModelDownloadPython(modelDir);
    expect(code).toContain('from huggingface_hub import snapshot_download');
    expect(code).toContain('repo_id="Systran/faster-whisper-base"');
    expect(code).toContain('revision="ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"');
    // JSON.stringify escaping keeps the Windows path a valid Python literal.
    expect(code).toContain(`local_dir=${JSON.stringify(modelDir)}`);
  });
});
