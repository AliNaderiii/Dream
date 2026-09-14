/**
 * Interactive Hierarchical Episodic Memory & Temporal Knowledge Graph Studio.
 *
 * Provides visual exploration for:
 * 1. Multi-Tier Memory Hierarchy (L0 Working -> L1 Episodic -> L2 Temporal KG -> L3 Persona).
 * 2. Jalali / Gregorian Temporal Horizon Timeline.
 * 3. Cross-modal Entity Linking & Graph Edge Inspector.
 * 4. Consolidated Persona & Long-Term Competency Distillation.
 */

import {
  Activity,
  Brain,
  Calendar,
  CheckCircle2,
  Clock,
  GitBranch,
  Layers,
  RefreshCw,
  Search,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  episodicCompressSession,
  episodicConsolidate,
  episodicGetHierarchyStats,
  episodicLinkEntityFact,
  episodicQueryTimeline,
  episodicRecordEvent,
  episodicReset,
  type ConsolidatedPersona,
  type EpisodeRecord,
  type HierarchyStatsResult,
} from '@/lib/bridge/episodic-kg';
import { useTranslation } from '@/lib/i18n';

export function TemporalMemoryStudio() {
  const { t } = useTranslation('memory');
  const { client } = useBridge();

  const [activeTab, setActiveTab] = useState<'hierarchy' | 'timeline' | 'graph' | 'persona'>(
    'hierarchy',
  );
  const [stats, setStats] = useState<HierarchyStatsResult | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeRecord[]>([]);
  const [persona, setPersona] = useState<ConsolidatedPersona | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [message, setMessage] = useState('');

  const loadData = useCallback(async () => {
    if (!client) return;
    try {
      const [statsRes, timelineRes, personaRes] = await Promise.all([
        episodicGetHierarchyStats(client),
        episodicQueryTimeline(client, searchQuery),
        episodicConsolidate(client, false, 1),
      ]);
      setStats(statsRes);
      setEpisodes(timelineRes.episodes);
      setPersona(personaRes.persona);
    } catch {
      // Handled silently
    }
  }, [client, searchQuery]);

  useEffect(() => {
    let cancelled = false;
    if (!client) return;
    void Promise.all([
      episodicGetHierarchyStats(client),
      episodicQueryTimeline(client, searchQuery),
      episodicConsolidate(client, false, 1),
    ])
      .then(([statsRes, timelineRes, personaRes]) => {
        if (!cancelled) {
          setStats(statsRes);
          setEpisodes(timelineRes.episodes);
          setPersona(personaRes.persona);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [client, searchQuery]);

  const handleSimulateTurn = async () => {
    if (!client) return;
    setIsProcessing(true);
    try {
      await episodicRecordEvent(
        client,
        'live_session',
        'user',
        'طراحی سیستم ارکستراسیون ایجنت‌های مستقل دریم',
        0.8,
      );
      setMessage(t('temporalStudio.eventRecorded'));
      await loadData();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCompress = async () => {
    if (!client) return;
    setIsProcessing(true);
    try {
      await episodicCompressSession(client, 'live_session', undefined, 'مهندسی_سیستم');
      setMessage(t('temporalStudio.sessionCompressed'));
      await loadData();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleLinkFact = async (episodeId: string) => {
    if (!client) return;
    setIsProcessing(true);
    try {
      await episodicLinkEntityFact(
        client,
        episodeId,
        'DreamKernel',
        'concept',
        'references',
        'EpisodicMemory',
      );
      setMessage(t('temporalStudio.factLinked'));
      await loadData();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleConsolidate = async () => {
    if (!client) return;
    setIsProcessing(true);
    try {
      const res = await episodicConsolidate(client, true, 1);
      setPersona(res.persona);
      setMessage(t('temporalStudio.personaConsolidated'));
      await loadData();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = async () => {
    if (!client) return;
    setIsProcessing(true);
    try {
      await episodicReset(client);
      setMessage(t('temporalStudio.memoryReset'));
      await loadData();
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-primary/10 p-3 text-primary">
            <Brain className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">{t('temporalStudio.title')}</h2>
            <p className="text-sm text-muted-foreground">{t('temporalStudio.subtitle')}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleSimulateTurn()}
            disabled={isProcessing}
          >
            <Clock className="h-4 w-4 me-1.5" />
            {t('temporalStudio.simulateTurn')}
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => void handleCompress()}
            disabled={isProcessing}
          >
            <Sparkles className="h-4 w-4 me-1.5" />
            {t('temporalStudio.compressEpisode')}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleConsolidate()}
            disabled={isProcessing}
          >
            <TrendingUp className="h-4 w-4 me-1.5" />
            {t('temporalStudio.consolidatePersona')}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleReset()}
            disabled={isProcessing}
            aria-label={t('temporalStudio.reset')}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {message && (
        <div className="flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2 text-sm text-primary">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{message}</span>
        </div>
      )}

      {/* Metrics Bar */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('temporalStudio.stats.l0Working')}
            </span>
            <p className="text-lg font-bold text-primary">{stats.tier_0_working_turns}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('temporalStudio.stats.l1Episodes')}
            </span>
            <p className="text-lg font-bold text-emerald-500">{stats.tier_1_episodes_count}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('temporalStudio.stats.l2Facts')}
            </span>
            <p className="text-lg font-bold text-amber-500">{stats.tier_2_temporal_facts_count}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('temporalStudio.stats.kgNodes')}
            </span>
            <p className="text-lg font-bold text-violet-500">{stats.total_knowledge_graph_nodes}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('temporalStudio.stats.kgEdges')}
            </span>
            <p className="text-lg font-bold text-cyan-500">{stats.total_knowledge_graph_edges}</p>
          </Card>
          <Card className="p-3 text-center">
            <span className="text-xs text-muted-foreground">
              {t('temporalStudio.stats.compressionRatio')}
            </span>
            <p className="text-lg font-bold text-rose-500">{stats.compression_ratio}x</p>
          </Card>
        </div>
      )}

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-2 border-b border-border/40 pb-2">
        <Button
          variant={activeTab === 'hierarchy' ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => setActiveTab('hierarchy')}
        >
          <Layers className="h-4 w-4 me-1.5" />
          {t('temporalStudio.tabs.hierarchy')}
        </Button>
        <Button
          variant={activeTab === 'timeline' ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => setActiveTab('timeline')}
        >
          <Calendar className="h-4 w-4 me-1.5" />
          {t('temporalStudio.tabs.timeline')}
        </Button>
        <Button
          variant={activeTab === 'graph' ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => setActiveTab('graph')}
        >
          <GitBranch className="h-4 w-4 me-1.5" />
          {t('temporalStudio.tabs.graph')}
        </Button>
        <Button
          variant={activeTab === 'persona' ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => setActiveTab('persona')}
        >
          <Brain className="h-4 w-4 me-1.5" />
          {t('temporalStudio.tabs.persona')}
        </Button>
      </div>

      {/* Tab 1: Hierarchy View */}
      {activeTab === 'hierarchy' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card className="p-5 flex flex-col gap-3 border-s-4 border-s-primary">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-primary">
                {t('temporalStudio.tier0Title')}
              </span>
              <Badge variant="neutral">L0 Buffer</Badge>
            </div>
            <h3 className="font-bold text-base">{t('temporalStudio.tier0Heading')}</h3>
            <p className="text-sm text-muted-foreground">{t('temporalStudio.tier0Desc')}</p>
            <div className="rounded-lg bg-muted/30 p-3 text-xs font-mono">
              {stats?.tier_0_working_turns ?? 0} {t('temporalStudio.workingTurnsBuffered')}
            </div>
          </Card>

          <Card className="p-5 flex flex-col gap-3 border-s-4 border-s-emerald-500">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-emerald-500">
                {t('temporalStudio.tier1Title')}
              </span>
              <Badge variant="info">L1 Episodic</Badge>
            </div>
            <h3 className="font-bold text-base">{t('temporalStudio.tier1Heading')}</h3>
            <p className="text-sm text-muted-foreground">{t('temporalStudio.tier1Desc')}</p>
            <div className="rounded-lg bg-muted/30 p-3 text-xs font-mono">
              {stats?.tier_1_episodes_count ?? 0} {t('temporalStudio.episodesDistilled')}
            </div>
          </Card>

          <Card className="p-5 flex flex-col gap-3 border-s-4 border-s-amber-500">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-amber-500">
                {t('temporalStudio.tier2Title')}
              </span>
              <Badge variant="accent">L2 Temporal KG</Badge>
            </div>
            <h3 className="font-bold text-base">{t('temporalStudio.tier2Heading')}</h3>
            <p className="text-sm text-muted-foreground">{t('temporalStudio.tier2Desc')}</p>
            <div className="rounded-lg bg-muted/30 p-3 text-xs font-mono">
              {stats?.total_knowledge_graph_nodes ?? 0} Nodes ·{' '}
              {stats?.total_knowledge_graph_edges ?? 0} Edges
            </div>
          </Card>

          <Card className="p-5 flex flex-col gap-3 border-s-4 border-s-violet-500">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-violet-500">
                {t('temporalStudio.tier3Title')}
              </span>
              <Badge variant="success">L3 Persona</Badge>
            </div>
            <h3 className="font-bold text-base">{t('temporalStudio.tier3Heading')}</h3>
            <p className="text-sm text-muted-foreground">{t('temporalStudio.tier3Desc')}</p>
            <div className="rounded-lg bg-muted/30 p-3 text-xs font-mono">
              {persona?.primary_domains.join(', ') || 'AI Engineering'}
            </div>
          </Card>
        </div>
      )}

      {/* Tab 2: Timeline View */}
      {activeTab === 'timeline' && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute start-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('temporalStudio.searchPlaceholder')}
                className="ps-9"
              />
            </div>
            <Button variant="secondary" size="sm" onClick={() => void loadData()}>
              {t('temporalStudio.filter')}
            </Button>
          </div>

          <div className="flex flex-col gap-3">
            {episodes.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-sm border border-dashed rounded-xl">
                {t('temporalStudio.noEpisodes')}
              </div>
            ) : (
              episodes.map((ep) => (
                <Card key={ep.episode_id} className="p-4 flex flex-col gap-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4 text-primary" />
                      <span className="font-bold text-sm">{ep.title_fa}</span>
                      <Badge variant="neutral">{ep.jalali_date}</Badge>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-amber-500 font-semibold">
                        ★ {ep.importance_score}/5
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void handleLinkFact(ep.episode_id)}
                      >
                        <GitBranch className="h-3.5 w-3.5 me-1" />
                        {t('temporalStudio.linkFact')}
                      </Button>
                    </div>
                  </div>

                  <p className="text-xs text-muted-foreground">{ep.summary_fa}</p>

                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    {ep.linked_entities.map((ent, idx) => (
                      <Badge key={idx} variant="neutral" className="text-[11px]">
                        #{ent}
                      </Badge>
                    ))}
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Graph View */}
      {activeTab === 'graph' && (
        <Card className="p-6 flex flex-col gap-4 bg-muted/10">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-base flex items-center gap-2">
              <GitBranch className="h-5 w-5 text-primary" />
              {t('temporalStudio.graphStructure')}
            </h3>
            <Badge variant="neutral">
              {stats?.total_knowledge_graph_nodes ?? 0} {t('temporalStudio.nodes')}
            </Badge>
          </div>

          <div className="rounded-xl border border-border/50 bg-background p-6 flex flex-col items-center justify-center gap-4 min-h-[220px]">
            <div className="flex flex-wrap justify-center items-center gap-4">
              <div className="rounded-xl bg-primary/20 border border-primary/40 px-4 py-2 text-center">
                <span className="text-xs text-muted-foreground block">Core Entity</span>
                <span className="font-bold text-sm">عامل دریم (DreamAgent)</span>
              </div>
              <div className="text-muted-foreground text-xs font-mono">──── [references] ────►</div>
              <div className="rounded-xl bg-emerald-500/20 border border-emerald-500/40 px-4 py-2 text-center">
                <span className="text-xs text-muted-foreground block">Episodic Entity</span>
                <span className="font-bold text-sm">زیرسیستم حافظه سلسله‌مراتبی</span>
              </div>
              <div className="text-muted-foreground text-xs font-mono">
                ──── [anchored_at] ────►
              </div>
              <div className="rounded-xl bg-violet-500/20 border border-violet-500/40 px-4 py-2 text-center">
                <span className="text-xs text-muted-foreground block">Temporal Horizon</span>
                <span className="font-bold text-sm">۱۴۰۳/۰۶/۲۵</span>
              </div>
            </div>
            <p className="text-xs text-muted-foreground text-center max-w-md">
              {t('temporalStudio.graphExplanation')}
            </p>
          </div>
        </Card>
      )}

      {/* Tab 4: Persona View */}
      {activeTab === 'persona' && persona && (
        <Card className="p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between border-b border-border/40 pb-3">
            <div className="flex items-center gap-2.5">
              <Activity className="h-5 w-5 text-violet-500" />
              <div>
                <h3 className="font-bold text-base">{persona.user_title_fa}</h3>
                <span className="text-xs text-muted-foreground">
                  {t('temporalStudio.synthesizedFrom')} {persona.total_episodes_synthesized}{' '}
                  {t('temporalStudio.episodes')}
                </span>
              </div>
            </div>
            <Badge variant="accent">Tier 3 Active</Badge>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-muted-foreground">
                {t('temporalStudio.primaryDomains')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {persona.primary_domains.map((dom, idx) => (
                  <Badge key={idx} variant="neutral">
                    {dom}
                  </Badge>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-muted-foreground">
                {t('temporalStudio.skillMasteries')}
              </span>
              <div className="flex flex-col gap-1.5">
                {Object.entries(persona.skill_masteries).map(([skill, val]) => (
                  <div key={skill} className="flex items-center justify-between text-xs">
                    <span className="font-mono">{skill}</span>
                    <span className="font-bold text-primary">{Math.round(val * 100)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
