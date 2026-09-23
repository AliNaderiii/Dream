import { describe, expect, it } from 'vitest';
import { BridgeUnavailableError, api, call, isTauri, pdfSiblingPath, status } from './bridge.js';

describe('browser environment (no Tauri)', () => {
  it('isTauri is false', () => {
    expect(isTauri).toBe(false);
  });

  it('call() rejects with BridgeUnavailableError, never fake data', async () => {
    await expect(call('stt.transcribe', { file_path: 'x' })).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
  });

  it('status() reports browser honestly', async () => {
    await expect(status()).resolves.toBe('browser');
  });

  it('workspace + vision helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.wsRootsList()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.wsFilesList('wsr1', '')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.wsFilesPreview('wsr1', 'a.txt')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.visionCaptureScreen()).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it('tts helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.ttsEngines()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.ttsVoices('piper')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.ttsSynthesize('سلام')).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it('pickFile-style guards: the error message names the browser preview', async () => {
    try {
      await call('anything');
      expect.unreachable();
    } catch (e) {
      expect(e.message).toContain('پیش‌نمایش مرورگر');
    }
  });
});

describe('pdfSiblingPath()', () => {
  it('derives <base>.report.pdf from a source path', () => {
    expect(pdfSiblingPath('C:\\Users\\a\\voice.ogg')).toBe('C:\\Users\\a\\voice.report.pdf');
    expect(pdfSiblingPath('/home/a/invoice.png')).toBe('/home/a/invoice.report.pdf');
  });

  it('supports a custom suffix', () => {
    expect(pdfSiblingPath('/tmp/x.wav', 'transcript')).toBe('/tmp/x.transcript.pdf');
  });

  it('handles files without an extension', () => {
    expect(pdfSiblingPath('/tmp/README')).toBe('/tmp/README.report.pdf');
  });
});
