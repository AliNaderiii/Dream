/**
 * Echo runtime for the speech-to-text bridge (`stt.transcribe`) — an honest
 * deterministic demo for the browser preview, where no Python sidecar (and
 * therefore no faster-whisper engine) runs.
 */

import type { SttTranscribeResult } from './stt';

/** Deterministic demo of `stt.transcribe` for the echo transport. */
export function echoSttTranscribe(
  filePath: string,
  language: 'fa' | 'en' | 'auto' = 'fa',
): SttTranscribeResult {
  // Accepted to mirror the real call signature; the demo never reads audio.
  void filePath;
  return {
    success: true,
    demo: true,
    available: false,
    engine: null,
    text: '',
    language,
    simulated: false,
    note: 'Browser preview — real transcription (faster-whisper) runs in the Python core (desktop app, install extra ".[stt]").',
  };
}
