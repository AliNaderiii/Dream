import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  browseApprove,
  browseDeny,
  browseFollow,
  browseList,
  browsePropose,
  type BrowseDraft,
} from '@/lib/bridge/browse';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';

export default function BrowseRoute() {
  const { t } = useTranslation('browse');
  const { client } = useBridge();
  const [url, setUrl] = useState('https://example.com');
  const [drafts, setDrafts] = useState<BrowseDraft[]>([]);
  const [active, setActive] = useState<BrowseDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () =>
    browseList(client).then((listed) => {
      setDrafts(listed.drafts ?? []);
    });

  useEffect(() => {
    let cancelled = false;
    void browseList(client)
      .then((listed) => {
        if (!cancelled) setDrafts(listed.drafts ?? []);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const onPropose = async () => {
    setError(null);
    try {
      const draft = await browsePropose(client, url);
      setActive(draft);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onApprove = async (draftId: string) => {
    setError(null);
    try {
      const draft = await browseApprove(client, draftId);
      setActive(draft);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onDeny = async (draftId: string) => {
    setError(null);
    try {
      await browseDeny(client, draftId);
      setActive(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onFollow = async (draftId: string, href: string) => {
    setError(null);
    try {
      const draft = await browseFollow(client, draftId, href);
      setActive(draft);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="browse-title">
      <header>
        <h1 id="browse-title" className="text-h2 font-semibold">
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
          <h2 className="text-h3 font-semibold">{t('proposeTitle')}</h2>
          <CardDescription>{t('proposeHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="success">{t('yolo')}</Badge>
            <Badge variant="neutral">{t('chrome')}</Badge>
            <Badge variant="warning">{t('once')}</Badge>
          </div>
          <Input label={t('url')} value={url} onChange={(event) => setUrl(event.target.value)} />
          <Button onClick={() => void onPropose()} disabled={!url.trim()}>
            {t('propose')}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('queue')}</h2>
          <CardDescription>{t('queueHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {drafts.length === 0 && <p className="text-caption text-fg-muted">{t('empty')}</p>}
          <ul className="flex flex-col gap-2">
            {drafts.map((draft) => (
              <li
                key={draft.draft_id}
                className="flex flex-col gap-2 rounded-lg border border-border-default p-3"
              >
                <p className="break-all font-mono text-caption" dir="ltr">
                  {draft.url}
                </p>
                <p className="text-caption text-fg-muted">{draft.status}</p>
                {draft.status === 'APPROVAL_PENDING' && (
                  <div className="flex gap-2">
                    <Button onClick={() => void onApprove(draft.draft_id)}>{t('approve')}</Button>
                    <Button variant="secondary" onClick={() => void onDeny(draft.draft_id)}>
                      {t('deny')}
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {active && active.excerpt && (
        <Card>
          <CardHeader>
            <h2 className="text-h3 font-semibold">{active.title}</h2>
            <CardDescription>{t('excerptHelp')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="whitespace-pre-wrap text-caption" dir="auto">
              {active.excerpt}
            </p>
            {active.links.length > 0 && (
              <ul className="flex flex-col gap-2" aria-label={t('links')}>
                {active.links.map((link) => (
                  <li key={link.url}>
                    <Button
                      variant="secondary"
                      onClick={() => void onFollow(active.draft_id, link.url)}
                    >
                      {t('follow')}: {link.host}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
    </main>
  );
}
