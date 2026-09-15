/**
 * Polyglot Sandbox & Code Execution Studio Component.
 *
 * Provides live code interpretation, execution status tracking,
 * output inspection, data science profiling, and artifact management.
 */

import {
  AlertTriangle,
  BarChart2,
  CheckCircle2,
  Code2,
  FileCode,
  FolderArchive,
  Layers,
  Play,
  RefreshCw,
  Server,
  Terminal,
  Trash2,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs } from '@/components/ui/tabs';
import { useTranslation } from '@/lib/i18n';
import { useBridge } from '@/lib/bridge/hooks';
import {
  sandboxAnalyzeData,
  sandboxGetStatus,
  sandboxListArtifacts,
  sandboxListBackends,
  sandboxReset,
  sandboxRunCode,
  sandboxSetBackend,
  type DatasetSummary,
  type ExecutionArtifact,
  type ExecutionResult,
  type SandboxStatusResult,
  type TerminalBackendInfo,
} from '@/lib/bridge/sandbox';
import { SandboxSettings } from './sandbox-settings';

const LANGUAGES = [
  { id: 'python', label: 'Python (REPL)' },
  { id: 'bash', label: 'Bash / Shell' },
  { id: 'sql', label: 'SQL' },
  { id: 'javascript', label: 'JavaScript' },
];

const SAMPLE_SNIPPETS: Record<string, string> = {
  python: `# Data computation and analysis\nimport math\n\ndata = [12, 45, 67, 89, 34, 56, 78]\nmean = sum(data) / len(data)\nvariance = sum((x - mean) ** 2 for x in data) / len(data)\nstd_dev = math.sqrt(variance)\n\nprint(f"Count: {len(data)}")\nprint(f"Mean: {mean:.2f}")\nprint(f"Std Dev: {std_dev:.2f}")`,
  bash: `# Process inspection\necho "Current Working Directory: $PWD"\necho "User Sandbox Isolation: Active"`,
  sql: `-- Tabular Query\nSELECT name, age, salary FROM employees WHERE salary > 50000 ORDER BY salary DESC;`,
  javascript: `// Vector calculation\nconst items = [10, 20, 30, 40, 50];\nconst squared = items.map(n => n * n);\nconsole.log("Squared items:", squared);`,
};

export function PolyglotSandboxStudio() {
  const { t } = useTranslation('sandbox');
  const { client } = useBridge();

  const [activeTab, setActiveTab] = useState<string>('console');
  const [selectedLanguage, setSelectedLanguage] = useState<string>('python');
  const [code, setCode] = useState<string>(SAMPLE_SNIPPETS.python);
  const [running, setRunning] = useState<boolean>(false);
  const [lastResult, setLastResult] = useState<ExecutionResult | null>(null);

  const [datasetInput, setDatasetInput] = useState<string>(
    'feature,category,value,confidence\nA1,Sensor,45.2,0.98\nA2,Sensor,51.8,0.94\nB1,Actuator,12.0,0.99\nB2,Actuator,18.5,0.91',
  );
  const [dataSummary, setDataSummary] = useState<DatasetSummary | null>(null);
  const [dataReport, setDataReport] = useState<string>('');
  const [analyzing, setAnalyzing] = useState<boolean>(false);

  const [artifacts, setArtifacts] = useState<ExecutionArtifact[]>([]);
  const [status, setStatus] = useState<SandboxStatusResult | null>(null);
  const [backends, setBackends] = useState<TerminalBackendInfo[]>([]);
  const [activeBackend, setActiveBackend] = useState<string>('local');
  const [message, setMessage] = useState<string | null>(null);

  const refreshState = useCallback(async () => {
    try {
      const [sRes, aRes, bRes] = await Promise.all([
        sandboxGetStatus(client),
        sandboxListArtifacts(client),
        sandboxListBackends(client),
      ]);
      setStatus(sRes);
      setArtifacts(aRes.artifacts);
      setBackends(bRes.backends);
      setActiveBackend(bRes.active_backend);
    } catch {
      // Ignored in offline fallback
    }
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const [sRes, aRes, bRes] = await Promise.all([
          sandboxGetStatus(client),
          sandboxListArtifacts(client),
          sandboxListBackends(client),
        ]);
        if (!cancelled) {
          setStatus(sRes);
          setArtifacts(aRes.artifacts);
          setBackends(bRes.backends);
          setActiveBackend(bRes.active_backend);
        }
      } catch {
        // Ignored
      }
    };
    void init();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleLanguageChange = (lang: string) => {
    setSelectedLanguage(lang);
    if (!code.trim() || Object.values(SAMPLE_SNIPPETS).includes(code)) {
      setCode(SAMPLE_SNIPPETS[lang] || '');
    }
  };

  const handleRunCode = async () => {
    if (!code.trim() || running) return;
    setRunning(true);
    setMessage(null);
    try {
      const res = await sandboxRunCode(client, code, selectedLanguage);
      setLastResult(res.result);
      await refreshState();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  const handleAnalyzeData = async () => {
    if (!datasetInput.trim() || analyzing) return;
    setAnalyzing(true);
    setMessage(null);
    try {
      const res = await sandboxAnalyzeData(client, datasetInput);
      setDataSummary(res.summary);
      setDataReport(res.markdown_report);
      await refreshState();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalyzing(false);
    }
  };

  const handleReset = async () => {
    try {
      await sandboxReset(client);
      setLastResult(null);
      setDataSummary(null);
      setDataReport('');
      await refreshState();
      setMessage(t('resetEnv'));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSwitchBackend = async (b: string) => {
    try {
      await sandboxSetBackend(client, b);
      setActiveBackend(b);
      await refreshState();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  const tabs = [
    {
      id: 'console',
      label: t('tabConsole'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-caption font-medium text-fg-secondary">{t('language')}:</span>
              <div className="flex rounded-md border border-border-default bg-surface p-0.5">
                {LANGUAGES.map((l) => (
                  <Button
                    key={l.id}
                    size="sm"
                    variant={selectedLanguage === l.id ? 'primary' : 'ghost'}
                    onClick={() => handleLanguageChange(l.id)}
                  >
                    {l.label}
                  </Button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleRunCode()}
                disabled={running || !code.trim()}
              >
                {running ? (
                  <RefreshCw className="mr-1.5 size-4 animate-spin" />
                ) : (
                  <Play className="mr-1.5 size-4" />
                )}
                {running ? t('executing') : t('executeCode')}
              </Button>
            </div>
          </div>

          <div className="relative rounded-lg border border-border-default bg-surface-2 p-2">
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="# Enter code here..."
              rows={9}
              className="w-full resize-y rounded-md bg-transparent p-2 font-mono text-body text-fg-primary outline-none ltr-island"
            />
          </div>

          {lastResult && (
            <div className="flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {lastResult.status === 'success' && (
                    <Badge variant="success">
                      <CheckCircle2 className="mr-1 size-3.5" />
                      {t('statusSuccess')}
                    </Badge>
                  )}
                  {lastResult.status === 'blocked' && (
                    <Badge variant="danger">
                      <AlertTriangle className="mr-1 size-3.5" />
                      {t('statusBlocked')}
                    </Badge>
                  )}
                  {lastResult.status === 'error' && (
                    <Badge variant="danger">
                      <XCircle className="mr-1 size-3.5" />
                      {t('statusError')}
                    </Badge>
                  )}
                  <span className="text-caption text-fg-muted">
                    {t('duration')}: {lastResult.duration_ms.toFixed(1)}ms · {t('exitCode')}:{' '}
                    {lastResult.exit_code}
                  </span>
                </div>
                {lastResult.variables_updated.length > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-caption text-fg-secondary">{t('variablesUpdated')}:</span>
                    {lastResult.variables_updated.map((v) => (
                      <Badge key={v} variant="neutral">
                        {v}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              {lastResult.stdout && (
                <div className="flex flex-col gap-1">
                  <span className="text-caption font-medium text-fg-secondary">
                    {t('stdoutLabel')}
                  </span>
                  <pre className="overflow-x-auto rounded-md bg-surface-2 p-3 font-mono text-body text-fg-primary ltr-island">
                    {lastResult.stdout}
                  </pre>
                </div>
              )}

              {lastResult.stderr && (
                <div className="flex flex-col gap-1">
                  <span className="text-caption font-medium text-danger-fg">
                    {t('stderrLabel')}
                  </span>
                  <pre className="overflow-x-auto rounded-md bg-danger-bg p-3 font-mono text-body text-danger-fg ltr-island">
                    {lastResult.stderr}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'profiler',
      label: t('tabProfiler'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-caption font-medium text-fg-secondary">
              {t('dataInputPlaceholder')}
            </span>
            <textarea
              value={datasetInput}
              onChange={(e) => setDatasetInput(e.target.value)}
              rows={5}
              className="w-full resize-y rounded-lg border border-border-default bg-surface p-2.5 font-mono text-body text-fg-primary outline-none ltr-island"
            />
            <div className="flex justify-end">
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleAnalyzeData()}
                disabled={analyzing || !datasetInput.trim()}
              >
                {analyzing ? (
                  <RefreshCw className="mr-1.5 size-4 animate-spin" />
                ) : (
                  <BarChart2 className="mr-1.5 size-4" />
                )}
                {t('analyzeData')}
              </Button>
            </div>
          </div>

          {dataSummary && (
            <div className="flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-4">
              <h3 className="text-h3 font-bold">{t('datasetSummary')}</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="flex flex-col gap-0.5 rounded-md bg-surface-2 p-3">
                  <span className="text-caption text-fg-muted">{t('totalRows')}</span>
                  <span className="text-h2 font-bold">{dataSummary.total_rows}</span>
                </div>
                <div className="flex flex-col gap-0.5 rounded-md bg-surface-2 p-3">
                  <span className="text-caption text-fg-muted">{t('totalColumns')}</span>
                  <span className="text-h2 font-bold">{dataSummary.total_columns}</span>
                </div>
                <div className="flex flex-col gap-0.5 rounded-md bg-surface-2 p-3 col-span-2">
                  <span className="text-caption text-fg-muted">Columns</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {dataSummary.column_names.map((col) => (
                      <Badge key={col} variant="neutral">
                        {col} ({dataSummary.column_types[col] || 'any'})
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>

              {dataReport && (
                <div className="rounded-md bg-surface-2 p-3 text-body whitespace-pre-wrap font-mono">
                  {dataReport}
                </div>
              )}
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'artifacts',
      label: t('tabArtifacts'),
      content: (
        <div className="flex flex-col gap-3">
          {artifacts.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 text-fg-muted">
              <FolderArchive className="size-8 mb-2 stroke-1" />
              <p className="text-body">{t('noArtifacts')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {artifacts.map((art) => (
                <div
                  key={art.file_path}
                  className="flex flex-col justify-between rounded-lg border border-border-default bg-surface p-3"
                >
                  <div className="flex items-start gap-2.5">
                    <FileCode className="size-5 shrink-0 text-accent" />
                    <div className="flex flex-col min-w-0">
                      <span className="truncate text-body font-medium">{art.name}</span>
                      <span className="text-caption text-fg-muted">
                        {(art.size_bytes / 1024).toFixed(1)} KB · {art.mime_type}
                      </span>
                    </div>
                  </div>
                  <span className="mt-2 text-caption text-fg-secondary">{art.description_fa}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'settings',
      label: t('tabSettings'),
      content: <SandboxSettings />,
    },
  ];

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border-default pb-3">
        <div>
          <h2 className="text-h1 font-bold">{t('studioTitle')}</h2>
          <p className="text-body text-fg-secondary">{t('studioSubtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Active Backend Selector */}
          <div className="flex items-center gap-1.5 rounded-md border border-border-default bg-surface px-2.5 py-1">
            <Server className="size-4 text-fg-muted" />
            <span className="text-caption text-fg-secondary">{t('backendLabel')}:</span>
            <select
              value={activeBackend}
              onChange={(e) => void handleSwitchBackend(e.target.value)}
              className="bg-transparent text-caption font-medium outline-none text-fg-primary"
            >
              {backends.map((b) => (
                <option key={b.type} value={b.type}>
                  {b.type.toUpperCase()} {b.available ? '✓' : '(offline)'}
                </option>
              ))}
            </select>
          </div>

          <Button variant="ghost" size="sm" onClick={() => void handleReset()}>
            <Trash2 className="mr-1.5 size-4" />
            {t('resetEnv')}
          </Button>
        </div>
      </header>

      {message && (
        <div className="rounded-md bg-accent-bg p-2.5 text-caption text-accent-fg">{message}</div>
      )}

      {/* Metrics Header */}
      {status && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <Terminal className="size-5 text-accent" />
            <div className="flex flex-col">
              <span className="text-caption text-fg-muted">Executions</span>
              <span className="text-body font-bold">{status.total_executions}</span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <Layers className="size-5 text-success-fg" />
            <div className="flex flex-col">
              <span className="text-caption text-fg-muted">Variables</span>
              <span className="text-body font-bold">{status.variables_count}</span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <FolderArchive className="size-5 text-warning-fg" />
            <div className="flex flex-col">
              <span className="text-caption text-fg-muted">Artifacts</span>
              <span className="text-body font-bold">{status.total_artifacts}</span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <Code2 className="size-5 text-fg-muted" />
            <div className="flex flex-col truncate">
              <span className="text-caption text-fg-muted">Workspace</span>
              <span className="truncate font-mono text-caption">{status.workspace_dir}</span>
            </div>
          </div>
        </div>
      )}

      <Tabs
        label="Sandbox Studio Tabs"
        items={tabs}
        value={activeTab}
        onValueChange={setActiveTab}
      />
    </div>
  );
}
