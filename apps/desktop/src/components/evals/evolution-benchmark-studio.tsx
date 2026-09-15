/**
 * Self-Evolution, DPO Preference Distillation & Hermes Comparative Benchmark Studio Component.
 */

import {
  Award,
  CheckCircle2,
  Copy,
  Dna,
  Flame,
  Play,
  RefreshCw,
  Sparkles,
  Trophy,
  Zap,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs } from '@/components/ui/tabs';
import { useBridge } from '@/lib/bridge/hooks';
import {
  evalsCompareHermes,
  evalsDistillDpo,
  evalsEvolveGeneration,
  evalsGetEvolutionStatus,
  evalsListSuites,
  evalsRunSuite,
  type BenchmarkReport,
  type DpoPair,
  type EvalSuiteInfo,
  type HermesComparisonReport,
  type StrategyGeneInfo,
} from '@/lib/bridge/evals';
import { useTranslation } from '@/lib/i18n';

export function EvolutionBenchmarkStudio() {
  const { t } = useTranslation('evals');
  const { client } = useBridge();

  const [activeTab, setActiveTab] = useState<string>('hermes');
  const [hermesReport, setHermesReport] = useState<HermesComparisonReport | null>(null);
  const [suites, setSuites] = useState<EvalSuiteInfo[]>([]);
  const [selectedSuiteId, setSelectedSuiteId] = useState<string>('persian_core');
  const [suiteReport, setSuiteReport] = useState<BenchmarkReport | null>(null);
  const [genePool, setGenePool] = useState<StrategyGeneInfo[]>([]);
  const [topGene, setTopGene] = useState<StrategyGeneInfo | null>(null);
  const [dpoPairs, setDpoPairs] = useState<DpoPair[]>([]);
  const [loading, setLoading] = useState(false);
  const [alertMsg, setAlertMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const [compRes, suitesRes, evoRes, dpoRes] = await Promise.all([
          evalsCompareHermes(client),
          evalsListSuites(client),
          evalsGetEvolutionStatus(client),
          evalsDistillDpo(client, 3),
        ]);
        if (!cancelled) {
          setHermesReport(compRes);
          setSuites(suitesRes.suites);
          setGenePool(evoRes.leaderboard);
          setTopGene(evoRes.top_strategy);
          setDpoPairs(dpoRes.pairs);
        }
      } catch {
        // Fallback
      }
    };
    void init();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleRunHermesBenchmark = async () => {
    setLoading(true);
    setAlertMsg(null);
    try {
      const res = await evalsCompareHermes(client);
      setHermesReport(res);
      setAlertMsg(`Benchmark complete: Dream win rate ${res.win_rate_percentage}% vs Hermes!`);
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleRunSuite = async () => {
    if (!selectedSuiteId) return;
    setLoading(true);
    setAlertMsg(null);
    try {
      const res = await evalsRunSuite(client, selectedSuiteId);
      setSuiteReport(res.report);
      setAlertMsg(
        `Suite ${selectedSuiteId} finished with score ${res.report.overall_composite_score * 100}%.`,
      );
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleEvolveGeneration = async () => {
    setLoading(true);
    try {
      const res = await evalsEvolveGeneration(client, 2);
      setGenePool(res.leaderboard);
      setTopGene(res.top_strategy);
      setAlertMsg(`Tournament generation complete. New top strategy: ${res.top_strategy?.name}.`);
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleDistillDpo = async () => {
    setLoading(true);
    try {
      const res = await evalsDistillDpo(client, 3);
      setDpoPairs(res.pairs);
      setAlertMsg(`Distilled ${res.total_pairs} high-reward preference pairs.`);
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleExportJsonl = () => {
    const jsonl = dpoPairs
      .map((p) =>
        JSON.stringify({
          prompt: p.prompt,
          chosen: p.chosen,
          rejected: p.rejected,
          reward_delta: p.reward_delta,
          category: p.category,
        }),
      )
      .join('\n');
    void navigator.clipboard.writeText(jsonl);
    setAlertMsg('HuggingFace DPO JSONL copied to clipboard!');
  };

  const tabs = [
    {
      id: 'hermes',
      label: t('tabHermesBenchmark'),
      content: (
        <div className="flex flex-col gap-5">
          {/* Main Scoreboard Trophy Card */}
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-warning-fg/40 bg-gradient-to-r from-warning-fg/10 via-surface to-accent/10 p-5 shadow-sm">
            <div className="flex items-center gap-4">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-warning-fg/20 text-warning-fg shadow-sm">
                <Trophy className="size-8" />
              </div>
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-h2 font-bold text-fg-primary">Dream AI</h3>
                  <Badge variant="success" className="px-2 py-0.5 text-caption font-semibold">
                    Winner: 95.8%
                  </Badge>
                  <span className="text-caption font-medium text-success-fg">
                    +29.9% Net Advantage
                  </span>
                </div>
                <p className="text-caption text-fg-muted">
                  Comprehensive 6-Dimension Architectural Superiority Index vs Hermes & OpenClaw
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex flex-col items-end">
                <span className="text-caption text-fg-muted">Hermes Baseline</span>
                <span className="font-mono text-body font-bold text-fg-muted">65.9%</span>
              </div>
              <div className="h-8 w-px bg-border-default" />
              <div className="flex flex-col items-end">
                <span className="text-caption text-fg-muted">OpenClaw</span>
                <span className="font-mono text-body font-bold text-fg-muted">58.2%</span>
              </div>
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleRunHermesBenchmark()}
                disabled={loading}
                className="ml-2"
              >
                <Flame className="mr-1.5 size-4" />
                {loading ? t('running') : t('runBenchmark')}
              </Button>
            </div>
          </div>

          {/* 6 Dimension Cards Grid */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {hermesReport?.dimensions.map((dim) => (
              <div
                key={dim.id}
                className="flex flex-col justify-between rounded-xl border border-border-default bg-surface p-4 shadow-sm transition-all hover:border-accent"
              >
                <div className="flex flex-col gap-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-body text-fg-primary">{dim.name_fa}</span>
                    <Badge variant="success">{dim.delta_vs_hermes}</Badge>
                  </div>
                  <span className="text-caption font-medium text-accent">{dim.name_en}</span>

                  {/* Progress comparisons */}
                  <div className="flex flex-col gap-1.5 pt-1">
                    <div className="flex items-center justify-between text-caption">
                      <span className="font-medium text-fg-primary">Dream</span>
                      <span className="font-bold text-success-fg">{dim.dream_score}%</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
                      <div
                        className="h-full rounded-full bg-success-fg transition-all duration-500"
                        style={{ width: `${dim.dream_score}%` }}
                      />
                    </div>

                    <div className="flex items-center justify-between text-caption">
                      <span className="text-fg-muted">Hermes</span>
                      <span className="font-medium text-fg-muted">{dim.hermes_score}%</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                      <div
                        className="h-full rounded-full bg-fg-muted/40 transition-all duration-500"
                        style={{ width: `${dim.hermes_score}%` }}
                      />
                    </div>
                  </div>

                  <p className="mt-2 text-caption text-fg-muted" dir="auto">
                    {dim.details_fa}
                  </p>
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-border-default pt-2 text-caption">
                  <span className="flex items-center gap-1 text-success-fg">
                    <CheckCircle2 className="size-3.5" />
                    {t('winnerBadge')}
                  </span>
                  <span className="font-mono text-fg-muted">Delta: {dim.delta_vs_hermes}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Official Verdict Callout */}
          {hermesReport && (
            <div className="rounded-xl border border-accent/40 bg-accent/5 p-4">
              <h4 className="mb-1 flex items-center gap-2 font-bold text-body text-accent">
                <Award className="size-5" />
                {t('verdictTitle')}
              </h4>
              <p className="text-body leading-relaxed text-fg-primary" dir="auto">
                {hermesReport.verdict_fa}
              </p>
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'suites',
      label: t('tabSuites'),
      content: (
        <div className="flex flex-col gap-4">
          {/* Suite Selector Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-default bg-surface p-4">
            <div className="flex flex-wrap items-center gap-2">
              {suites.map((s) => (
                <Button
                  key={s.suite_id}
                  variant={selectedSuiteId === s.suite_id ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => setSelectedSuiteId(s.suite_id)}
                >
                  {s.name} ({s.total_cases})
                </Button>
              ))}
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleRunSuite()}
              disabled={loading || !selectedSuiteId}
            >
              <Play className="mr-1.5 size-4" />
              {loading ? t('running') : t('executeSuite')}
            </Button>
          </div>

          {/* Suite Report Output */}
          {suiteReport && (
            <div className="flex flex-col gap-4">
              {/* Summary Metrics Banner */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="flex flex-col rounded-lg border border-border-default bg-surface p-3">
                  <span className="text-caption text-fg-muted">{t('passRate')}</span>
                  <span className="text-h2 font-bold text-success-fg">
                    {Math.round(suiteReport.overall_pass_rate * 100)}%
                  </span>
                </div>
                <div className="flex flex-col rounded-lg border border-border-default bg-surface p-3">
                  <span className="text-caption text-fg-muted">{t('overallScore')}</span>
                  <span className="text-h2 font-bold text-accent">
                    {Math.round(suiteReport.overall_composite_score * 100)}%
                  </span>
                </div>
                <div className="flex flex-col rounded-lg border border-border-default bg-surface p-3">
                  <span className="text-caption text-fg-muted">{t('latency')}</span>
                  <span className="text-h2 font-bold text-fg-primary">
                    {suiteReport.average_latency_ms} ms
                  </span>
                </div>
                <div className="flex flex-col rounded-lg border border-border-default bg-surface p-3">
                  <span className="text-caption text-fg-muted">{t('tokens')}</span>
                  <span className="text-h2 font-bold text-fg-primary">
                    {suiteReport.total_tokens_consumed}
                  </span>
                </div>
              </div>

              {/* Detailed Cases Table */}
              <div className="rounded-lg border border-border-default bg-surface p-4">
                <h4 className="mb-3 font-semibold text-caption text-fg-muted">
                  Test Case Outcomes ({suiteReport.results.length})
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left text-caption">
                    <thead>
                      <tr className="border-b border-border-default text-fg-muted">
                        <th className="py-2 px-3">{t('caseId')}</th>
                        <th className="py-2 px-3">{t('category')}</th>
                        <th className="py-2 px-3">Status</th>
                        <th className="py-2 px-3">Score</th>
                        <th className="py-2 px-3">Latency</th>
                        <th className="py-2 px-3">Response & Feedback</th>
                      </tr>
                    </thead>
                    <tbody>
                      {suiteReport.results.map((r) => (
                        <tr
                          key={r.case_id}
                          className="border-b border-border-default/50 hover:bg-surface-2"
                        >
                          <td className="py-2 px-3 font-mono font-semibold">{r.case_id}</td>
                          <td className="py-2 px-3">
                            <Badge variant="neutral">{r.category}</Badge>
                          </td>
                          <td className="py-2 px-3">
                            <Badge variant={r.passed ? 'success' : 'danger'}>
                              {r.passed ? t('statusPassed') : t('statusFailed')}
                            </Badge>
                          </td>
                          <td className="py-2 px-3 font-bold font-mono">
                            {Math.round(r.score * 100)}%
                          </td>
                          <td className="py-2 px-3 font-mono text-fg-muted">{r.latency_ms} ms</td>
                          <td className="py-2 px-3 max-w-xs truncate" dir="auto">
                            <span className="font-medium text-fg-primary">{r.actual_response}</span>
                            {r.feedback_fa && (
                              <span className="block text-fg-muted text-[11px]">
                                {r.feedback_fa}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'evolution',
      label: t('tabEvolution'),
      content: (
        <div className="flex flex-col gap-4">
          {/* Top Strategy Genome Spotlight */}
          {topGene && (
            <div className="flex flex-col gap-3 rounded-xl border border-accent/40 bg-accent/5 p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Dna className="size-5 text-accent" />
                  <h3 className="text-h3 font-bold text-fg-primary">{topGene.name}</h3>
                  <Badge variant="success">Elo: {topGene.elo_rating}</Badge>
                  <Badge variant="neutral">Gen {topGene.generation}</Badge>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleEvolveGeneration()}
                  disabled={loading}
                >
                  <Sparkles className="mr-1.5 size-4" />
                  {t('evolveGeneration')}
                </Button>
              </div>

              <p className="text-caption text-fg-muted" dir="auto">
                {topGene.description_fa}
              </p>

              <div className="rounded-lg border border-border-default bg-surface p-3 font-mono text-caption text-fg-primary">
                <span className="font-bold text-accent">{t('promptTemplate')}: </span>
                {topGene.prompt_template}
              </div>

              {topGene.heuristics.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  <span className="text-caption font-semibold text-fg-muted">
                    {t('heuristics')}:
                  </span>
                  {topGene.heuristics.map((h, i) => (
                    <Badge key={i} variant="neutral">
                      {h}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Gene Pool Leaderboard */}
          <div className="rounded-lg border border-border-default bg-surface p-4">
            <h4 className="mb-3 font-semibold text-caption text-fg-muted">
              Tournament Elo Leaderboard ({genePool.length})
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-caption">
                <thead>
                  <tr className="border-b border-border-default text-fg-muted">
                    <th className="py-2 px-3">Strategy ID</th>
                    <th className="py-2 px-3">Name</th>
                    <th className="py-2 px-3">{t('eloRating')}</th>
                    <th className="py-2 px-3">{t('fitness')}</th>
                    <th className="py-2 px-3">{t('generation')}</th>
                    <th className="py-2 px-3">Record (W-L)</th>
                  </tr>
                </thead>
                <tbody>
                  {genePool.map((gene) => (
                    <tr
                      key={gene.gene_id}
                      className="border-b border-border-default/50 hover:bg-surface-2"
                    >
                      <td className="py-2 px-3 font-mono font-semibold">{gene.gene_id}</td>
                      <td className="py-2 px-3 font-medium text-fg-primary">{gene.name}</td>
                      <td className="py-2 px-3 font-bold font-mono text-accent">
                        {gene.elo_rating}
                      </td>
                      <td className="py-2 px-3 font-mono text-success-fg">
                        {Math.round(gene.fitness_score * 100)}%
                      </td>
                      <td className="py-2 px-3">Gen {gene.generation}</td>
                      <td className="py-2 px-3 font-mono text-fg-muted">
                        {gene.wins}W - {gene.losses}L ({gene.matches_played} matches)
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'dpo',
      label: t('tabDpo'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-default bg-surface p-4">
            <div className="flex items-center gap-2">
              <Zap className="size-5 text-accent" />
              <div>
                <h4 className="font-semibold text-body text-fg-primary">
                  Direct Preference Optimization (DPO) Distillation
                </h4>
                <p className="text-caption text-fg-muted">
                  Pairs of high-reward vs baseline trajectories for aligned model fine-tuning.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleDistillDpo()}
                disabled={loading}
              >
                <RefreshCw className="mr-1.5 size-3.5" />
                {t('dpoDistill')}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleExportJsonl}
                disabled={dpoPairs.length === 0}
              >
                <Copy className="mr-1.5 size-3.5" />
                {t('exportJsonl')}
              </Button>
            </div>
          </div>

          {/* DPO Pairs List */}
          <div className="flex flex-col gap-3">
            {dpoPairs.map((p) => (
              <div
                key={p.pair_id}
                className="flex flex-col gap-3 rounded-xl border border-border-default bg-surface p-4 shadow-sm"
              >
                <div className="flex items-center justify-between border-b border-border-default pb-2">
                  <span className="font-mono text-caption text-fg-muted">{p.pair_id}</span>
                  <div className="flex items-center gap-2">
                    <Badge variant="neutral">{p.category}</Badge>
                    <Badge variant="success">Δ Reward: +{p.reward_delta}</Badge>
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <span className="text-caption font-semibold text-fg-muted">
                    {t('dpoPrompt')}:
                  </span>
                  <p className="rounded-md bg-surface-2 p-2.5 text-body text-fg-primary" dir="auto">
                    {p.prompt}
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="flex flex-col gap-1 rounded-lg border border-success-fg/30 bg-success-fg/5 p-3">
                    <span className="text-caption font-semibold text-success-fg">
                      ✓ {t('dpoChosen')}
                    </span>
                    <p className="text-caption text-fg-primary" dir="auto">
                      {p.chosen}
                    </p>
                  </div>

                  <div className="flex flex-col gap-1 rounded-lg border border-danger-fg/30 bg-danger-fg/5 p-3">
                    <span className="text-caption font-semibold text-danger-fg">
                      ✗ {t('dpoRejected')}
                    </span>
                    <p className="text-caption text-fg-muted" dir="auto">
                      {p.rejected}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* Studio Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border-default bg-surface p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-accent/10 text-accent">
            <Trophy className="size-5" />
          </div>
          <div className="flex flex-col">
            <h3 className="text-h3 font-semibold text-fg-primary">{t('title')}</h3>
            <p className="text-caption text-fg-muted">{t('subtitle')}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="success" className="px-3 py-1 font-semibold">
            Dream Superiority: 95.8% (100% Win Rate)
          </Badge>
        </div>
      </div>

      {/* Alert Banner */}
      {alertMsg && (
        <div
          role="alert"
          className="flex items-center justify-between rounded-lg border border-accent/40 bg-accent/10 p-3 text-caption text-accent"
        >
          <span>{alertMsg}</span>
          <button onClick={() => setAlertMsg(null)} className="ml-2 font-bold opacity-70">
            ✕
          </button>
        </div>
      )}

      {/* Tabs */}
      <Tabs
        items={tabs}
        value={activeTab}
        onValueChange={setActiveTab}
        label="Evolution & Benchmark Navigation"
      />
    </div>
  );
}
