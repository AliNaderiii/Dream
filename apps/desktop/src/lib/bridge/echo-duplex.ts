/** Fallback offline mock implementations for duplex.* methods. */

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
      '# گزارش مکالمه صوتی زنده (Desktop Voice Transcript)\n\n' +
      '**کاربر:** سلام دریم، آخرین وضعیت پروژه چیست؟\n\n' +
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
