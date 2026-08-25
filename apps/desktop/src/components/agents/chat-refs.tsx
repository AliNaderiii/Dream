import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  workspaceCommands,
  workspaceRefsParse,
  workspaceShellExecute,
  workspaceShellPropose,
} from '@/lib/bridge/workspace';
import { useTranslation } from '@/lib/i18n';

export function ChatRefs() {
  const { t } = useTranslation('workspace');
  const { client } = useBridge();
  const [draft, setDraft] = useState('@sales.csv #sess_demo /plan !ls');
  const [parsed, setParsed] = useState<{
    files: string[];
    conversations: string[];
    commands: string[];
    shell: string[];
  } | null>(null);
  const [palette, setPalette] = useState<Array<{ name: string; title: string; summary: string }>>(
    [],
  );
  const [query, setQuery] = useState('');
  const [shell, setShell] = useState<{
    approval_id: string;
    risk: string;
    executed: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hint = useMemo(() => t('refs.hint'), [t]);

  const onParse = async () => {
    setError(null);
    try {
      setParsed(await workspaceRefsParse(client, draft));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onPalette = async () => {
    setPalette((await workspaceCommands(client, query)).commands);
  };

  const onShell = async () => {
    const command = parsed?.shell[0] ?? draft.replace(/^.*!/, '').trim();
    if (!command) return;
    try {
      const proposal = await workspaceShellPropose(client, command);
      setShell(proposal);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onApprove = async () => {
    if (!shell) return;
    if (shell.risk === 'dangerous') {
      setError('dangerous shell commands are refused');
      setShell({ ...shell, executed: false });
      return;
    }
    try {
      const result = await workspaceShellExecute(client, shell.approval_id, true);
      setShell({ ...shell, executed: result.executed });
      if (!result.executed) {
        setError('dangerous shell commands are refused');
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <section className="flex flex-col gap-3" aria-label={t('refs.title')}>
      <h2 className="text-h3 font-semibold">{t('refs.title')}</h2>
      <p className="text-caption text-fg-muted">{hint}</p>
      <Textarea
        label={t('refs.draft')}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        rows={3}
      />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void onParse()}>{t('refs.parse')}</Button>
        <Button variant="secondary" onClick={() => void onShell()}>
          {t('refs.proposeShell')}
        </Button>
      </div>
      {parsed && (
        <ul className="text-caption">
          <li>
            {t('refs.files')}: {parsed.files.join(', ') || '—'}
          </li>
          <li>
            {t('refs.conversations')}: {parsed.conversations.join(', ') || '—'}
          </li>
          <li>
            {t('refs.commands')}: {parsed.commands.join(', ') || '—'}
          </li>
          <li>
            {t('refs.shell')}: {parsed.shell.join(', ') || '—'}
          </li>
        </ul>
      )}
      <Input
        label={t('refs.palette')}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') void onPalette();
        }}
      />
      <Button variant="secondary" onClick={() => void onPalette()}>
        {t('refs.searchCommands')}
      </Button>
      {palette.length > 0 && (
        <ul className="flex flex-col gap-1">
          {palette.map((item) => (
            <li key={item.name} className="rounded-md bg-surface-2 px-3 py-2 text-caption">
              <strong>{item.title}</strong> — {item.summary}
            </li>
          ))}
        </ul>
      )}
      {shell && (
        <div className="rounded-lg border border-border-default p-3">
          <p className="text-caption">
            {t('refs.risk')}: {shell.risk}
          </p>
          <Button className="mt-2" onClick={() => void onApprove()} disabled={shell.executed}>
            {t('refs.approveShell')}
          </Button>
          {shell.executed && <p className="mt-2 text-caption">{t('refs.executed')}</p>}
        </div>
      )}
      {error && (
        <p role="alert" className="text-caption text-danger-fg">
          {error}
        </p>
      )}
    </section>
  );
}
