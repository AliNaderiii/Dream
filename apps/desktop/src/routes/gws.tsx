import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Textarea } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import { gwsDisconnect, gwsOauthBegin, gwsOauthComplete, gwsStatus } from '@/lib/bridge/gws';
import { useTranslation } from '@/lib/i18n';

export default function GoogleRoute() {
  const { t } = useTranslation('gws');
  const { client } = useBridge();
  const [connected, setConnected] = useState(false);
  const [authUrl, setAuthUrl] = useState('');
  const [state, setState] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void gwsStatus(client)
      .then((shot) => {
        if (!cancelled) setConnected(shot.connected);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const onBegin = async () => {
    setError(null);
    try {
      const started = await gwsOauthBegin(client);
      setAuthUrl(started.authorization_url);
      setState(started.state);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onComplete = async () => {
    setError(null);
    try {
      const done = await gwsOauthComplete(client, state, code);
      setConnected(done.connected);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onDisconnect = async () => {
    setError(null);
    try {
      await gwsDisconnect(client);
      setConnected(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="gws-title">
      <header>
        <h1 id="gws-title" className="text-h2 font-semibold">
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
          <h2 className="text-h3 font-semibold">{t('statusTitle')}</h2>
          <CardDescription>{t('statusHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Badge variant={connected ? 'success' : 'warning'}>
            {connected ? t('connected') : t('disconnected')}
          </Badge>
          <p className="text-caption text-fg-muted">{t('readonlyNote')}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('connectTitle')}</h2>
          <CardDescription>{t('connectHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Button onClick={() => void onBegin()}>{t('begin')}</Button>
          {authUrl && (
            <p className="ltr-island break-all text-caption text-fg-muted" title={authUrl}>
              {authUrl}
            </p>
          )}
          <Textarea
            label={t('code')}
            value={code}
            rows={3}
            onChange={(event) => setCode(event.target.value)}
          />
          <Button onClick={() => void onComplete()} disabled={!state.trim() || !code.trim()}>
            {t('complete')}
          </Button>
          <Button onClick={() => void onDisconnect()} disabled={!connected}>
            {t('disconnect')}
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
