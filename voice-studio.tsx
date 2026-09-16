import { useEffect, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
import { useBridge } from '@/lib/bridge/hooks';

const INITIAL_VISUALIZER: DuplexVisualizerFrame = {
  timestamp_ms: 0,
  rms_volume: 0.0,
  waveform_peaks: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  frequency_bins: [0, 0, 0, 0, 0, 0, 0, 0],
  is_speaking: false,
};

export function VoiceStudio() {
  const { client } = useBridge();

  const [isActive, setIsActive] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [duplexState, setDuplexState] = useState<
    'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted'
  >('idle');
  const vadThreshold = 0.5;
  const [visualizer, setVisualizer] = useState<DuplexVisualizerFrame>(INITIAL_VISUALIZER);
  const [latencyMs, setLatencyMs] = useState(140);
  const [transcript, setTranscript] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Polling loop for visualizer frames and state
  useEffect(() => {
    if (!isActive) {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      return;
    }

    pollTimerRef.current = setInterval(() => {
      void (async () => {
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
        } catch {
          // Fallback or ignore transient poll errors
        }
      })();
    }, 80);

    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [client, isActive, vadThreshold, duplexState]);

  const handleStartSession = async () => {
    setError(null);
    try {
      await duplexStart(client, 'desktop-live-voice', 16000, vadThreshold);
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
      setVisualizer(INITIAL_VISUALIZER);
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
    <Card className="w-full border-zinc-800 bg-zinc-950/80 text-zinc-100 shadow-2xl backdrop-blur-md">
      <CardHeader className="flex flex-row items-center justify-between border-b border-zinc-800/80 pb-4">
        <div>
          <CardTitle className="flex items-center gap-2 text-xl font-bold">
            🎙️ استودیوی صوتی دوبلکس زنده (Desktop Live Voice Studio)
          </CardTitle>
          <CardDescription className="mt-1 text-sm text-zinc-400">
            مکالمه صوتی هم‌زمان، تشخیص بلادرنگ گفتار با VAD v5 و قطع آنی (Zero-Latency Barge-in)
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Badge className={`border px-3 py-1 text-xs ${stateColors[duplexState]}`}>
            {stateLabelsFa[duplexState]}
          </Badge>
          <Badge className="border border-zinc-700 bg-zinc-800 text-xs text-zinc-300">
            {latencyMs}ms Latency
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        {error && (
          <div className="rounded-lg border border-rose-800 bg-rose-950/50 p-3 text-sm text-rose-300">
            ⚠️ {error}
          </div>
        )}

        {/* 3D/2D Dynamic Audio Waveform & Pulse Visualizer */}
        <div className="relative flex min-h-[220px] flex-col items-center justify-center overflow-hidden rounded-2xl border border-zinc-800/70 bg-zinc-900/60 p-8">
          {/* Glowing background pulse aura */}
          <div
            className="pointer-events-none absolute rounded-full opacity-40 blur-2xl transition-all duration-150"
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
          <div className="z-10 flex h-28 w-full max-w-md items-center justify-center gap-1.5">
            {visualizer.waveform_peaks.map((peak, idx) => {
              const heightPct = Math.max(
                8,
                Math.min(100, Math.abs(peak) * 100 + (isActive ? 12 : 4)),
              );
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
          <div className="z-10 mt-4 flex w-full max-w-xs items-center justify-center gap-3">
            {visualizer.frequency_bins.map((bin, idx) => (
              <div key={idx} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className="w-full rounded-t bg-indigo-500/80 transition-all duration-100"
                  style={{ height: `${Math.max(4, bin * 32)}px` }}
                />
                <span className="font-mono text-[9px] text-zinc-500">{idx + 1}k</span>
              </div>
            ))}
          </div>
        </div>

        {/* Studio Controls Panel */}
        <div className="grid grid-cols-1 gap-3 pt-2 md:grid-cols-4">
          {!isActive ? (
            <Button
              onClick={() => {
                void handleStartSession();
              }}
              className="rounded-xl bg-emerald-600 py-2.5 font-semibold text-white shadow-lg shadow-emerald-950 hover:bg-emerald-500"
            >
              📞 شروع مکالمه زنده
            </Button>
          ) : (
            <Button
              onClick={() => {
                void handleStopSession();
              }}
              variant="destructive"
              className="rounded-xl bg-rose-600 py-2.5 font-semibold text-white shadow-lg shadow-rose-950 hover:bg-rose-500"
            >
              🛑 قطع تماس صوتی
            </Button>
          )}

          <Button
            onClick={() => {
              void handleBargeIn();
            }}
            disabled={!isActive}
            className="rounded-xl border border-zinc-700 bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
          >
            ⚡ قطع آنی دستی (Barge-in)
          </Button>

          <Button
            onClick={() => setIsMuted(!isMuted)}
            disabled={!isActive}
            className={`${isMuted ? 'border-amber-500 bg-amber-600/40 text-amber-200' : 'border-zinc-700 bg-zinc-800 text-zinc-300'} rounded-xl border`}
          >
            {isMuted ? '🔇 میکروفون قطع است' : '🎙️ میکروفون فعال'}
          </Button>

          <Button
            onClick={() => {
              void handleExportTranscript();
            }}
            variant="secondary"
            className="rounded-xl border-zinc-700 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
          >
            📝 متن مکالمه (Transcript)
          </Button>
        </div>

        {/* Transcript Area */}
        {transcript && (
          <div className="whitespace-pre-wrap rounded-xl border border-zinc-800 bg-zinc-900/80 p-4 font-sans text-sm leading-relaxed text-zinc-300">
            {transcript}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
