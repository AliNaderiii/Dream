import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input, Textarea } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import { liveloopArmDraft, liveloopRoleTurn, liveloopRouteSnapshot } from '@/lib/bridge/liveloop';
import { useTranslation } from '@/lib/i18n';
import { useProviderStore } from '@/stores/use-provider-store';

export default function LiveRoute() {
  const { t } = useTranslation('live');
  const { client } = useBridge();
  const bar = useProviderStore((s) => s.providers.find((p) => p.id === s.activeProviderId));
  const [note, setNote] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [spaceId, setSpaceId] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [draftId, setDraftId] = useState('');
  const [armed, setArmed] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void liveloopRouteSnapshot(client, bar?.name ?? 'echo', 'Earth Runtime', 'qwen3.6-35b')
      .then((shot) => {
        if (cancelled) return;
        setNote(shot.note_en);
        setMismatch(shot.mismatch);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client, bar?.name]);

  const onAsk = async () => {
    setError(null);
    try {
      const result = await liveloopRoleTurn(client, spaceId, 'secretary', question, false);
      setAnswer(result.answer);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onArm = async () => {
    setError(null);
    try {
      const result = await liveloopArmDraft(client, draftId, true);
      setArmed(result.schedule.schedule_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="live-title">
      <header>
        <h1 id="live-title" className="text-h2 font-semibold">
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
          <h2 className="text-h3 font-semibold">{t('honestyTitle')}</h2>
          <CardDescription>{t('honestyHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Badge variant={mismatch ? 'warning' : 'success'}>
            {mismatch ? t('honestyHint') : t('honestyOk')}
          </Badge>
          {note && <p className="text-caption text-fg-muted">{note}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('roleTitle')}</h2>
          <CardDescription>{t('roleHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Input
            label={t('spaceId')}
            value={spaceId}
            onChange={(event) => setSpaceId(event.target.value)}
          />
          <Textarea
            label={t('question')}
            value={question}
            rows={3}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <Button onClick={() => void onAsk()} disabled={!spaceId.trim() || !question.trim()}>
            {t('ask')}
          </Button>
          {answer && (
            <p aria-live="polite" className="whitespace-pre-wrap text-body">
              {answer}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('armTitle')}</h2>
          <CardDescription>{t('armHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Input
            label={t('draftId')}
            value={draftId}
            onChange={(event) => setDraftId(event.target.value)}
          />
          <Button onClick={() => void onArm()} disabled={!draftId.trim()}>
            {t('arm')}
          </Button>
          {armed && (
            <p aria-live="polite" className="text-caption">
              {t('armedAs')} {armed}
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
