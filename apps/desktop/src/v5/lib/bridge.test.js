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

  it('browse + sandbox helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.browsePropose('https://x.example')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.browseList()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.browseApprove('brw_x')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.sandboxRun('print(1)')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.sandboxStatus()).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it('webbrowser helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.wbStatus()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.wbAttach(9222)).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.wbNavigate('https://x.example')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.wbClick('a')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.wbScreenshot()).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it('reasoning + dialectic helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.reasoningPlanTree('هدف')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.reasoningExpand('t', 'n', ['فکر'])).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.reasoningMcts('t', ['فکر'])).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.dialecticAdd('general', 'باور')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.dialecticSnapshot()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.dialecticTensions()).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it('provider-hubs helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.phRuntimes()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.phRoute()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.phTest('ollama')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.phModels('ollama')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.phSelectModel('ollama', 'qwen2.5:7b')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.phDiagnose('vllm')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.phGateway()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.phGatewayUpdate({ enabled: true })).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.phCatalog('ollama')).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it('space + liveloop helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.spaceList()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.spaceCreate('فروشگاه', 'fa', 'guarded')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.spaceGet('spc_x')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.spaceAttachFolder('spc_x', 'C:/x')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.spaceSetInstruction('spc_x', { text: 'قواعد' })).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.spaceSetInstruction('spc_x', { path: 'C:/x.md' })).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.spaceProposeDraft('spc_x', 'هر روز ساعت ۹')).rejects.toBeInstanceOf(
      BridgeUnavailableError,
    );
    await expect(api.spaceApproveDraft('dft_x')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.spaceDenyDraft('dft_x')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.llArmDraft('dft_x')).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it('agent-mode helpers are wired to the real bridge — honest in the browser', async () => {
    await expect(api.amGoal('هدف', ['معیار'])).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.amReport('goal_x')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.amStop({ goalId: 'goal_x' })).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.amStop({})).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.amStatus()).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.shPropose('ls -la')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.shPropose('ls', 'C:/root')).rejects.toBeInstanceOf(BridgeUnavailableError);
    await expect(api.shExecute('sh_x')).rejects.toBeInstanceOf(BridgeUnavailableError);
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
