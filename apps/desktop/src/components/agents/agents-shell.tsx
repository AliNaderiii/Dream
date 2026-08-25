import { useEffect, useState } from 'react';

import { ChatRefs } from '@/components/agents/chat-refs';
import { ModeIndicator } from '@/components/agents/mode-indicator';
import { SubagentPanel } from '@/components/agents/subagent-panel';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input, Textarea } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  workspaceContinue,
  workspaceGoal,
  workspacePlan,
  workspaceStatus,
  workspaceStop,
  workspaceSubagentsLive,
  type AgentGoal,
  type AgentPlan,
  type LiveSubagent,
} from '@/lib/bridge/workspace';
import { useTranslation } from '@/lib/i18n';

export function AgentsShell() {
  const { t } = useTranslation('workspace');
  const { client } = useBridge();
  const [mode, setMode] = useState<'chat' | 'plan' | 'goal'>('plan');
  const [prompt, setPrompt] = useState('Summarise the sales table');
  const [objective, setObjective] = useState('Keep the sales table honest');
  const [criteriaText, setCriteriaText] = useState(
    'CSV preview has a chart\nmust fetch live market prices',
  );
  const [plan, setPlan] = useState<AgentPlan | null>(null);
  const [goal, setGoal] = useState<AgentGoal | null>(null);
  const [agents, setAgents] = useState<LiveSubagent[]>([]);
  const [running, setRunning] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [live, setLive] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    const [status, liveAgents] = await Promise.all([
      workspaceStatus(client),
      workspaceSubagentsLive(client),
    ]);
    setRunning(status.running);
    setCancelled(status.cancelled);
    setLive(status.live);
    setAgents(liveAgents.subagents);
  };

  useEffect(() => {
    let cancelled = false;
    void Promise.all([workspaceStatus(client), workspaceSubagentsLive(client)]).then(
      ([status, liveAgents]) => {
        if (cancelled) return;
        setRunning(status.running);
        setCancelled(status.cancelled);
        setLive(status.live);
        setAgents(liveAgents.subagents);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client]);

  const onPlan = async () => {
    setError(null);
    setMode('plan');
    try {
      setPlan(await workspacePlan(client, prompt));
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onContinue = async () => {
    if (!plan) return;
    try {
      setPlan(await workspaceContinue(client, plan.plan_id));
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onGoal = async () => {
    setError(null);
    setMode('goal');
    const criteria = criteriaText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    try {
      setGoal(await workspaceGoal(client, objective, criteria));
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onStop = async () => {
    const result = await workspaceStop(client);
    setCancelled(true);
    setRunning(false);
    setLive(result.live);
    await refresh();
  };

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="agents-title">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 id="agents-title" className="text-h2 font-semibold">
            {t('agents.title')}
          </h1>
          <p className="text-body text-fg-muted">{t('agents.subtitle')}</p>
        </div>
        <ModeIndicator mode={mode} live={live} running={running} cancelled={cancelled} />
      </header>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(260px,0.4fr)]">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold">{t('agents.planTitle')}</h2>
              <CardDescription>{t('agents.planHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Textarea
                label={t('agents.prompt')}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={3}
              />
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void onPlan()}>{t('agents.plan')}</Button>
                <Button variant="secondary" onClick={() => void onContinue()} disabled={!plan}>
                  {t('agents.continue')}
                </Button>
                <Button variant="danger-outline" onClick={() => void onStop()}>
                  {t('agents.stop')}
                </Button>
              </div>
              {plan && (
                <ol className="list-decimal ps-5 text-caption">
                  {plan.steps.map((step) => (
                    <li key={step.index}>
                      {step.title} — {step.status}
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold">{t('agents.goalTitle')}</h2>
              <CardDescription>{t('agents.goalHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Input
                label={t('agents.objective')}
                value={objective}
                onChange={(event) => setObjective(event.target.value)}
              />
              <Textarea
                label={t('agents.criteria')}
                value={criteriaText}
                onChange={(event) => setCriteriaText(event.target.value)}
                rows={4}
              />
              <Button onClick={() => void onGoal()}>{t('agents.startGoal')}</Button>
              {goal && (
                <p aria-live="polite" className="text-body">
                  {goal.report}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <ChatRefs />
            </CardContent>
          </Card>
        </div>
        <Card>
          <CardContent>
            <SubagentPanel agents={agents} />
          </CardContent>
        </Card>
      </div>
      {error && (
        <p role="alert" className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg">
          {error}
        </p>
      )}
    </main>
  );
}
