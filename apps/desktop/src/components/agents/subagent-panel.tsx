import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';
import type { LiveSubagent } from '@/lib/bridge/workspace';

export function SubagentPanel({ agents }: { agents: LiveSubagent[] }) {
  const { t } = useTranslation('workspace');
  return (
    <section aria-label={t('agents.subagents')} className="flex flex-col gap-2">
      <h2 className="text-h3 font-semibold">{t('agents.subagents')}</h2>
      {agents.length === 0 ? (
        <p className="text-caption text-fg-muted">{t('agents.noSubagents')}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {agents.map((agent) => (
            <li
              key={agent.agent_id}
              className="rounded-lg border border-border-default bg-surface p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold">{agent.name}</p>
                <Badge variant={agent.status === 'cancelled' ? 'warning' : 'accent'}>
                  {agent.status}
                </Badge>
              </div>
              <p className="text-caption text-fg-muted">{agent.latest_action}</p>
              <progress
                className="mt-2 h-2 w-full"
                max={1}
                value={agent.progress}
                aria-label={t('agents.progress')}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
