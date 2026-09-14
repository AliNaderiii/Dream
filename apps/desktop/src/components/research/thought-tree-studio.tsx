/** Interactive Tree-of-Thought & Self-Reflective MCTS Studio component. */

import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  GitBranch,
  Network,
  Play,
  RotateCcw,
  Scissors,
  Sparkles,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  reasoningBacktrack,
  reasoningExpandBranch,
  reasoningGetTreeStats,
  reasoningMctsSearch,
  reasoningPlanTree,
  reasoningReset,
  reasoningStepCritique,
  reasoningSynthesizeSolution,
  type MetacognitiveEvaluation,
  type ThoughtNode,
  type TreeStatsResult,
} from '@/lib/bridge/reasoning';
import { useTranslation } from '@/lib/i18n';

export function ThoughtTreeStudio() {
  const { t } = useTranslation('research');
  const { client } = useBridge();

  const [goal, setGoal] = useState('');
  const [stats, setStats] = useState<TreeStatsResult | null>(null);
  const [selectedNode, setSelectedNode] = useState<ThoughtNode | null>(null);
  const [critique, setCritique] = useState<MetacognitiveEvaluation | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [message, setMessage] = useState('');
  const [solutionSummary, setSolutionSummary] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!client) return;
    try {
      const statsRes = await reasoningGetTreeStats(client);
      setStats(statsRes);
      if (statsRes.trajectory?.nodes && statsRes.trajectory.nodes.length > 0) {
        setSelectedNode(statsRes.trajectory.nodes[0]);
      }
    } catch {
      // Handled silently
    }
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    if (!client) return;
    void reasoningGetTreeStats(client)
      .then((statsRes) => {
        if (!cancelled) {
          setStats(statsRes);
          if (statsRes.trajectory?.nodes && statsRes.trajectory.nodes.length > 0) {
            setSelectedNode(statsRes.trajectory.nodes[0]);
          }
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [client]);

  const handlePlanTree = async () => {
    if (!client || !goal.trim()) return;
    setIsProcessing(true);
    setMessage('');
    setSolutionSummary(null);
    try {
      const res = await reasoningPlanTree(client, goal.trim(), 'tree_of_thought');
      setMessage(t('thoughtTree.treeInitialized'));
      setStats({
        status: 'healthy',
        total_trajectories: 1,
        active_trajectory_id: res.trajectory_id,
        active_nodes_count: 1,
        pruned_nodes_count: 0,
        max_tree_depth: 0,
        confidence: 1.0,
        trajectory: res.trajectory,
      });
      if (res.trajectory.nodes && res.trajectory.nodes.length > 0) {
        setSelectedNode(res.trajectory.nodes[0]);
      }
    } catch (err) {
      setMessage(`خطا در ایجاد درخت استدلال: ${String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleMctsSearch = async () => {
    if (!client || !stats?.active_trajectory_id) return;
    setIsProcessing(true);
    try {
      await reasoningMctsSearch(client, stats.active_trajectory_id);
      setMessage(t('thoughtTree.mctsStepExecuted'));
      await loadData();
    } catch (err) {
      setMessage(`خطا در جستجوی MCTS: ${String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleExpandBranch = async (nodeId: string) => {
    if (!client || !stats?.active_trajectory_id) return;
    setIsProcessing(true);
    try {
      await reasoningExpandBranch(client, stats.active_trajectory_id, nodeId, [
        'شاخه تحلیلی: بررسی معماری و تخصیص منابع',
        'شاخه کاربردی: پیاده‌سازی گام‌های اجرایی و تست پایدار',
      ]);
      setMessage(t('thoughtTree.branchExpanded'));
      await loadData();
    } catch (err) {
      setMessage(`خطا در گسترش شاخه: ${String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleStepCritique = async (nodeId: string) => {
    if (!client || !stats?.active_trajectory_id) return;
    setIsProcessing(true);
    try {
      const res = await reasoningStepCritique(client, stats.active_trajectory_id, nodeId);
      setCritique(res.critique);
      setMessage(t('thoughtTree.critiqueCompleted'));
      await loadData();
    } catch (err) {
      setMessage(`خطا در تحلیل خودبازتابی: ${String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleBacktrack = async () => {
    if (!client || !stats?.active_trajectory_id) return;
    setIsProcessing(true);
    try {
      const res = await reasoningBacktrack(client, stats.active_trajectory_id, 0.35);
      setMessage(`${t('thoughtTree.backtrackDone')} (${res.pruned_nodes_count} شاخه ضعیف هرس شد)`);
      await loadData();
    } catch (err) {
      setMessage(`خطا در بازگشت و هرس شاخه‌ها: ${String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSynthesize = async () => {
    if (!client || !stats?.active_trajectory_id) return;
    setIsProcessing(true);
    try {
      const res = await reasoningSynthesizeSolution(client, stats.active_trajectory_id);
      setSolutionSummary(res.final_answer);
      setMessage(t('thoughtTree.solutionSynthesized'));
      await loadData();
    } catch (err) {
      setMessage(`خطا در سنتز راهکار نهایی: ${String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = async () => {
    if (!client) return;
    setIsProcessing(true);
    try {
      await reasoningReset(client);
      setStats(null);
      setSelectedNode(null);
      setCritique(null);
      setSolutionSummary(null);
      setGoal('');
      setMessage(t('thoughtTree.resetDone'));
    } catch (err) {
      setMessage(`خطا در پاکسازی: ${String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const nodes = stats?.trajectory?.nodes ?? [];

  return (
    <div className="flex flex-col gap-6 p-6 max-w-7xl mx-auto w-full">
      {/* Header & Goal Planner */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <Brain className="h-7 w-7 text-primary" />
          <div>
            <h2 className="text-xl font-bold tracking-tight">{t('thoughtTree.title')}</h2>
            <p className="text-sm text-muted-foreground">{t('thoughtTree.subtitle')}</p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 mt-2">
          <Input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder={t('thoughtTree.goalPlaceholder')}
            className="flex-1"
            disabled={isProcessing}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              onClick={() => void handlePlanTree()}
              disabled={isProcessing || !goal.trim()}
            >
              <Play className="h-4 w-4 me-1.5" />
              {t('thoughtTree.planTree')}
            </Button>
            <Button
              variant="secondary"
              onClick={() => void handleMctsSearch()}
              disabled={isProcessing || !stats?.active_trajectory_id}
            >
              <Network className="h-4 w-4 me-1.5" />
              {t('thoughtTree.mctsStep')}
            </Button>
            <Button
              variant="secondary"
              onClick={() => void handleBacktrack()}
              disabled={isProcessing || !stats?.active_trajectory_id}
            >
              <Scissors className="h-4 w-4 me-1.5" />
              {t('thoughtTree.backtrack')}
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleSynthesize()}
              disabled={isProcessing || !stats?.active_trajectory_id}
            >
              <Sparkles className="h-4 w-4 me-1.5" />
              {t('thoughtTree.synthesize')}
            </Button>
            <Button variant="ghost" onClick={() => void handleReset()} disabled={isProcessing}>
              <RotateCcw className="h-4 w-4 me-1.5" />
              {t('thoughtTree.reset')}
            </Button>
          </div>
        </div>
      </div>

      {message && (
        <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg text-xs font-medium text-primary flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" />
          <span>{message}</span>
        </div>
      )}

      {/* Metrics Bar */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('thoughtTree.stats.activeNodes')}
            </span>
            <p className="text-lg font-bold text-primary">{stats.active_nodes_count}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('thoughtTree.stats.prunedNodes')}
            </span>
            <p className="text-lg font-bold text-rose-500">{stats.pruned_nodes_count}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">{t('thoughtTree.stats.maxDepth')}</span>
            <p className="text-lg font-bold text-emerald-500">{stats.max_tree_depth}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('thoughtTree.stats.confidence')}
            </span>
            <p className="text-lg font-bold text-amber-500">
              {Math.round(stats.confidence * 100)}%
            </p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">{t('thoughtTree.stats.strategy')}</span>
            <p className="text-lg font-bold text-violet-500">MCTS + ToT</p>
          </Card>
        </div>
      )}

      {/* Synthesized Solution Box */}
      {solutionSummary && (
        <Card className="p-5 border-2 border-emerald-500/40 bg-emerald-500/5 flex flex-col gap-2.5">
          <div className="flex items-center gap-2 text-emerald-600 font-bold text-sm">
            <Sparkles className="h-4 w-4" />
            <span>{t('thoughtTree.solutionHeading')}</span>
          </div>
          <p className="text-xs font-mono whitespace-pre-line leading-relaxed text-foreground">
            {solutionSummary}
          </p>
        </Card>
      )}

      {/* Tree Visualization & Critique Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Thought Tree Node Explorer */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-primary" />
              {t('thoughtTree.treeNodesTitle')}
            </h3>
            <span className="text-xs text-muted-foreground">
              {nodes.length} {t('thoughtTree.totalNodes')}
            </span>
          </div>

          {nodes.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground text-sm border border-dashed rounded-xl">
              {t('thoughtTree.noNodesPrompt')}
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {nodes.map((node) => {
                const isSelected = selectedNode?.node_id === node.node_id;
                const isPruned = node.status === 'pruned';
                return (
                  <Card
                    key={node.node_id}
                    onClick={() => setSelectedNode(node)}
                    className={`p-4 cursor-pointer transition-all ${
                      isSelected
                        ? 'border-primary ring-1 ring-primary/40 bg-primary/5'
                        : isPruned
                          ? 'opacity-40 border-border/40'
                          : 'hover:border-border'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            node.depth === 0
                              ? 'accent'
                              : isPruned
                                ? 'danger'
                                : node.score >= 0.8
                                  ? 'success'
                                  : 'neutral'
                          }
                        >
                          Level {node.depth}
                        </Badge>
                        <span className="text-xs font-semibold">{node.thought_content}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-amber-500">
                          ★ {(node.score * 10).toFixed(1)}/10
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 mt-2 border-t border-border/30 text-xs text-muted-foreground">
                      <span>{node.eval_rationale || t('thoughtTree.defaultRationale')}</span>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleStepCritique(node.node_id);
                          }}
                        >
                          <Activity className="h-3.5 w-3.5 me-1 text-primary" />
                          {t('thoughtTree.critiqueBtn')}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleExpandBranch(node.node_id);
                          }}
                        >
                          <GitBranch className="h-3.5 w-3.5 me-1 text-emerald-500" />
                          {t('thoughtTree.expandBtn')}
                        </Button>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        {/* Self-Reflective Metacognitive Inspector */}
        <div className="flex flex-col gap-3">
          <h3 className="font-bold text-sm flex items-center gap-2">
            <Activity className="h-4 w-4 text-violet-500" />
            {t('thoughtTree.metacognitiveInspector')}
          </h3>

          <Card className="p-5 flex flex-col gap-4">
            {selectedNode ? (
              <>
                <div className="flex items-center justify-between border-b border-border/40 pb-3">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Node ID: {selectedNode.node_id}
                  </span>
                  <Badge variant={selectedNode.status === 'pruned' ? 'danger' : 'success'}>
                    {selectedNode.status.toUpperCase()}
                  </Badge>
                </div>

                <div className="flex flex-col gap-1.5">
                  <span className="text-xs text-muted-foreground">
                    {t('thoughtTree.thoughtStatement')}
                  </span>
                  <p className="text-xs font-medium bg-muted/20 p-2.5 rounded-lg border border-border/40">
                    {selectedNode.thought_content}
                  </p>
                </div>

                {critique ? (
                  <div className="flex flex-col gap-3 pt-2">
                    <div className="flex items-center justify-between text-xs">
                      <span>{t('thoughtTree.coherenceScore')}</span>
                      <span className="font-bold text-emerald-500">
                        {Math.round(critique.coherence_score * 100)}%
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span>{t('thoughtTree.depthScore')}</span>
                      <span className="font-bold text-primary">
                        {Math.round(critique.depth_score * 100)}%
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span>{t('thoughtTree.hallucinationRisk')}</span>
                      <span
                        className={`font-bold ${
                          critique.hallucination_risk > 0.3 ? 'text-rose-500' : 'text-emerald-500'
                        }`}
                      >
                        {Math.round(critique.hallucination_risk * 100)}%
                      </span>
                    </div>
                    <div className="p-3 bg-muted/30 rounded-lg text-xs flex flex-col gap-1 mt-1">
                      <span className="font-semibold text-muted-foreground">
                        {t('thoughtTree.critiqueNotes')}
                      </span>
                      <p className="text-foreground">{critique.critique_notes}</p>
                    </div>
                  </div>
                ) : (
                  <div className="p-4 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                    {t('thoughtTree.noCritiquePrompt')}
                  </div>
                )}
              </>
            ) : (
              <div className="p-6 text-center text-xs text-muted-foreground">
                <AlertTriangle className="h-6 w-6 text-muted-foreground mx-auto mb-2" />
                {t('thoughtTree.selectNodePrompt')}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
