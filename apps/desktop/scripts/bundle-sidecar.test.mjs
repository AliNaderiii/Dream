import { describe, expect, it } from 'vitest';
import { join } from 'node:path';
import {
  findPthName,
  sttModelDir,
  sttModelDownloadPython,
  sttPipSpec,
  ttsVoiceDir,
  ttsVoiceDownloadPython,
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

describe('sttPipSpec / fullPipSpec', () => {
  it('appends the stt + tts extras to the repository root path', () => {
    expect(sttPipSpec('C:\\repo\\Dream')).toBe('C:\\repo\\Dream[stt,tts,browser]');
  });
});

describe('ttsVoiceDir', () => {
  it('nests the pinned piper voices under <python>/models', () => {
    const pythonDir = join('C:', 'app', 'python');
    expect(ttsVoiceDir(pythonDir)).toBe(join(pythonDir, 'models', 'piper-voices'));
  });
});

describe('ttsVoiceDownloadPython', () => {
  it('pins the repo, revision, and both voice files', () => {
    const voiceDir = join('C:', 'app', 'python', 'models', 'piper-voices');
    const code = ttsVoiceDownloadPython(voiceDir);
    expect(code).toContain('from huggingface_hub import hf_hub_download');
    expect(code).toContain('repo_id="rhasspy/piper-voices"');
    expect(code).toContain('revision="c10ece1aade47bb51c153c893d14e5bf8e5b7117"');
    expect(code).toContain('fa_IR-reza_ibrahim-medium.onnx');
    expect(code).toContain('fa_IR-reza_ibrahim-medium.onnx.json');
    expect(code).toContain(`local_dir=${JSON.stringify(voiceDir)}`);
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
