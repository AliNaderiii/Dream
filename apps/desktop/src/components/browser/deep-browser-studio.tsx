/**
 * Deep Web & Autonomous Browser Studio Component.
 *
 * Provides live interactive viewport, DOM semantic inspector,
 * autonomous deep web crawler, and real-time SSRF security monitoring.
 */

import {
  Camera,
  Compass,
  Eye,
  Globe,
  Layers,
  MousePointer,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Type,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs } from '@/components/ui/tabs';
import {
  browserClick,
  browserClose,
  browserDeepCrawl,
  browserExtractContent,
  browserGetStatus,
  browserLaunch,
  browserNavigate,
  browserReset,
  browserScreenshot,
  browserTypeText,
  type BrowserSession,
  type CrawlResult,
  type PageSnapshot,
} from '@/lib/bridge/browser';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';

export function DeepBrowserStudio() {
  const { t } = useTranslation('browse');
  const { client } = useBridge();

  const [activeTab, setActiveTab] = useState<string>('viewport');
  const [session, setSession] = useState<BrowserSession | null>(null);
  const [snapshot, setSnapshot] = useState<PageSnapshot | null>(null);
  const [backendType, setBackendType] = useState('mock');
  const [urlInput, setUrlInput] = useState('https://docs.dream-ai.dev');
  const [loading, setLoading] = useState(false);
  const [alertMsg, setAlertMsg] = useState<string | null>(null);
  const [alertType, setAlertType] = useState<'success' | 'error' | 'info'>('info');

  // Simulator state
  const [targetSelector, setTargetSelector] = useState('');
  const [typeInput, setTypeInput] = useState('');
  const [screenshotPath, setScreenshotPath] = useState<string | null>(null);

  // Crawler state
  const [crawlGoal, setCrawlGoal] = useState('استخراج مستندات و ساختار API');
  const [crawlDepth, setCrawlDepth] = useState(2);
  const [crawlMaxPages, setCrawlMaxPages] = useState(4);
  const [crawlResult, setCrawlResult] = useState<CrawlResult | null>(null);
  const [crawling, setCrawling] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const res = await browserGetStatus(client);
      setSession(res.session);
    } catch {
      // Ignored
    }
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const res = await browserGetStatus(client);
        if (!cancelled) {
          setSession(res.session);
          if (res.session.current_url && res.session.current_url !== 'about:blank') {
            setUrlInput(res.session.current_url);
            const content = await browserExtractContent(client);
            if (!cancelled) setSnapshot(content.snapshot);
          }
        }
      } catch {
        // Fallback
      }
    };
    void init();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleLaunch = async (backend: string) => {
    setLoading(true);
    try {
      const res = await browserLaunch(client, backend, true);
      setSession(res.session);
      setBackendType(backend);
      setAlertMsg(`Browser session launched with ${backend.toUpperCase()} driver.`);
      setAlertType('success');
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleNavigate = async (urlToVisit?: string) => {
    const target = (urlToVisit || urlInput).trim();
    if (!target) return;
    setLoading(true);
    setAlertMsg(null);
    try {
      const res = await browserNavigate(client, target);
      setSnapshot(res.snapshot);
      setUrlInput(res.snapshot.url);
      if (res.snapshot.screenshot_path) {
        setScreenshotPath(res.snapshot.screenshot_path);
      }
      await refreshStatus();
      setAlertMsg(`Navigated to ${res.snapshot.url} (${res.snapshot.status_code})`);
      setAlertType('success');
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleClickElement = async (selector: string) => {
    if (!selector.trim()) return;
    try {
      const res = await browserClick(client, selector.trim());
      setAlertMsg(res.result.message);
      setAlertType('success');
      await refreshStatus();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    }
  };

  const handleTypeText = async () => {
    if (!targetSelector.trim() || !typeInput) return;
    try {
      const res = await browserTypeText(client, targetSelector.trim(), typeInput);
      setAlertMsg(`Typed '${res.result.text}' into ${targetSelector}`);
      setAlertType('success');
      setTypeInput('');
      await refreshStatus();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    }
  };

  const handleScreenshot = async () => {
    try {
      const res = await browserScreenshot(client);
      setScreenshotPath(res.screenshot_path);
      setAlertMsg(`Screenshot saved at ${res.screenshot_path}`);
      setAlertType('success');
      await refreshStatus();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    }
  };

  const handleDeepCrawl = async () => {
    if (!urlInput.trim() || crawling) return;
    setCrawling(true);
    setAlertMsg(null);
    try {
      const res = await browserDeepCrawl(
        client,
        urlInput.trim(),
        crawlGoal.trim(),
        crawlDepth,
        crawlMaxPages,
      );
      setCrawlResult(res);
      setAlertMsg(`Crawl complete: ${res.total_pages} pages extracted.`);
      setAlertType('success');
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    } finally {
      setCrawling(false);
    }
  };

  const handleReset = async () => {
    try {
      await browserReset(client);
      setSnapshot(null);
      setCrawlResult(null);
      setScreenshotPath(null);
      await refreshStatus();
      setAlertMsg(t('resetSession'));
      setAlertType('info');
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    }
  };

  const handleCloseSession = async () => {
    try {
      await browserClose(client);
      await refreshStatus();
      setAlertMsg(t('closeSession'));
      setAlertType('info');
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
      setAlertType('error');
    }
  };

  const tabs = [
    {
      id: 'viewport',
      label: t('tabLiveViewport'),
      content: (
        <div className="flex flex-col gap-4">
          {/* Action Simulator Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-default bg-surface p-3">
            <div className="flex flex-1 flex-wrap items-center gap-2">
              <input
                type="text"
                placeholder={t('selectorPlaceholder')}
                aria-label={t('selectorPlaceholder')}
                value={targetSelector}
                onChange={(e) => setTargetSelector(e.target.value)}
                className="h-8 min-w-44 flex-1 rounded-md border border-border-default bg-surface-2 px-2.5 font-mono text-caption outline-none"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleClickElement(targetSelector)}
                disabled={!targetSelector.trim()}
              >
                <MousePointer className="mr-1 size-3.5" />
                {t('actionClick')}
              </Button>
              <input
                type="text"
                placeholder={t('textPlaceholder')}
                aria-label={t('textPlaceholder')}
                value={typeInput}
                onChange={(e) => setTypeInput(e.target.value)}
                className="h-8 min-w-36 flex-1 rounded-md border border-border-default bg-surface-2 px-2.5 text-caption outline-none"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleTypeText()}
                disabled={!targetSelector.trim() || !typeInput.trim()}
              >
                <Type className="mr-1 size-3.5" />
                {t('actionType')}
              </Button>
            </div>
            <Button variant="secondary" size="sm" onClick={() => void handleScreenshot()}>
              <Camera className="mr-1 size-3.5" />
              {t('actionScreenshot')}
            </Button>
          </div>

          {/* Viewport Simulation Box */}
          <div className="flex flex-col overflow-hidden rounded-xl border border-border-default bg-surface shadow-sm">
            {/* Viewport Window Header */}
            <div className="flex items-center justify-between border-b border-border-default bg-surface-2 px-4 py-2.5">
              <div className="flex items-center gap-2">
                <div className="flex gap-1.5">
                  <div className="size-3 rounded-full bg-danger-fg opacity-80" />
                  <div className="size-3 rounded-full bg-warning-fg opacity-80" />
                  <div className="size-3 rounded-full bg-success-fg opacity-80" />
                </div>
                <span className="font-medium text-caption text-fg-muted">
                  {snapshot?.title || session?.page_title || 'About Blank'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {snapshot && (
                  <Badge variant={snapshot.status_code === 200 ? 'success' : 'warning'}>
                    HTTP {snapshot.status_code}
                  </Badge>
                )}
                <Badge variant="neutral">
                  <Layers className="mr-1 size-3" />
                  {snapshot?.elements.length ?? 0} Elements
                </Badge>
              </div>
            </div>

            {/* Viewport Content */}
            <div className="flex min-h-64 flex-col gap-4 p-5">
              {snapshot ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-h3 font-semibold text-fg-primary">{snapshot.title}</h3>
                    <span className="font-mono text-caption text-fg-muted">{snapshot.url}</span>
                  </div>
                  <div
                    className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg border border-border-default bg-surface-2 p-4 font-mono text-caption text-fg-primary"
                    dir="auto"
                  >
                    {snapshot.content_markdown}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center text-fg-muted">
                  <Globe className="mb-2 size-10 opacity-30" />
                  <p className="text-body">{t('proposeHelp')}</p>
                </div>
              )}

              {/* Screenshot Preview if available */}
              {screenshotPath && (
                <div className="mt-2 flex items-center gap-2 rounded-md border border-border-default bg-surface-2 p-2.5 text-caption">
                  <Camera className="size-4 text-accent" />
                  <span className="text-fg-muted">Latest Screenshot:</span>
                  <span className="font-mono text-fg-primary">{screenshotPath}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'dom',
      label: t('tabDomInspector'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-border-default bg-surface p-4">
            <h3 className="mb-3 flex items-center gap-2 text-h3 font-semibold">
              <Terminal className="size-4 text-accent" />
              {t('interactiveElements')} ({snapshot?.elements.length ?? 0})
            </h3>
            {snapshot && snapshot.elements.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-caption">
                  <thead>
                    <tr className="border-b border-border-default text-fg-muted">
                      <th className="py-2 px-3">{t('elemId')}</th>
                      <th className="py-2 px-3">{t('elemTag')}</th>
                      <th className="py-2 px-3">{t('elemText')}</th>
                      <th className="py-2 px-3">{t('elemSelector')}</th>
                      <th className="py-2 px-3">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.elements.map((elem) => (
                      <tr
                        key={elem.element_id}
                        className="border-b border-border-default/50 hover:bg-surface-2"
                      >
                        <td className="py-2 px-3 font-mono font-semibold">{elem.element_id}</td>
                        <td className="py-2 px-3">
                          <Badge variant="neutral">{elem.tag_name}</Badge>
                        </td>
                        <td className="py-2 px-3 max-w-44 truncate">{elem.text}</td>
                        <td className="py-2 px-3 font-mono text-fg-muted">{elem.selector}</td>
                        <td className="py-2 px-3">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              setTargetSelector(elem.selector);
                              if (elem.tag_name === 'a' && elem.attributes?.href) {
                                void handleNavigate(elem.attributes.href);
                              } else if (elem.tag_name === 'button') {
                                void handleClickElement(elem.selector);
                              }
                            }}
                          >
                            Use
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="py-4 text-center text-caption text-fg-muted">
                No interactive elements extracted.
              </p>
            )}
          </div>
        </div>
      ),
    },
    {
      id: 'crawler',
      label: t('tabDeepCrawler'),
      content: (
        <div className="flex flex-col gap-4">
          {/* Crawler Configuration Form */}
          <div className="flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-4">
            <h3 className="flex items-center gap-2 text-h3 font-semibold">
              <Compass className="size-4 text-accent" />
              {t('tabDeepCrawler')}
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-caption text-fg-muted">{t('crawlGoal')}</label>
                <input
                  type="text"
                  placeholder={t('crawlGoalPlaceholder')}
                  aria-label={t('crawlGoal')}
                  value={crawlGoal}
                  onChange={(e) => setCrawlGoal(e.target.value)}
                  className="h-8 w-full rounded-md border border-border-default bg-surface-2 px-2.5 text-caption outline-none"
                />
              </div>
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <label className="mb-1 block text-caption text-fg-muted">
                    {t('crawlDepth')}: {crawlDepth}
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="3"
                    aria-label={t('crawlDepth')}
                    value={crawlDepth}
                    onChange={(e) => setCrawlDepth(Number(e.target.value))}
                    className="w-full accent-accent"
                  />
                </div>
                <div className="flex-1">
                  <label className="mb-1 block text-caption text-fg-muted">
                    {t('crawlPages')}: {crawlMaxPages}
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="10"
                    aria-label={t('crawlPages')}
                    value={crawlMaxPages}
                    onChange={(e) => setCrawlMaxPages(Number(e.target.value))}
                    className="w-full accent-accent"
                  />
                </div>
              </div>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleDeepCrawl()}
              disabled={crawling || !urlInput.trim()}
              className="mt-1 self-start"
            >
              <Compass className="mr-1.5 size-4" />
              {crawling ? t('crawling') : t('startCrawl')}
            </Button>
          </div>

          {/* Crawl Results */}
          {crawlResult && (
            <div className="flex flex-col gap-4">
              {/* Synthesis Box */}
              <div className="rounded-lg border border-accent/40 bg-accent/5 p-4">
                <h4 className="mb-1 font-semibold text-caption text-accent">
                  {t('crawlSynthesis')}
                </h4>
                <p className="text-body text-fg-primary" dir="auto">
                  {crawlResult.synthesis}
                </p>
              </div>

              {/* Pages Extracted */}
              <div className="rounded-lg border border-border-default bg-surface p-4">
                <h4 className="mb-3 font-semibold text-caption text-fg-muted">
                  {t('pagesCrawled')} ({crawlResult.pages.length})
                </h4>
                <div className="flex flex-col gap-2">
                  {crawlResult.pages.map((p, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-md border border-border-default bg-surface-2 p-3"
                    >
                      <div className="flex flex-col gap-1">
                        <span className="font-medium text-caption text-fg-primary">{p.title}</span>
                        <span className="font-mono text-caption text-fg-muted">{p.url}</span>
                        <span className="text-caption text-fg-muted truncate max-w-lg">
                          {p.content_preview}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="neutral">Depth {p.depth}</Badge>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => void handleNavigate(p.url)}
                        >
                          <Eye className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'security',
      label: t('tabSecurityMonitor'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2 rounded-lg border border-success-fg/30 bg-success-fg/5 p-4">
              <div className="flex items-center gap-2">
                <ShieldCheck className="size-5 text-success-fg" />
                <h4 className="font-semibold text-body text-success-fg">{t('ssrfProtection')}</h4>
              </div>
              <p className="text-caption text-fg-muted">
                Strict RFC 1918 IPv4 & IPv6 loopback filtration active. Localhost, cloud metadata
                (169.254.169.254), and credential-smuggled URLs are rejected at the bridge boundary.
              </p>
            </div>

            <div className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-4">
              <div className="flex items-center gap-2">
                <ShieldAlert className="size-5 text-warning-fg" />
                <h4 className="font-semibold text-body text-fg-primary">SSRF Refusal Test</h4>
              </div>
              <p className="text-caption text-fg-muted">
                Test the security boundary by attempting to navigate to blocked local hosts.
              </p>
              <div className="mt-1 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleNavigate('http://127.0.0.1:8000/admin')}
                >
                  Test 127.0.0.1
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleNavigate('http://localhost:3000')}
                >
                  Test Localhost
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleNavigate('http://169.254.169.254/latest')}
                >
                  Test Metadata
                </Button>
              </div>
            </div>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* Top Header & Driver Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-default bg-surface p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-accent/10 text-accent">
            <Globe className="size-5" />
          </div>
          <div className="flex flex-col">
            <h2 className="text-h3 font-semibold text-fg-primary">{t('studioTitle')}</h2>
            <p className="text-caption text-fg-muted">{t('studioSubtitle')}</p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          <select
            value={backendType}
            onChange={(e) => void handleLaunch(e.target.value)}
            aria-label="Browser driver backend"
            className="h-8 rounded-md border border-border-default bg-surface-2 px-2 text-caption outline-none"
          >
            <option value="mock">Mock / Headless DOM</option>
            <option value="playwright">Playwright Chromium</option>
            <option value="cdp">Chrome DevTools (CDP)</option>
            <option value="stealth">Stealth Undetected</option>
          </select>
          <Button variant="secondary" size="sm" onClick={() => void handleReset()}>
            <RefreshCw className="mr-1 size-3.5" />
            {t('resetSession')}
          </Button>
          <Button variant="destructive" size="sm" onClick={() => void handleCloseSession()}>
            <XCircle className="mr-1 size-3.5" />
            {t('closeSession')}
          </Button>
        </div>
      </div>

      {/* URL Address Bar */}
      <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface p-2.5">
        <div className="flex items-center gap-1.5 pl-1 text-fg-muted">
          <Globe className="size-4" />
        </div>
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleNavigate();
          }}
          placeholder="https://example.com"
          aria-label={t('url')}
          className="h-8 flex-1 rounded-md border border-border-default bg-surface-2 px-3 font-mono text-body outline-none"
          dir="ltr"
        />
        <Button
          variant="primary"
          size="sm"
          onClick={() => void handleNavigate()}
          disabled={loading || !urlInput.trim()}
        >
          {loading ? t('navigating') : t('navigateAction')}
        </Button>
      </div>

      {/* Alert Banner */}
      {alertMsg && (
        <div
          role="alert"
          className={`flex items-center justify-between rounded-lg border p-3 text-caption ${
            alertType === 'error'
              ? 'border-danger-fg/40 bg-danger-fg/10 text-danger-fg'
              : alertType === 'success'
                ? 'border-success-fg/40 bg-success-fg/10 text-success-fg'
                : 'border-accent/40 bg-accent/10 text-accent'
          }`}
        >
          <span>{alertMsg}</span>
          <button onClick={() => setAlertMsg(null)} className="ml-2 font-bold opacity-70">
            ✕
          </button>
        </div>
      )}

      {/* Tabs */}
      <Tabs
        items={tabs}
        value={activeTab}
        onValueChange={setActiveTab}
        label="Browser Studio Navigation"
      />
    </div>
  );
}
