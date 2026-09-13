import {
  Activity,
  Crosshair,
  Eye,
  Film,
  Layers,
  Play,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  visionDecomposeVideo,
  visionGetMetrics,
  visionGroundUIElements,
  visionInspectDiagram,
  visionReset,
  type UIElementGrounding,
  type VideoTimeline,
  type VisionMetricsResult,
} from '@/lib/bridge/vision';
import { useTranslation } from '@/lib/i18n';

export function VisionStudio() {
  const { t } = useTranslation('live');
  const { client } = useBridge();

  const [intent, setIntent] = useState('');
  const [isGrounding, setIsGrounding] = useState(false);
  const [isDecomposing, setIsDecomposing] = useState(false);
  const [isDiagramming, setIsDiagramming] = useState(false);
  const [groundedElements, setGroundedElements] = useState<UIElementGrounding[]>([]);
  const [proposedActions, setProposedActions] = useState<string[]>([]);
  const [videoTimeline, setVideoTimeline] = useState<VideoTimeline | null>(null);
  const [diagramResult, setDiagramResult] = useState<{
    valid: boolean;
    diagram_type?: string;
    total_nodes?: number;
    total_edges?: number;
    summary_fa: string;
  } | null>(null);
  const [metrics, setMetrics] = useState<VisionMetricsResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshMetrics = useCallback(async () => {
    try {
      const res = await visionGetMetrics(client);
      setMetrics(res);
    } catch {
      // Fallback
    }
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    void visionGetMetrics(client)
      .then((res) => {
        if (!cancelled) setMetrics(res);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleInspectScreen = async () => {
    setIsGrounding(true);
    setError(null);
    try {
      const res = await visionGroundUIElements(client, undefined, intent.trim());
      setGroundedElements(res.elements);
      setProposedActions(res.proposed_actions);
      await refreshMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsGrounding(false);
    }
  };

  const handleDecomposeVideo = async () => {
    setIsDecomposing(true);
    setError(null);
    try {
      const res = await visionDecomposeVideo(client, 'desktop_screen_record', 10.0, 30.0);
      setVideoTimeline(res);
      await refreshMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsDecomposing(false);
    }
  };

  const handleInspectDiagram = async () => {
    setIsDiagramming(true);
    setError(null);
    try {
      const mermaidCode =
        'graph TD\n  Client[Desktop Client] --> Bridge[Bridge Supervisor]\n  Bridge --> Kernel[Dream Kernel]\n  Kernel --> Vision[Vision Engine]';
      const res = await visionInspectDiagram(client, mermaidCode, 'mermaid');
      setDiagramResult(res);
      await refreshMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsDiagramming(false);
    }
  };

  const handleReset = async () => {
    setError(null);
    try {
      await visionReset(client);
      setGroundedElements([]);
      setProposedActions([]);
      setVideoTimeline(null);
      setDiagramResult(null);
      await refreshMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex flex-col gap-6" data-testid="vision-studio">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-accent-fg" />
              <h2 className="text-h3 font-semibold">{t('vision.title')}</h2>
            </div>
            <div className="flex items-center gap-2">
              {metrics && (
                <Badge variant="info">
                  <Activity className="mr-1 h-3 w-3" />
                  Analyses: {metrics.total_analyses_count}
                </Badge>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void handleReset()}
                aria-label={t('vision.reset')}
              >
                <Trash2 className="mr-1 h-4 w-4" />
                {t('vision.reset')}
              </Button>
            </div>
          </div>
          <CardDescription>{t('vision.subtitle')}</CardDescription>
        </CardHeader>

        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="flex-1">
              <Input
                label={t('vision.intent')}
                placeholder={t('vision.intentPlaceholder')}
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
              />
            </div>
            <div className="flex items-end gap-2">
              <Button
                variant="primary"
                disabled={isGrounding}
                onClick={() => void handleInspectScreen()}
              >
                {isGrounding ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    {t('vision.grounding')}
                  </>
                ) : (
                  <>
                    <Crosshair className="mr-1 h-4 w-4" />
                    {t('vision.groundAction')}
                  </>
                )}
              </Button>

              <Button
                variant="secondary"
                disabled={isDecomposing}
                onClick={() => void handleDecomposeVideo()}
              >
                {isDecomposing ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    {t('vision.decomposing')}
                  </>
                ) : (
                  <>
                    <Film className="mr-1 h-4 w-4" />
                    {t('vision.decomposeVideo')}
                  </>
                )}
              </Button>

              <Button
                variant="secondary"
                disabled={isDiagramming}
                onClick={() => void handleInspectDiagram()}
                aria-label={t('vision.inspectDiagram')}
              >
                {isDiagramming ? (
                  <RefreshCw className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Layers className="mr-1 h-4 w-4" />
                )}
                {t('vision.inspectDiagram')}
              </Button>
            </div>
          </div>

          {error && (
            <p
              role="alert"
              className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg"
            >
              {error}
            </p>
          )}

          {/* Proposed Actions Feedback */}
          {proposedActions.length > 0 && (
            <div className="rounded-lg border border-accent-solid bg-accent-soft p-3">
              <div className="flex items-center gap-2 text-accent-text font-medium text-body">
                <Sparkles className="h-4 w-4" />
                <span>Proposed Action:</span>
              </div>
              <ul className="mt-1 list-inside list-disc text-body text-accent-text">
                {proposedActions.map((act, i) => (
                  <li key={i}>{act}</li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Screen Elements Spatial Canvas & Grounding Targets */}
      {groundedElements.length > 0 && (
        <Card>
          <CardHeader>
            <h3 className="text-h4 font-semibold">{t('vision.detectedElements')}</h3>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Interactive Screen Overlay Canvas Preview */}
            <div className="relative h-48 w-full rounded-lg border border-border-default bg-surface-base overflow-hidden p-2">
              <div className="absolute inset-0 bg-grid-pattern opacity-10 pointer-events-none" />
              {groundedElements.map((elem) => {
                const top = `${elem.box.ymin * 100}%`;
                const left = `${elem.box.xmin * 100}%`;
                const width = `${(elem.box.xmax - elem.box.xmin) * 100}%`;
                const height = `${(elem.box.ymax - elem.box.ymin) * 100}%`;

                return (
                  <div
                    key={elem.element_id}
                    style={{ top, left, width, height }}
                    className="absolute flex items-center justify-between rounded border-2 border-accent-fg bg-accent-soft/30 p-1 transition-all hover:bg-accent-soft/50"
                  >
                    <span className="truncate text-micro font-medium text-accent-text">
                      {elem.label_fa}
                    </span>
                    <div
                      className="h-2.5 w-2.5 rounded-full bg-danger-fg animate-ping"
                      title={`Target: (${elem.click_target.x}, ${elem.click_target.y})`}
                    />
                  </div>
                );
              })}
            </div>

            {/* List of grounded elements */}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {groundedElements.map((elem) => (
                <div
                  key={elem.element_id}
                  className="flex items-center justify-between rounded-lg border border-border-default bg-surface-elevated p-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral">{elem.element_type}</Badge>
                      <span className="text-body font-medium text-fg">{elem.label_fa}</span>
                    </div>
                    <p className="text-caption text-fg-muted font-mono">ID: {elem.element_id}</p>
                  </div>
                  <div className="text-right">
                    <Badge variant="success">
                      {t('vision.confidence', { conf: (elem.confidence * 100).toFixed(0) })}
                    </Badge>
                    <p className="mt-1 text-micro text-fg-muted font-mono">
                      Target: ({elem.click_target.x}, {elem.click_target.y})
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Video Keyframe Timeline */}
      {videoTimeline && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Play className="h-5 w-5 text-accent-fg" />
              <h3 className="text-h4 font-semibold">{t('vision.videoTimeline')}</h3>
            </div>
            <CardDescription>{videoTimeline.narrative_summary_fa}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {videoTimeline.keyframes.map((kf) => (
                <div
                  key={kf.frame_id}
                  className="flex flex-col justify-between rounded-lg border border-border-default bg-surface-elevated p-3"
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Badge variant={kf.is_scene_transition ? 'warning' : 'neutral'}>
                        Scene {kf.scene_id} ({kf.timestamp_sec}s)
                      </Badge>
                      <span className="text-caption text-fg-muted">
                        Entropy: {kf.entropy_score}
                      </span>
                    </div>
                    <p className="text-body text-fg">{kf.caption_fa}</p>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1">
                    {kf.detected_entities.map((ent, i) => (
                      <Badge key={i} variant="neutral">
                        {ent}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diagram Inspection Result */}
      {diagramResult && (
        <Card>
          <CardHeader>
            <h3 className="text-h4 font-semibold">{t('vision.diagramInspector')}</h3>
            <CardDescription>{diagramResult.summary_fa}</CardDescription>
          </CardHeader>
          <CardContent className="flex gap-4">
            <div className="rounded-md border border-border-default bg-surface-elevated p-3 text-center">
              <span className="text-caption text-fg-muted">Nodes</span>
              <p className="text-h3 font-bold text-fg">{diagramResult.total_nodes ?? 0}</p>
            </div>
            <div className="rounded-md border border-border-default bg-surface-elevated p-3 text-center">
              <span className="text-caption text-fg-muted">Edges</span>
              <p className="text-h3 font-bold text-fg">{diagramResult.total_edges ?? 0}</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
