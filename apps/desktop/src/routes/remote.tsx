import { Play, Square } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { useBridge } from '@/lib/bridge/hooks';
import {
  remotegwIssueToken,
  remotegwPreview,
  remotegwStart,
  remotegwStatus,
  remotegwStop,
} from '@/lib/bridge/remotegw';
import { useTranslation } from '@/lib/i18n';

export default function RemoteRoute() {
  const { t } = useTranslation('remote');
  const { client } = useBridge();
  const [url, setUrl] = useState('http://127.0.0.1:8765/');
  const [running, setRunning] = useState(false);
  const [leaves, setLeaves] = useState(false);
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([remotegwStatus(client), remotegwPreview(client)])
      .then(([status, preview]) => {
        if (cancelled) return;
        setRunning(status.running);
        setLeaves(status.leaves_machine);
        setUrl(preview.url);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const onStart = async () => {
    setError(null);
    try {
      const started = await remotegwStart(client);
      setRunning(true);
      setLeaves(Boolean(started.leaves_machine));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onStop = async () => {
    setError(null);
    try {
      await remotegwStop(client);
      setRunning(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onIssue = async () => {
    setError(null);
    try {
      const issued = await remotegwIssueToken(client, 'read', 'Phone');
      setToken(issued.token);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="remote-title">
      <header>
        <h1 id="remote-title" className="text-h2 font-semibold">
          {t('title')}
        </h1>
        <p className="text-body text-fg-muted">{t('subtitle')}</p>
      </header>

      {error && (
        <p role="alert" className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('bindTitle')}</h2>
          <CardDescription>{t('bindHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="font-mono text-body">{url}</p>
          <div className="flex flex-wrap gap-2">
            <Badge variant={running ? 'success' : 'neutral'}>
              {running ? t('running') : t('stopped')}
            </Badge>
            <Badge variant={leaves ? 'warning' : 'success'}>
              {leaves ? t('leavesYes') : t('leavesNo')}
            </Badge>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => void onStart()}>
              <Play aria-hidden />
              {t('start')}
            </Button>
            <Button variant="secondary" onClick={() => void onStop()}>
              <Square aria-hidden />
              {t('stop')}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('qrTitle')}</h2>
          <CardDescription>{t('qrHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <svg
            viewBox="0 0 80 80"
            className="size-40 border border-border-default"
            role="img"
            aria-label={t('qrLabel')}
          >
            <rect width="80" height="80" fill="white" />
            <rect x="8" y="8" width="20" height="20" fill="black" />
            <rect x="52" y="8" width="20" height="20" fill="black" />
            <rect x="8" y="52" width="20" height="20" fill="black" />
            <text x="40" y="44" textAnchor="middle" fontSize="6" fill="black">
              URL
            </text>
          </svg>
          <p className="text-caption text-fg-muted">{t('qrHint')}</p>
          <Button onClick={() => void onIssue()}>{t('issue')}</Button>
          {token && (
            <p className="break-all font-mono text-caption" aria-live="polite">
              {t('pasteOnce')}: {token}
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
