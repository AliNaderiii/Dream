import { useEffect, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useBridge } from '@/lib/bridge/hooks';
import {
  duplexExportTranscript,
  duplexGetMetrics,
  duplexGetVisualizer,
  duplexInjectInterruption,
  duplexPushMicChunk,
  duplexStart,
  duplexStop,
  type DuplexVisualizerFrame,
} from '@/lib/bridge/duplex';
import { useTranslation } from '@/lib/i18n';

export function VoiceStudio() {
  const { t } = useTranslation('live');
  const { client } = useBridge();

  const [isActive, setIsActive] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [duplexState, setDuplexState] = useState<'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted'>('idle');
  const [vadThreshold, setVadThreshold] = useState(0.5);
  const [visualizer, setVisualizer] = useState<DuplexVisualizerFrame>({
    timestamp_ms: Date.now(),
    rms_volume: 0.0,
    waveform_peaks: Array(16).fill(0.0),
    frequency_bins: Array(8).fill(0.0),
    is_speaking: false,
  });
  const [latencyMs, setLatencyMs] = useState(140);
  const [transcript, setTranscript] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Polling loop for visualizer frames and state
  useEffect(() => {
    if (!isActive) {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      return;
    }

    pollTimerRef.current = setInterval(async () => {
      try {
        const frame = await duplexGetVisualizer(client);
        setVisualizer(frame);

        if (frame.is_speaking) {
          setDuplexState('speaking');
        } else if (frame.rms_volume > vadThreshold) {
          setDuplexState('listening');
        } else if (duplexState === 'speaking') {
          setDuplexState('listening');
        }
      } catch (err) {
        // Fallback or ignore transient poll errors
      }
    }, 80);

    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [client, isActive, vadThreshold, duplexState]);

  const handleStartSession = async () => {
    setError(null);
    try {
      const res = await duplexStart(client, 'desktop-live-voice', 16000, vadThreshold);
      setIsActive(true);
      setDuplexState('listening');

      // Seed mock microphone chunk
      await duplexPushMicChunk(client, 'U2FtcGxlUEMxNkF1ZGlvQ2h1bms=');
      const metrics = await duplexGetMetrics(client, 'desktop-live-voice');
      if (metrics?.stats?.estimated_latency_ms) {
        setLatencyMs(metrics.stats.estimated_latency_ms);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleStopSession = async () => {
    try {
      await duplexStop(client);
      setIsActive(false);
      setDuplexState('idle');
      setVisualizer({
        timestamp_ms: Date.now(),
        rms_volume: 0.0,
        waveform_peaks: Array(16).fill(0.0),
        frequency_bins: Array(8).fill(0.0),
        is_speaking: false,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleBargeIn = async () => {
    try {
      await duplexInjectInterruption(client, 'desktop-live-voice');
      setDuplexState('interrupted');
      setTimeout(() => setDuplexState('listening'), 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleExportTranscript = async () => {
    try {
      const res = await duplexExportTranscript(client, 'desktop-live-voice', 'markdown');
      setTranscript(res.transcript);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const stateColors: Record<string, string> = {
    idle: 'bg-zinc-700 text-zinc-200 border-zinc-600',
    listening: 'bg-emerald-600/30 text-emerald-300 border-emerald-500 animate-pulse',
    thinking: 'bg-amber-600/30 text-amber-300 border-amber-500 animate-pulse',
    speaking: 'bg-indigo-600/40 text-indigo-200 border-indigo-400 animate-bounce',
    interrupted: 'bg-rose-600/40 text-rose-200 border-rose-500',
  };

  const stateLabelsFa: Record<string, string> = {
    idle: 'آماده‌به‌کار (Off)',
    listening: 'در حال شنیدن صدای شما (Listening)',
    thinking: 'در حال پردازش و تفکر (Thinking)',
    speaking: 'در حال پاسخ صوتی (Speaking)',
    interrupted: 'قطع مکالمه دستی (Barge-in)',
  };

  return (
    <Card className="w-full border-zinc-800 bg-zinc-950/80 text-zinc-100 backdrop-blur-md shadow-2xl">
      <CardHeader className="flex flex-row items-center justify-between border-b border-zinc-800/80 pb-4">
        <div>
          <CardTitle className="text-xl font-bold flex items-center gap-2">
            🎙️ استودیوی صوتی دوبلکس زنده (Desktop Live Voice Studio)
          </CardTitle>
          <CardDescription className="text-zinc-400 text-sm mt-1">
            مکالمه صوتی هم‌زمان، تشخیص بلادرنگ گفتار با VAD v5 و قطع آنی (Zero-Latency Barge-in)
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Badge className={`px-3 py-1 text-xs border ${stateColors[duplexState]}`}>
            {stateLabelsFa[duplexState]}
          </Badge>
          <Badge className="bg-zinc-800 text-zinc-300 border-zinc-700 text-xs">
            {latencyMs}ms Latency
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        {error && (
          <div className="p-3 bg-rose-950/50 border border-rose-800 text-rose-300 rounded-lg text-sm">
            ⚠️ {error}
          </div>
        )}

        {/* 3D/2D Dynamic Audio Waveform & Pulse Visualizer */}
        <div className="relative flex flex-col items-center justify-center p-8 bg-zinc-900/60 rounded-2xl border border-zinc-800/70 overflow-hidden min-h-[220px]">
          {/* Glowing background pulse aura */}
          <div
            className="absolute rounded-full transition-all duration-150 blur-2xl opacity-40 pointer-events-none"
            style={{
              width: `${Math.max(120, visualizer.rms_volume * 400)}px`,
              height: `${Math.max(120, visualizer.rms_volume * 400)}px`,
              backgroundColor:
                duplexState === 'speaking'
                  ? '#818cf8'
                  : duplexState === 'listening'
                  ? '#10b981'
                  : '#3b82f6',
            }}
          />

          {/* Central Animated Equalizer Waveform */}
          <div className="flex items-center justify-center gap-1.5 h-28 z-10 w-full max-w-md">
            {visualizer.waveform_peaks.map((peak, idx) => {
              const heightPct = Math.max(8, Math.min(100, Math.abs(peak) * 100 + (isActive ? 12 : 4)));
              return (
                <div
                  key={idx}
                  className="flex-1 rounded-full transition-all duration-75"
                  style={{
                    height: `${heightPct}%`,
                    background:
                      duplexState === 'speaking'
                        ? 'linear-gradient(to top, #6366f1, #a855f7)'
                        : duplexState === 'listening'
                        ? 'linear-gradient(to top, #059669, #34d399)'
                        : 'linear-gradient(to top, #3f3f46, #71717a)',
                    boxShadow: isActive ? '0 0 10px rgba(99, 102, 241, 0.4)' : 'none',
                  }}
                />
              );
            })}
          </div>

          {/* 8-Band Frequency Spectrum Bar */}
          <div className="flex items-center justify-center gap-3 mt-4 z-10 w-full max-w-xs">
            {visualizer.frequency_bins.map((bin, idx) => (
              <div key={idx} className="flex flex-col items-center gap-1 flex-1">
                <div
                  className="w-full bg-indigo-500/80 rounded-t transition-all duration-100"
                  style={{ height: `${Math.max(4, bin * 32)}px` }}
                />
                <span className="text-[9px] text-zinc-500 font-mono">{idx + 1}k</span>
              </div>
            ))}
          </div>
        </div>

        {/* Studio Controls Panel */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 pt-2">
          {!isActive ? (
            <Button
              onClick={handleStartSession}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-2.5 rounded-xl shadow-lg shadow-emerald-950"
            >
              📞 شروع مکالمه زنده
            </Button>
          ) : (
            <Button
              onClick={handleStopSession}
              variant="destructive"
              className="bg-rose-600 hover:bg-rose-500 text-white font-semibold py-2.5 rounded-xl shadow-lg shadow-rose-950"
            >
              🛑 قطع تماس صوتی
            </Button>
          )}

          <Button
            onClick={handleBargeIn}
            disabled={!isActive}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded-xl"
          >
            ⚡ قطع آنی دستی (Barge-in)
          </Button>

          <Button
            onClick={() => setIsMuted(!isMuted)}
            disabled={!isActive}
            className={`${isMuted ? 'bg-amber-600/40 text-amber-200 border-amber-500' : 'bg-zinc-800 text-zinc-300 border-zinc-700'} border rounded-xl`}
          >
            {isMuted ? '🔇 میکروفون قطع است' : '🎙️ میکروفون فعال'}
          </Button>

          <Button
            onClick={handleExportTranscript}
            variant="outline"
            className="border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800 rounded-xl"
          >
            📝 متن مکالمه (Transcript)
          </Button>
        </div>

        {/* Transcript Area */}
        {transcript && (
          <div className="p-4 bg-zinc-900/80 rounded-xl border border-zinc-800 text-sm text-zinc-300 font-sans leading-relaxed whitespace-pre-wrap">
            {transcript}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
