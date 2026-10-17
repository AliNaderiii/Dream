/**
 * Code view tests.
 *
 * Two layers:
 *
 *  1. Browser-honest defaults: outside the desktop shell there is no core, so
 *     nothing executes, nothing is faked, and no evidence drawer opens by itself.
 *  2. The *contract*: `sandbox.run_code` answers `{status, result}`, and every
 *     status the backend can return (`success`, `error`, `timeout`, `cancelled`,
 *     `denied`, `unavailable`) must render. Before MASTER-P0 the view read
 *     `result.result.stdout` while the handler returned a flat `{stdout}`, so a
 *     successful run showed a red error chip and *no output at all*. These tests
 *     mount the real view against the real payload shape, which is what keeps
 *     that class of bug from coming back.
 */
import { describe, expect, it, vi, afterEach } from 'vitest';
import { codeView } from './code.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 30));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  codeView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

/** The exact envelope dream.security.codeexec.CodeExecutionResponse.to_dict()
 *  produces for a successful run. */
const successEnvelope = (overrides = {}) => ({
  status: 'success',
  execution_id: 'exe-abc123',
  result: {
    status: 'success',
    execution_id: 'exe-abc123',
    stdout: 'سلام از سندباکس دریم\n',
    stderr: '',
    stdout_path: '',
    stderr_path: '',
    exit_code: 0,
    duration_ms: 42.5,
    timed_out: false,
    truncated: false,
    artifacts: [],
    error: null,
    error_message: '',
    variables_updated: [],
    isolation: {
      backend: 'docker',
      network: 'none',
      rootfs: 'read-only',
      capabilities: 'drop-all',
      no_new_privileges: true,
      privileged: false,
      user: '1001:1001',
      process_limit: 64,
      memory_mb: 1024,
      cpu_count: 1,
      timeout_seconds: 15,
      max_output_bytes: 200000,
      env_policy: 'explicit-minimal (no host environment, no credentials)',
      docker_socket: 'not mounted',
    },
    limits: { timeout_seconds: 15, memory_mb: 1024, network_enabled: false },
    ...overrides,
  },
});

/** Stub the bridge module the view imports, then re-import the view fresh. */
async function mountWithBridge(api) {
  vi.resetModules();
  vi.doMock('../lib/bridge.js', async () => {
    const actual = await vi.importActual('../lib/bridge.js');
    return { ...actual, api: { ...actual.api, ...api } };
  });
  const mod = await import('./code.js');
  const root = document.createElement('div');
  const ctx = { app, settings, openEvidence: () => {} };
  mod.codeView(root, ctx);
  await flush();
  return root;
}

afterEach(() => {
  vi.doUnmock('../lib/bridge.js');
  vi.resetModules();
});

describe('code view — browser-honest defaults', () => {
  it('offers run + reset and states the container-only promise', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('اجرا');
    expect(root.textContent).toContain('بازنشانی نشست');
    expect(root.textContent).toContain('اجرای واقعی پایتون');
    expect(root.textContent).toContain('کانتینر');
    expect(root.textContent).toContain('شبکه خاموش');
  });

  it('says the desktop app is where the sandbox lives — never fakes output', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelector('.files-preview-text')).toBeNull();
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});

describe('code view — the execution contract', () => {
  it('renders the stdout of a successful run (regression: output was invisible)', async () => {
    const root = await mountWithBridge({
      sandboxRun: async () => successEnvelope(),
      sandboxStatus: async () => ({ status: 'healthy', backend: 'docker', available: true }),
      sandboxReset: async () => ({ status: 'reset' }),
    });

    root.querySelector('textarea').value = 'print("hi")';
    root.querySelector('button').click();
    await flush();

    expect(root.querySelector('.files-preview-text').textContent).toContain('سلام از سندباکس دریم');
    expect(root.textContent).toContain('موفق');
    expect(root.textContent).toContain('exit 0');
    expect(root.textContent).not.toContain('خطای برنامه');
  });

  it('shows the isolation profile the backend reported', async () => {
    const root = await mountWithBridge({
      sandboxRun: async () => successEnvelope(),
      sandboxStatus: async () => ({ status: 'healthy', backend: 'docker', available: true }),
      sandboxReset: async () => ({ status: 'reset' }),
    });

    root.querySelector('textarea').value = 'print("hi")';
    root.querySelector('button').click();
    await flush();

    const text = root.textContent;
    expect(text).toContain('شبکه: خاموش');
    expect(text).toContain('فقط‌خواندنی');
    expect(text).toContain('حذف‌شده');
  });

  it.each([
    ['error', 'خطای برنامه', 'ZeroDivisionError'],
    ['timeout', 'مهلت تمام شد', 'مهلت'],
    ['cancelled', 'لغو شد', 'لغو'],
    ['denied', 'رد شد', 'رد شد'],
    ['unavailable', 'در دسترس نیست', 'روی میزبان اجرا نمی‌کند'],
  ])('renders status %s with its bilingual reason', async (status, chip, fragment) => {
    const root = await mountWithBridge({
      sandboxRun: async () => ({
        status,
        execution_id: 'exe-x',
        result: {
          status,
          stdout: '',
          stderr: '',
          exit_code: -1,
          duration_ms: 5,
          timed_out: status === 'timeout',
          truncated: false,
          artifacts: [],
          error: { code: status, reason_en: fragment, reason_fa: fragment, detail: '' },
          error_message: `${fragment}\n${fragment}`,
          variables_updated: [],
          isolation: {},
          limits: {},
        },
      }),
      sandboxStatus: async () => ({ status: 'healthy', backend: 'docker', available: true }),
      sandboxReset: async () => ({ status: 'reset' }),
    });

    root.querySelector('textarea').value = 'print(1)';
    root.querySelector('button').click();
    await flush();

    const text = root.textContent;
    expect(text).toContain(chip);
    expect(text).toContain(fragment);
  });

  it('renders stderr and a truncated marker', async () => {
    const root = await mountWithBridge({
      sandboxRun: async () =>
        successEnvelope({
          status: 'error',
          exit_code: 1,
          stderr: 'Traceback: boom',
          truncated: true,
          stdout_path: '/tmp/sandbox/runs/exe/../stdout.txt',
          error_message: 'error: the program exited with status 1',
        }),
      sandboxStatus: async () => ({ status: 'healthy', backend: 'docker', available: true }),
      sandboxReset: async () => ({ status: 'reset' }),
    });

    root.querySelector('textarea').value = 'boom';
    root.querySelector('button').click();
    await flush();

    const text = root.textContent;
    expect(text).toContain('Traceback: boom');
    expect(text).toContain('خروجی بریده شد');
    expect(text).toContain('خروجی کامل');
  });

  it('lists artifacts with their size', async () => {
    const root = await mountWithBridge({
      sandboxRun: async () =>
        successEnvelope({
          artifacts: [
            { name: 'chart.png', file_path: '/tmp/sandbox/runs/exe/chart.png', size_bytes: 2048 },
          ],
        }),
      sandboxStatus: async () => ({ status: 'healthy', backend: 'docker', available: true }),
      sandboxReset: async () => ({ status: 'reset' }),
    });

    root.querySelector('textarea').value = 'print(1)';
    root.querySelector('button').click();
    await flush();

    const text = root.textContent;
    expect(text).toContain('ARTIFACTS');
    expect(text).toContain('chart.png');
    expect(text).toContain('/tmp/sandbox/runs/exe/chart.png');
  });

  it('surfaces an unavailable runner in the status strip instead of a fake healthy state', async () => {
    const root = await mountWithBridge({
      sandboxRun: async () => successEnvelope(),
      sandboxStatus: async () => ({
        status: 'healthy',
        backend: 'docker',
        available: false,
        total_executions: 0,
        total_artifacts: 0,
      }),
      sandboxReset: async () => ({ status: 'reset' }),
    });

    expect(root.textContent).toContain('بک‌اند در دسترس نیست');
  });

  it('reports a bridge error rather than inventing a result', async () => {
    const root = await mountWithBridge({
      sandboxRun: async () => {
        throw new Error('پاسخی از هسته نیامد');
      },
      sandboxStatus: async () => ({ status: 'healthy', backend: 'docker', available: true }),
      sandboxReset: async () => ({ status: 'reset' }),
    });

    root.querySelector('textarea').value = 'print(1)';
    root.querySelector('button').click();
    await flush();

    expect(root.textContent).toContain('پاسخی از هسته نیامد');
    expect(root.querySelector('.files-preview-text')).toBeNull();
  });

  it('sends only the contract fields to sandbox.run_code', async () => {
    // No mock here: this asserts on the real client, so a renamed field or a
    // re-introduced boundary-widening parameter fails the build.
    await flush();
    const real = await import('../lib/bridge.js');
    const source = real.api.sandboxRun.toString();
    expect(source).toContain("'sandbox.run_code'");
    expect(source).toContain('timeout_seconds');
    expect(source).not.toContain('network_enabled');
    expect(source).not.toContain('workspace_path');
    expect(source).not.toContain('mount_workspace_read_write');
    expect(source).not.toContain('env_vars');
  });

  it('exposes cancel and the daemon probe', async () => {
    await flush();
    const real = await import('../lib/bridge.js');
    expect(real.api.sandboxCancel.toString()).toContain("'sandbox.cancel'");
    expect(real.api.sandboxDaemon.toString()).toContain("'sandbox.status'");
  });
});
