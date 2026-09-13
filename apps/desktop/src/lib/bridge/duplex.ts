/** Typed client wrappers for duplex.* JSON-RPC methods. */

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
  return echoOr(client, () => echo.echoDuplexStart(sessionId), 'duplex.start', {
    session_id: sessionId,
    sample_rate: sampleRate,
    vad_threshold: vadThreshold,
  });
}

export function duplexPushMicChunk(
  client: BridgeClient,
  chunkB64: string,
): Promise<DuplexMicResult> {
  return echoOr(client, () => echo.echoDuplexPushMicChunk(chunkB64), 'duplex.push_mic_chunk', {
    chunk_b64: chunkB64,
  });
}

export function duplexGetVisualizer(client: BridgeClient): Promise<DuplexVisualizerFrame> {
  return echoOr(client, () => echo.echoDuplexGetVisualizer(), 'duplex.get_visualizer', {});
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
  return echoOr(client, () => echo.echoDuplexGetMetrics(sessionId), 'duplex.get_metrics', {
    session_id: sessionId,
  });
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
  return echoOr(client, () => echo.echoDuplexStop(sessionId), 'duplex.stop', {
    session_id: sessionId,
  });
}
