/** In-memory echo fallback implementation for sandbox.* bridge methods. */

import type {
  DatasetSummary,
  ExecutionArtifact,
  ExecutionResult,
  SandboxStatusResult,
  TerminalBackendInfo,
} from './sandbox';

const state: {
  executions: ExecutionResult[];
  artifacts: ExecutionArtifact[];
  activeBackend: string;
} = {
  executions: [],
  artifacts: [],
  activeBackend: 'local',
};

export function echoSandboxRunCode(
  code: string,
  language = 'python',
  _timeoutSeconds = 15.0,
): {
  status: string;
  result: ExecutionResult;
} {
  if (!code || !code.trim()) {
    throw new Error('code must be a non-empty string');
  }

  const isBlocked = code.includes('rm -rf /') || code.includes('os.system');
  const now = Date.now() / 1000;

  if (isBlocked) {
    const blockedRes: ExecutionResult = {
      language,
      status: 'blocked',
      exit_code: 1,
      stdout: '',
      stderr: 'Security Policy Refusal: Destructive command blocked by L3 floor.',
      duration_ms: 1.2,
      artifacts: [],
      error_message: 'Blocked by L3 security policy',
      variables_updated: [],
      timestamp: now,
    };
    state.executions.push(blockedRes);
    return { status: 'blocked', result: blockedRes };
  }

  const result: ExecutionResult = {
    language,
    status: 'success',
    exit_code: 0,
    stdout: `[Echo Sandbox] Executed ${language} snippet successfully.\nOutput: 42`,
    stderr: '',
    duration_ms: 4.8,
    artifacts: [],
    error_message: '',
    variables_updated: ['x', 'result'],
    timestamp: now,
  };

  state.executions.push(result);
  return {
    status: 'success',
    result,
  };
}

export function echoSandboxAnalyzeData(dataOrPath: string): {
  status: string;
  summary: DatasetSummary;
  markdown_report: string;
} {
  if (!dataOrPath || !dataOrPath.trim()) {
    throw new Error('data_or_path must be a non-empty string');
  }

  const summary: DatasetSummary = {
    total_rows: 5,
    total_columns: 3,
    column_names: ['id', 'metric', 'value'],
    column_types: { id: 'int', metric: 'string', value: 'float' },
    null_counts: { id: 0, metric: 0, value: 0 },
    numeric_stats: {
      value: { mean: 45.2, min: 10.0, max: 98.5, std: 12.3 },
    },
    sample_preview: [
      { id: 1, metric: 'latency', value: 12.4 },
      { id: 2, metric: 'throughput', value: 88.1 },
    ],
  };

  const markdown_report =
    '### گزارش تحلیل آماری داده‌ها\n- **تعداد ردیف‌ها:** ۵\n- **تعداد ستون‌ها:** ۳\n- **کیفیت داده:** ۱۰۰٪ بدون مقدار گمشده';

  return {
    status: 'success',
    summary,
    markdown_report,
  };
}

export function echoSandboxListArtifacts(): {
  status: string;
  artifacts: ExecutionArtifact[];
  count: number;
} {
  return {
    status: 'success',
    artifacts: [...state.artifacts],
    count: state.artifacts.length,
  };
}

export function echoSandboxGetStatus(): SandboxStatusResult {
  return {
    status: 'healthy',
    total_executions: state.executions.length,
    total_artifacts: state.artifacts.length,
    workspace_dir: '/tmp/dream_sandbox',
    variables_count: 5,
    last_execution_status:
      state.executions.length > 0 ? state.executions[state.executions.length - 1].status : 'ready',
  };
}

export function echoSandboxReset(): { status: string; message: string } {
  state.executions = [];
  state.artifacts = [];
  return {
    status: 'reset',
    message: 'Echo sandbox reset successfully.',
  };
}

export function echoSandboxListBackends(): {
  status: string;
  backends: TerminalBackendInfo[];
  active_backend: string;
} {
  const backends: TerminalBackendInfo[] = [
    {
      type: 'local',
      is_active: state.activeBackend === 'local',
      available: true,
      details: 'Local Process Host Environment',
      latency_ms: 0.5,
      metadata: {},
    },
    {
      type: 'docker',
      is_active: state.activeBackend === 'docker',
      available: true,
      details: 'Docker Isolated Container Sandbox',
      latency_ms: 12.0,
      metadata: {},
    },
    {
      type: 'modal',
      is_active: state.activeBackend === 'modal',
      available: false,
      details: 'Modal Cloud Serverless Container',
      latency_ms: 0.0,
      metadata: {},
    },
  ];

  return {
    status: 'success',
    backends,
    active_backend: state.activeBackend,
  };
}

export function echoSandboxSetBackend(backend: string): {
  status: string;
  active_backend: string;
} {
  state.activeBackend = backend;
  return {
    status: 'success',
    active_backend: backend,
  };
}
