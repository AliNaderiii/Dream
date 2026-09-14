import { AlertTriangle, CheckCircle2, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  dialecticDebateTurn,
  dialecticDetectTensions,
  dialecticReconcileTension,
  dialecticReset,
  dialecticSnapshot,
  type BeliefNode,
  type DialecticDebateResult,
  type DialecticMemorySnapshot,
  type DialecticTension,
} from '@/lib/bridge/dialectic';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';

export function DialecticStudio() {
  const { t } = useTranslation('research');
  const { client } = useBridge();

  const [topic, setTopic] = useState('');
  const [domain, setDomain] = useState('architecture');
  const [isDebating, setIsDebating] = useState(false);
  const [isReconciling, setIsReconciling] = useState(false);
  const [lastDebate, setLastDebate] = useState<DialecticDebateResult | null>(null);
  const [snapshot, setSnapshot] = useState<DialecticMemorySnapshot | null>(null);
  const [tensions, setTensions] = useState<DialecticTension[]>([]);
  const [nuancedInputs, setNuancedInputs] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const refreshData = useCallback(async () => {
    try {
      const snap = await dialecticSnapshot(client);
      setSnapshot(snap);
      const tens = await dialecticDetectTensions(client);
      setTensions(tens.tensions);
    } catch {
      // Echo mode / fallback
    }
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    void dialecticSnapshot(client)
      .then((snap) => {
        if (!cancelled) setSnapshot(snap);
      })
      .catch(() => {});

    void dialecticDetectTensions(client)
      .then((tens) => {
        if (!cancelled) setTensions(tens.tensions);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleRunDebate = async () => {
    if (!topic.trim()) return;
    setIsDebating(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await dialecticDebateTurn(client, topic.trim(), domain.trim() || 'general');
      setLastDebate(res);
      await refreshData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsDebating(false);
    }
  };

  const handleReconcile = async (tensionId: string) => {
    const nuance = nuancedInputs[tensionId];
    if (!nuance || !nuance.trim()) return;

    setIsReconciling(true);
    setError(null);
    try {
      await dialecticReconcileTension(client, tensionId, nuance.trim());
      setSuccessMessage(t('dialectic.reconciledSuccess'));
      setNuancedInputs((prev) => {
        const next = { ...prev };
        delete next[tensionId];
        return next;
      });
      await refreshData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsReconciling(false);
    }
  };

  const handleReset = async () => {
    setError(null);
    try {
      await dialecticReset(client);
      setLastDebate(null);
      await refreshData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex flex-col gap-6" data-testid="dialectic-studio">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-accent-fg" />
              <h2 className="text-h3 font-semibold">{t('dialectic.title')}</h2>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleReset()}
              aria-label={t('dialectic.reset')}
            >
              <Trash2 className="mr-1 h-4 w-4" />
              {t('dialectic.reset')}
            </Button>
          </div>
          <CardDescription>{t('dialectic.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className="md:col-span-2">
              <Input
                label={t('dialectic.topic')}
                placeholder={t('dialectic.topicPlaceholder')}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </div>
            <div>
              <Input
                label={t('dialectic.domain')}
                placeholder={t('dialectic.domainPlaceholder')}
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button
              variant="primary"
              disabled={isDebating || !topic.trim()}
              onClick={() => void handleRunDebate()}
            >
              {isDebating ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  {t('dialectic.debating')}
                </>
              ) : (
                t('dialectic.startDebate')
              )}
            </Button>
          </div>

          {error && (
            <p
              role="alert"
              className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg"
            >
              {error}
            </p>
          )}

          {successMessage && (
            <div className="flex items-center gap-2 rounded-lg border border-success-fg bg-success/10 p-3 text-body text-success-fg">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 3-Agent Live Debate Stage */}
      {lastDebate && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Thesis */}
          <Card className="border-emerald-500/30 bg-emerald-500/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <h3 className="text-h4 font-semibold text-emerald-400">{t('dialectic.thesis')}</h3>
                <Badge variant="success">
                  Conf: {(lastDebate.thesis.confidence * 100).toFixed(0)}%
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-body text-fg">{lastDebate.thesis.statement}</p>
              <div className="text-caption text-fg-muted">
                Domain: <span className="font-mono">{lastDebate.thesis.domain}</span>
              </div>
            </CardContent>
          </Card>

          {/* Antithesis */}
          <Card className="border-amber-500/30 bg-amber-500/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <h3 className="text-h4 font-semibold text-amber-400">
                  {t('dialectic.antithesis')}
                </h3>
                <Badge variant="warning">
                  Conf: {(lastDebate.antithesis.confidence * 100).toFixed(0)}%
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-body text-fg">{lastDebate.antithesis.statement}</p>
              <div className="text-caption text-fg-muted">
                Domain: <span className="font-mono">{lastDebate.antithesis.domain}</span>
              </div>
            </CardContent>
          </Card>

          {/* Synthesis */}
          <Card className="border-indigo-500/30 bg-indigo-500/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <h3 className="text-h4 font-semibold text-indigo-400">
                  {t('dialectic.synthesis')}
                </h3>
                <Badge variant="info">
                  Conf: {(lastDebate.synthesis.confidence * 100).toFixed(0)}%
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-body text-fg">{lastDebate.synthesis.statement}</p>
              <div className="text-caption text-fg-muted">
                Domain: <span className="font-mono">{lastDebate.synthesis.domain}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tensions & Contradictions Panel */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
            <h2 className="text-h3 font-semibold">{t('dialectic.tensions')}</h2>
          </div>
          <CardDescription>
            {snapshot
              ? t('dialectic.tensionsCount', { count: tensions.filter((t) => !t.resolved).length })
              : ''}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tensions.filter((t) => !t.resolved).length === 0 ? (
            <p className="text-body text-fg-muted">{t('dialectic.noTensions')}</p>
          ) : (
            <div className="flex flex-col gap-4">
              {tensions
                .filter((ten) => !ten.resolved)
                .map((ten) => (
                  <div
                    key={ten.tension_id}
                    className="flex flex-col gap-3 rounded-lg border border-amber-500/30 bg-surface-elevated p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium text-fg">{ten.description}</p>
                      <Badge variant="warning">{ten.tension_id}</Badge>
                    </div>

                    <div className="flex flex-col gap-2 sm:flex-row">
                      <div className="flex-1">
                        <Input
                          label={t('dialectic.nuancedStatement')}
                          placeholder={t('dialectic.nuancedPlaceholder')}
                          value={nuancedInputs[ten.tension_id] || ''}
                          onChange={(e) =>
                            setNuancedInputs((prev) => ({
                              ...prev,
                              [ten.tension_id]: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="flex items-end">
                        <Button
                          variant="secondary"
                          disabled={isReconciling || !nuancedInputs[ten.tension_id]?.trim()}
                          onClick={() => void handleReconcile(ten.tension_id)}
                        >
                          {t('dialectic.reconcile')}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Belief Knowledge Graph Snapshot */}
      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('dialectic.beliefs')}</h2>
          <CardDescription>
            {snapshot ? t('dialectic.nodesCount', { count: snapshot.nodes_count }) : ''}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!snapshot || snapshot.top_beliefs.length === 0 ? (
            <p className="text-body text-fg-muted">{t('dialectic.noBeliefs')}</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {snapshot.top_beliefs.map((node: BeliefNode) => (
                <div
                  key={node.belief_id}
                  className="flex flex-col justify-between rounded-lg border border-border-default bg-surface-elevated p-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <Badge variant="neutral">{node.domain}</Badge>
                      <span className="text-caption text-fg-muted">
                        Conf: {(node.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-body text-fg">{node.statement}</p>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-caption text-fg-muted">
                    <span className="font-mono">{node.belief_id}</span>
                    <Badge
                      variant={
                        node.status === 'active'
                          ? 'success'
                          : node.status === 'contradicted'
                            ? 'warning'
                            : 'neutral'
                      }
                    >
                      {node.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
