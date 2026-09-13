#!/usr/bin/env python3
"""
Dream Assistant — Desktop Real-Time Voice Bridge & Tauri UI Upgrade Script.

This script automatically creates and updates:
1. dream/bridge/methods_duplex.py (Desktop Duplex JSON-RPC bridge methods)
2. apps/desktop/src/lib/bridge/duplex.ts (TypeScript duplex bridge client)
3. apps/desktop/src/lib/bridge/echo-duplex.ts (Offline echo duplex fallback)
4. apps/desktop/src/components/live/voice-studio.tsx (Interactive live visualizer & audio controls)
5. apps/desktop/src/routes/live.tsx (Live route integrating VoiceStudio)
6. tests/test_desktop_duplex_voice_bridge.py (Duplex bridge test suite)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

FILES = {
    "dream/bridge/methods_duplex.py": '''"""``duplex.*`` RPC surface, registered through the P0 extension seam.

This module is discovered automatically by :mod:`dream.bridge.extensions`.
It exposes the real-time audio duplex voice bridge and visualizer state to
the desktop UI and JSON-RPC clients:

===========================  =================================================
``duplex.start``             start or reconfigure a live desktop duplex voice session
``duplex.push_mic_chunk``    ingest a microphone PCM audio chunk and get visualizer metrics
``duplex.get_visualizer``    poll the latest 16-peak waveform and 8-band spectrum metrics
``duplex.inject_interruption`` force a manual barge-in cut-off on speech output
``duplex.get_metrics``       retrieve turn metrics, VAD confidence, and latencies
``duplex.export_transcript`` export the duplex conversation history as text/markdown
``duplex.stop``              gracefully stop and terminate the voice session
===========================  =================================================
"""

from __future__ import annotations

import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.duplex.desktop_bridge import get_desktop_voice_bridge
from dream.duplex.engine import get_duplex_engine
from dream.duplex.types import DuplexConfig

logger = logging.getLogger("dream.bridge.duplex")

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


async def duplex_start(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Start or configure a live desktop duplex voice session."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    sample_rate = int(data.get("sample_rate") or 16000)
    vad_threshold = float(data.get("vad_threshold") or data.get("vad_energy_threshold") or 0.015)

    if sample_rate not in (8000, 16000, 24000, 48000):
        raise invalid_params("sample_rate must be 8000, 16000, 24000, or 48000 Hz")

    bridge = get_desktop_voice_bridge()
    bridge.session_id = session_id
    bridge.sample_rate = sample_rate

    cfg = DuplexConfig(
        session_id=session_id,
        sample_rate=sample_rate,
        vad_energy_threshold=vad_threshold,
    )
    res = await bridge.start(cfg)
    return {
        "status": "connected",
        "session_id": session_id,
        "sample_rate": sample_rate,
        "frame_size_ms": 20,
        "details": res,
    }


async def duplex_push_mic_chunk(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Ingest base64 PCM audio chunk from microphone and return visualizer metrics."""
    data = _params(params, kwargs)
    base64_pcm = str(data.get("chunk_b64") or data.get("base64_pcm") or "").strip()

    bridge = get_desktop_voice_bridge()
    try:
        result = await bridge.process_incoming_mic_chunk(base64_pcm)
        return result
    except Exception as exc:
        raise invalid_params(f"Failed to process mic audio chunk: {exc}") from exc


def duplex_get_visualizer(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Return the latest waveform peaks, frequency spectrum bins, and speaking state."""
    bridge = get_desktop_voice_bridge()
    return bridge.get_latest_visualizer()


async def duplex_inject_interruption(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Force manual barge-in interruption on active speech playback."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    engine = get_duplex_engine()
    session = engine.get_or_create_session(session_id)
    await session.interrupt_manually(reason="desktop_ui_barge_in")
    return {
        "status": "interrupted",
        "session_id": session_id,
        "interrupted": True,
    }


def duplex_get_metrics(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Retrieve latency, turn counts, and audio metrics for active session."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    engine = get_duplex_engine()
    session = engine.get_or_create_session(session_id)
    status = session.get_status()
    return {
        "session_id": session_id,
        "status": "ok",
        "stats": status.get("metrics", {}),
    }


def duplex_export_transcript(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Export the conversation transcript of the duplex session."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    format_type = str(data.get("format") or "markdown").lower()
    engine = get_duplex_engine()
    session = engine.get_or_create_session(session_id)
    turns = session.get_transcript()

    if format_type == "json":
        import json
        transcript_text = json.dumps(turns, ensure_ascii=False, indent=2)
    else:
        lines = ["# گزارش مکالمه صوتی زنده (Desktop Live Voice Transcript)\\n"]
        for t in turns:
            speaker = "کاربر" if t.get("speaker") == "user" else "دریم (Dream)"
            lines.append(f"**{speaker}:** {t.get('text', '')}\\n")
        transcript_text = "\\n".join(lines) if turns else "هنوز مکالمه‌ای ثبت نشده است."

    return {
        "session_id": session_id,
        "format": format_type,
        "transcript": transcript_text,
    }


async def duplex_stop(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Gracefully terminate desktop voice session."""
    bridge = get_desktop_voice_bridge()
    return await bridge.stop()


HANDLERS = {
    "duplex.start": duplex_start,
    "duplex.push_mic_chunk": duplex_push_mic_chunk,
    "duplex.get_visualizer": duplex_get_visualizer,
    "duplex.inject_interruption": duplex_inject_interruption,
    "duplex.get_metrics": duplex_get_metrics,
    "duplex.export_transcript": duplex_export_transcript,
    "duplex.stop": duplex_stop,
}
''',

    "apps/desktop/src/lib/bridge/duplex.ts": '''/** Typed client wrappers for duplex.* JSON-RPC methods. */

import type { BridgeClient } from './client';
import * as echo from './echo-duplex';

export interface DuplexVisualizerFrame {
  timestamp_ms: number;
  rms_volume: number; // 0.0 to 1.0
  waveform_peaks: number[]; // 16 normalized values
  frequency_bins: number[]; // 8 spectrum bands
  is_speaking: boolean;
  is_interrupted?: boolean;
}

export interface DuplexStartResult {
  status: string;
  session_id: string;
  sample_rate: number;
  frame_size_ms: number;
  details?: Record<string, unknown>;
}

export interface DuplexMicResult {
  status: string;
  duplex_state: string;
  interrupted: boolean;
  visualizer: DuplexVisualizerFrame;
}

export interface DuplexMetricsResult {
  session_id: string;
  status: string;
  stats: {
    user_turns?: number;
    assistant_turns?: number;
    interruption_count?: number;
    total_duration_sec?: number;
    estimated_latency_ms?: number;
    [key: string]: unknown;
  };
}

export interface DuplexTranscriptResult {
  session_id: string;
  format: string;
  transcript: string;
}

function echoOr<T>(
  client: BridgeClient,
  local: () => T,
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  if (client.transportKind === 'echo') {
    try {
      return Promise.resolve(local());
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  }
  return client.call<T>(method, params);
}

export function duplexStart(
  client: BridgeClient,
  sessionId = 'desktop-live-voice',
  sampleRate = 16000,
  vadThreshold = 0.5,
): Promise<DuplexStartResult> {
  return echoOr(
    client,
    () => echo.echoDuplexStart(sessionId),
    'duplex.start',
    { session_id: sessionId, sample_rate: sampleRate, vad_threshold: vadThreshold },
  );
}

export function duplexPushMicChunk(
  client: BridgeClient,
  chunkB64: string,
): Promise<DuplexMicResult> {
  return echoOr(
    client,
    () => echo.echoDuplexPushMicChunk(chunkB64),
    'duplex.push_mic_chunk',
    { chunk_b64: chunkB64 },
  );
}

export function duplexGetVisualizer(
  client: BridgeClient,
): Promise<DuplexVisualizerFrame> {
  return echoOr(
    client,
    () => echo.echoDuplexGetVisualizer(),
    'duplex.get_visualizer',
    {},
  );
}

export function duplexInjectInterruption(
  client: BridgeClient,
  sessionId = 'desktop-live-voice',
): Promise<{ status: string; session_id: string; interrupted: boolean }> {
  return echoOr(
    client,
    () => echo.echoDuplexInjectInterruption(sessionId),
    'duplex.inject_interruption',
    { session_id: sessionId },
  );
}

export function duplexGetMetrics(
  client: BridgeClient,
  sessionId = 'desktop-live-voice',
): Promise<DuplexMetricsResult> {
  return echoOr(
    client,
    () => echo.echoDuplexGetMetrics(sessionId),
    'duplex.get_metrics',
    { session_id: sessionId },
  );
}

export function duplexExportTranscript(
  client: BridgeClient,
  sessionId = 'desktop-live-voice',
  format = 'markdown',
): Promise<DuplexTranscriptResult> {
  return echoOr(
    client,
    () => echo.echoDuplexExportTranscript(sessionId, format),
    'duplex.export_transcript',
    { session_id: sessionId, format },
  );
}

export function duplexStop(
  client: BridgeClient,
  sessionId = 'desktop-live-voice',
): Promise<{ status: string; session_id: string }> {
  return echoOr(
    client,
    () => echo.echoDuplexStop(sessionId),
    'duplex.stop',
    { session_id: sessionId },
  );
}
''',

    "apps/desktop/src/lib/bridge/echo-duplex.ts": '''/** Fallback offline mock implementations for duplex.* methods. */

import type {
  DuplexMetricsResult,
  DuplexMicResult,
  DuplexStartResult,
  DuplexTranscriptResult,
  DuplexVisualizerFrame,
} from './duplex';

let mockIsSpeaking = false;
let mockRMS = 0.0;

export function echoDuplexStart(sessionId = 'desktop-live-voice'): DuplexStartResult {
  mockIsSpeaking = false;
  mockRMS = 0.05;
  return {
    status: 'connected',
    session_id: sessionId,
    sample_rate: 16000,
    frame_size_ms: 20,
    details: { status: 'connected', session_id: sessionId },
  };
}

export function echoDuplexPushMicChunk(chunkB64 = ''): DuplexMicResult {
  mockIsSpeaking = chunkB64.length > 50;
  mockRMS = mockIsSpeaking ? 0.45 : 0.02;

  const peaks = Array.from({ length: 16 }, (_, i) =>
    mockIsSpeaking ? Math.sin(i * 0.4) * 0.7 : 0.05,
  );
  const bins = Array.from({ length: 8 }, (_, i) =>
    mockIsSpeaking ? Math.min(1.0, 0.2 + (i * 0.1)) : 0.02,
  );

  return {
    status: 'ok',
    duplex_state: mockIsSpeaking ? 'speaking' : 'listening',
    interrupted: false,
    visualizer: {
      timestamp_ms: Date.now(),
      rms_volume: mockRMS,
      waveform_peaks: peaks,
      frequency_bins: bins,
      is_speaking: mockIsSpeaking,
      is_interrupted: false,
    },
  };
}

export function echoDuplexGetVisualizer(): DuplexVisualizerFrame {
  const peaks = Array.from({ length: 16 }, (_, i) =>
    mockIsSpeaking ? Math.sin(Date.now() / 200 + i * 0.5) * 0.8 : 0.02,
  );
  const bins = Array.from({ length: 8 }, (_, i) =>
    mockIsSpeaking ? 0.3 + 0.5 * Math.abs(Math.sin(Date.now() / 300 + i)) : 0.01,
  );

  return {
    timestamp_ms: Date.now(),
    rms_volume: mockRMS,
    waveform_peaks: peaks,
    frequency_bins: bins,
    is_speaking: mockIsSpeaking,
    is_interrupted: false,
  };
}

export function echoDuplexInjectInterruption(sessionId = 'desktop-live-voice') {
  mockIsSpeaking = false;
  mockRMS = 0.0;
  return {
    status: 'interrupted',
    session_id: sessionId,
    interrupted: true,
  };
}

export function echoDuplexGetMetrics(sessionId = 'desktop-live-voice'): DuplexMetricsResult {
  return {
    session_id: sessionId,
    status: 'ok',
    stats: {
      user_turns: 4,
      assistant_turns: 3,
      interruption_count: 1,
      total_duration_sec: 18.5,
      estimated_latency_ms: 185,
    },
  };
}

export function echoDuplexExportTranscript(
  sessionId = 'desktop-live-voice',
  format = 'markdown',
): DuplexTranscriptResult {
  return {
    session_id: sessionId,
    format,
    transcript:
      '# گزارش مکالمه صوتی زنده (Desktop Voice Transcript)\\n\\n' +
      '**کاربر:** سلام دریم، آخرین وضعیت پروژه چیست؟\\n\\n' +
      '**دریم:** سلام علی جان! تمام تست‌های CI با موفقیت پاس شدند و سیستم هوش صوتی دوبلکس آماده است.',
  };
}

export function echoDuplexStop(sessionId = 'desktop-live-voice') {
  mockIsSpeaking = false;
  mockRMS = 0.0;
  return {
    status: 'disconnected',
    session_id: sessionId,
  };
}
''',

    "apps/desktop/src/components/live/voice-studio.tsx": '''import { useEffect, useRef, useState } from 'react';

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
''',

    "apps/desktop/src/routes/live.tsx": '''import { useEffect, useState } from 'react';

import { VoiceStudio } from '@/components/live/voice-studio';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input, Textarea } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import { liveloopArmDraft, liveloopRoleTurn, liveloopRouteSnapshot } from '@/lib/bridge/liveloop';
import { useTranslation } from '@/lib/i18n';
import { useProviderStore } from '@/stores/use-provider-store';

export default function LiveRoute() {
  const { t } = useTranslation('live');
  const { client } = useBridge();
  const bar = useProviderStore((s) => s.providers.find((p) => p.id === s.activeProviderId));
  const [note, setNote] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [spaceId, setSpaceId] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [draftId, setDraftId] = useState('');
  const [armed, setArmed] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void liveloopRouteSnapshot(client, bar?.name ?? 'echo', 'Earth Runtime', 'qwen3.6-35b')
      .then((shot) => {
        if (cancelled) return;
        setNote(shot.note_en);
        setMismatch(shot.mismatch);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client, bar?.name]);

  const onAsk = async () => {
    setError(null);
    try {
      const result = await liveloopRoleTurn(client, spaceId, 'secretary', question, false);
      setAnswer(result.answer);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onArm = async () => {
    setError(null);
    try {
      const result = await liveloopArmDraft(client, draftId, true);
      setArmed(result.schedule.schedule_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <main className="flex h-full flex-col gap-6 overflow-y-auto p-4" aria-labelledby="live-title">
      <header>
        <h1 id="live-title" className="text-h2 font-semibold">
          {t('title')}
        </h1>
        <p className="text-body text-fg-muted">{t('subtitle')}</p>
      </header>

      {/* Real-time Duplex Voice Studio & Waveform Visualizer */}
      <VoiceStudio />

      {error && (
        <p role="alert" className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('honestyTitle')}</h2>
          <CardDescription>{t('honestyHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Badge variant={mismatch ? 'warning' : 'success'}>
            {mismatch ? t('honestyHint') : t('honestyOk')}
          </Badge>
          {note && <p className="text-caption text-fg-muted">{note}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('roleTitle')}</h2>
          <CardDescription>{t('roleHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Input
            label={t('spaceId')}
            value={spaceId}
            onChange={(event) => setSpaceId(event.target.value)}
          />
          <Textarea
            label={t('question')}
            value={question}
            rows={3}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <Button onClick={() => void onAsk()} disabled={!spaceId.trim() || !question.trim()}>
            {t('ask')}
          </Button>
          {answer && (
            <p aria-live="polite" className="whitespace-pre-wrap text-body">
              {answer}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('armTitle')}</h2>
          <CardDescription>{t('armHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Input
            label={t('draftId')}
            value={draftId}
            onChange={(event) => setDraftId(event.target.value)}
          />
          <Button onClick={() => void onArm()} disabled={!draftId.trim()}>
            {t('arm')}
          </Button>
          {armed && (
            <p aria-live="polite" className="text-caption">
              {t('armedAs')} {armed}
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
''',

    "tests/test_desktop_duplex_voice_bridge.py": '''"""Tests for Desktop Real-Time Duplex Voice Bridge and JSON-RPC Methods."""

from __future__ import annotations

import asyncio
import base64
import struct

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_duplex import (
    duplex_export_transcript,
    duplex_get_metrics,
    duplex_get_visualizer,
    duplex_inject_interruption,
    duplex_push_mic_chunk,
    duplex_start,
    duplex_stop,
)


def test_duplex_bridge_extension_discovery():
    """Verify duplex.* methods are automatically registered in the Bridge Registry."""
    handlers = Registry.publish({})
    assert "duplex.start" in handlers
    assert "duplex.push_mic_chunk" in handlers
    assert "duplex.get_visualizer" in handlers
    assert "duplex.inject_interruption" in handlers
    assert "duplex.get_metrics" in handlers
    assert "duplex.export_transcript" in handlers
    assert "duplex.stop" in handlers


def test_duplex_start_valid_and_invalid_params():
    """Test starting a duplex session with valid and invalid sample rates."""
    async def _test():
        res = await duplex_start({"session_id": "test-voice-sess", "sample_rate": 16000})
        assert res["status"] == "connected"
        assert res["session_id"] == "test-voice-sess"
        assert res["sample_rate"] == 16000

        with pytest.raises(BridgeError):
            await duplex_start({"sample_rate": 12345})

        await duplex_stop()

    asyncio.run(_test())


def test_duplex_push_mic_chunk_and_visualizer_pipeline():
    """Test pushing audio chunks, computing visualizer metrics, and polling."""
    async def _test():
        await duplex_start({"session_id": "test-mic-stream", "sample_rate": 16000})

        pcm_samples = [1000] * 320
        pcm_bytes = struct.pack("<320h", *pcm_samples)
        b64_chunk = base64.b64encode(pcm_bytes).decode("utf-8")

        push_res = await duplex_push_mic_chunk({"chunk_b64": b64_chunk})
        assert push_res["status"] == "ok"
        assert "visualizer" in push_res

        v_frame = push_res["visualizer"]
        assert len(v_frame["waveform_peaks"]) == 16
        assert len(v_frame["frequency_bins"]) == 8
        assert v_frame["rms_volume"] > 0.0

        polled = duplex_get_visualizer()
        assert len(polled["waveform_peaks"]) == 16
        assert len(polled["frequency_bins"]) == 8

        await duplex_stop()

    asyncio.run(_test())


def test_duplex_inject_interruption_and_metrics():
    """Test barge-in interruption injection and metrics retrieval."""
    async def _test():
        await duplex_start({"session_id": "test-interruption"})

        intr_res = await duplex_inject_interruption({"session_id": "test-interruption"})
        assert intr_res["session_id"] == "test-interruption"
        assert "interrupted" in intr_res

        metrics_res = duplex_get_metrics({"session_id": "test-interruption"})
        assert metrics_res["status"] == "ok"
        assert "stats" in metrics_res

        await duplex_stop()

    asyncio.run(_test())


def test_duplex_export_transcript_lifecycle():
    """Test exporting the conversation transcript in markdown format."""
    async def _test():
        await duplex_start({"session_id": "test-transcript-session"})

        trans_res = duplex_export_transcript({
            "session_id": "test-transcript-session",
            "format": "markdown",
        })
        assert trans_res["session_id"] == "test-transcript-session"
        assert trans_res["format"] == "markdown"
        assert isinstance(trans_res["transcript"], str)

        await duplex_stop()

    asyncio.run(_test())
''',
}


def main() -> int:
    print("🚀 Applying Dream Desktop Voice Bridge & Tauri UI Upgrade...")
    for rel_path, content in FILES.items():
        target = REPO_ROOT / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [OK] Wrote {rel_path} ({len(content)} bytes)")

    print("\n✅ All 6 desktop & voice bridge files written successfully with standard UTF-8 (No BOM)!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
