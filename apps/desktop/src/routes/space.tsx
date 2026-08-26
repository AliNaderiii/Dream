import { Check, Plus, Send, ShieldAlert, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input, Textarea } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  spaceApproveDraft,
  spaceAsk,
  spaceAttachFolder,
  spaceCreate,
  spaceDenyDraft,
  spaceList,
  spaceProposeDraft,
  spaceSetInstruction,
  type SpaceDraft,
  type SpaceRecord,
} from '@/lib/bridge/space';
import { useTranslation } from '@/lib/i18n';

export default function SpaceRoute() {
  const { t } = useTranslation('space');
  const { client } = useBridge();
  const [spaces, setSpaces] = useState<SpaceRecord[]>([]);
  const [active, setActive] = useState<SpaceRecord | null>(null);
  const [name, setName] = useState('Studio');
  const [folder, setFolder] = useState('');
  const [instruction, setInstruction] = useState(
    'Outcome:\nSources:\nConstraints:\nDeliverable:\nReview point:',
  );
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [rule, setRule] = useState('every day at 9 AM');
  const [drafts, setDrafts] = useState<SpaceDraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [roleId, setRoleId] = useState('secretary');

  const refresh = async (spaceId?: string) => {
    const listed = await spaceList(client);
    const rows = listed.spaces ?? [];
    setSpaces(rows);
    const next = rows.find((row) => row.space_id === spaceId) ?? rows[0] ?? null;
    setActive(next);
    if (next?.instruction?.text) setInstruction(next.instruction.text);
  };

  useEffect(() => {
    let cancelled = false;
    void spaceList(client)
      .then((listed) => {
        if (cancelled) return;
        const rows = listed.spaces ?? [];
        setSpaces(rows);
        const next = rows[0] ?? null;
        setActive(next);
        if (next?.instruction?.text) setInstruction(next.instruction.text);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const onCreate = async () => {
    setError(null);
    try {
      const created = await spaceCreate(client, name);
      await refresh(created.space_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onAttach = async () => {
    if (!active) return;
    setError(null);
    try {
      await spaceAttachFolder(client, active.space_id, folder);
      await refresh(active.space_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onSaveInstruction = async () => {
    if (!active) return;
    setError(null);
    try {
      await spaceSetInstruction(client, active.space_id, instruction);
      await refresh(active.space_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onAsk = async () => {
    if (!active || !question.trim()) return;
    setError(null);
    try {
      const result = await spaceAsk(client, active.space_id, roleId, question.trim());
      setAnswer(result.answer);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onDraft = async () => {
    if (!active) return;
    setError(null);
    try {
      const draft = await spaceProposeDraft(client, active.space_id, rule);
      setDrafts((current) => [draft, ...current]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onDecide = async (draftId: string, allow: boolean) => {
    setError(null);
    try {
      const updated = allow
        ? await spaceApproveDraft(client, draftId)
        : await spaceDenyDraft(client, draftId);
      setDrafts((current) => current.map((row) => (row.draft_id === draftId ? updated : row)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="space-title">
      <header>
        <h1 id="space-title" className="text-h2 font-semibold">
          {t('title')}
        </h1>
        <p className="text-body text-fg-muted">{t('subtitle')}</p>
      </header>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('createTitle')}</h2>
          <CardDescription>{t('createHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_auto]">
          <Input label={t('nameLabel')} value={name} onChange={(event) => setName(event.target.value)} />
          <Button className="self-end" onClick={() => void onCreate()}>
            <Plus aria-hidden />
            {t('create')}
          </Button>
        </CardContent>
      </Card>

      {error && (
        <p role="alert" className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg">
          {error}
        </p>
      )}

      <section className="flex flex-wrap gap-2" aria-label={t('spaces')}>
        {spaces.map((row) => (
          <Button
            key={row.space_id}
            variant={row.space_id === active?.space_id ? 'primary' : 'secondary'}
            onClick={() => {
              setActive(row);
              if (row.instruction?.text) setInstruction(row.instruction.text);
            }}
          >
            {row.name}
          </Button>
        ))}
      </section>

      {active && (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold">{t('folderTitle')}</h2>
              <CardDescription>{t('folderHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {active.imported_in_place && (
                <Badge variant="success">{t('inPlace')}</Badge>
              )}
              <Input
                label={t('folderLabel')}
                value={folder}
                onChange={(event) => setFolder(event.target.value)}
              />
              <Button onClick={() => void onAttach()} disabled={!folder.trim()}>
                {t('attach')}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold">{t('handoffTitle')}</h2>
              <CardDescription>{t('handoffHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Textarea
                label={t('instructionLabel')}
                value={instruction}
                rows={8}
                onChange={(event) => setInstruction(event.target.value)}
              />
              <Button onClick={() => void onSaveInstruction()}>{t('saveInstruction')}</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold">{t('askTitle')}</h2>
              <CardDescription>{t('askHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-caption">
                {t('roleLabel')}
                <select
                  className="rounded-md border border-border-default bg-surface px-3 py-2"
                  value={roleId}
                  onChange={(event) => setRoleId(event.target.value)}
                >
                  <option value="secretary">{t('roleSecretary')}</option>
                  <option value="research">{t('roleResearch')}</option>
                  <option value="data">{t('roleData')}</option>
                  <option value="desk">{t('roleDesk')}</option>
                  <option value="security">{t('roleSecurity')}</option>
                </select>
              </label>
              <Textarea
                label={t('questionLabel')}
                value={question}
                rows={3}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <Button onClick={() => void onAsk()} disabled={!question.trim()}>
                <Send aria-hidden />
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
              <h2 className="text-h3 font-semibold">{t('draftTitle')}</h2>
              <CardDescription>{t('draftHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Input label={t('ruleLabel')} value={rule} onChange={(event) => setRule(event.target.value)} />
              <Button onClick={() => void onDraft()}>{t('propose')}</Button>
              <ul className="flex flex-col gap-2" aria-label={t('drafts')}>
                {drafts.map((draft) => (
                  <li
                    key={draft.draft_id}
                    className="rounded-lg border border-border-default p-3 text-caption"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={draft.status === 'APPROVED' ? 'success' : 'neutral'}>
                        {draft.status}
                      </Badge>
                      {draft.dangerous && (
                        <Badge variant="warning">
                          <ShieldAlert className="size-3" aria-hidden />
                          {t('dangerous')}
                        </Badge>
                      )}
                    </div>
                    <p className="mt-2">{draft.rule}</p>
                    {draft.status === 'APPROVAL_PENDING' && (
                      <div className="mt-2 flex gap-2">
                        <Button size="sm" onClick={() => void onDecide(draft.draft_id, true)}>
                          <Check aria-hidden />
                          {t('approve')}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void onDecide(draft.draft_id, false)}
                        >
                          <X aria-hidden />
                          {t('deny')}
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}
    </main>
  );
}
