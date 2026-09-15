import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient, type BridgeClient } from './client';
import {
  sandboxAnalyzeData,
  sandboxGetStatus,
  sandboxListArtifacts,
  sandboxListBackends,
  sandboxReset,
  sandboxRunCode,
  sandboxSetBackend,
} from './sandbox';

describe('Sandbox Bridge Client (Echo transport)', () => {
  let client: BridgeClient;

  beforeEach(async () => {
    resetBridgeClient();
    client = getBridgeClient();
    await sandboxReset(client);
  });

  it('runs code snippet and returns execution result', async () => {
    const res = await sandboxRunCode(client, 'x = [i**2 for i in range(10)]');
    expect(res.status).toBe('success');
    expect(res.result.exit_code).toBe(0);
    expect(res.result.variables_updated).toContain('x');
  });

  it('blocks destructive code execution under L3 floor', async () => {
    const res = await sandboxRunCode(client, 'import os; os.system("rm -rf /")');
    expect(res.status).toBe('blocked');
    expect(res.result.status).toBe('blocked');
  });

  it('analyzes tabular dataset and returns summary report', async () => {
    const res = await sandboxAnalyzeData(client, 'a,b\n1,2\n3,4');
    expect(res.status).toBe('success');
    expect(res.summary.total_rows).toBeGreaterThan(0);
    expect(res.markdown_report).toContain('گزارش');
  });

  it('queries status, artifacts, and manages backends', async () => {
    const status = await sandboxGetStatus(client);
    expect(status.status).toBe('healthy');

    const artifacts = await sandboxListArtifacts(client);
    expect(artifacts.status).toBe('success');

    const backends = await sandboxListBackends(client);
    expect(backends.backends.length).toBeGreaterThan(0);

    const setRes = await sandboxSetBackend(client, 'docker');
    expect(setRes.active_backend).toBe('docker');
  });
});
