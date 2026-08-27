import { useEffect, useState } from 'react';

import { BotAvatar } from '@/components/bots/bot-avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Textarea } from '@/components/ui/input';
import { botsList, type BotRecord } from '@/lib/bridge/bots';
import { groupsStart, type GroupRun } from '@/lib/bridge/groups';
import { useBridge } from '@/lib/bridge/hooks';
import { spaceList, type SpaceRecord } from '@/lib/bridge/space';
import { useTranslation } from '@/lib/i18n';

export default function GroupsRoute() {
  const { t } = useTranslation('groups');
  const { client } = useBridge();
  const [spaces, setSpaces] = useState<SpaceRecord[]>([]);
  const [active, setActive] = useState<SpaceRecord | null>(null);
  const [bots, setBots] = useState<BotRecord[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<GroupRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const spaceId = active?.space_id;

  useEffect(() => {
    let cancelled = false;
    void spaceList(client)
      .then((listed) => {
        if (cancelled) return;
        const rows = listed.spaces ?? [];
        setSpaces(rows);
        setActive(rows[0] ?? null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    if (!spaceId) {
      return;
    }
    void botsList(client, spaceId)
      .then((roster) => {
        if (cancelled) return;
        setBots(roster.bots ?? []);
        setSelected([]);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client, spaceId]);

  const onToggle = (botId: string) => {
    setSelected((current) => {
      if (current.includes(botId)) return current.filter((id) => id !== botId);
      if (current.length >= 6) return current;
      return [...current, botId];
    });
  };

  const onRun = async () => {
    if (!spaceId) return;
    setError(null);
    try {
      const run = await groupsStart(client, spaceId, selected, question);
      setResult(run);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const canRun =
    Boolean(spaceId) && selected.length >= 2 && selected.length <= 6 && Boolean(question.trim());

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="groups-title">
      <header>
        <h1 id="groups-title" className="text-h2 font-semibold">
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
          <h2 className="text-h3 font-semibold">{t('space')}</h2>
          <CardDescription>{t('spaceHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {spaces.length === 0 && <p className="text-caption text-fg-muted">{t('empty')}</p>}
          <ul className="flex flex-wrap gap-2">
            {spaces.map((space) => (
              <li key={space.space_id}>
                <Button
                  variant={space.space_id === spaceId ? 'primary' : 'secondary'}
                  onClick={() => setActive(space)}
                >
                  {space.name}
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('bots')}</h2>
          <CardDescription>{t('botsHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {bots.length === 0 && <p className="text-caption text-fg-muted">{t('emptyBots')}</p>}
          <ul className="flex flex-col gap-2">
            {bots.map((bot) => (
              <li key={bot.bot_id}>
                <label className="flex items-center gap-2 text-caption">
                  <input
                    type="checkbox"
                    checked={selected.includes(bot.bot_id)}
                    onChange={() => onToggle(bot.bot_id)}
                  />
                  <BotAvatar shape={bot.avatar.shape} hue={bot.avatar.hue} />
                  <span>
                    {bot.name} · {bot.role_id} · {bot.model}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <Textarea
            label={t('question')}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <Button onClick={() => void onRun()} disabled={!canRun}>
            {t('run')}
          </Button>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <h2 className="text-h3 font-semibold">{t('transcript')}</h2>
            <CardDescription>{t('cap')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant="success">{t('yolo')}</Badge>
              <Badge variant="neutral">
                {t('rounds')}: {result.rounds}/{result.cap}
              </Badge>
              <Badge variant="warning">
                {t('stopped')}: {result.stopped}
              </Badge>
            </div>
            <ol className="flex flex-col gap-2">
              {result.transcript.map((turn) => (
                <li
                  key={`${turn.round}-${turn.bot_id}`}
                  className="rounded-lg border border-border-default p-3 text-caption"
                  dir="auto"
                >
                  <p className="font-semibold">
                    {t('round')} {turn.round} · {turn.name}
                  </p>
                  <p className="whitespace-pre-wrap text-fg-muted">{turn.answer}</p>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
