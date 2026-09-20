/**
 * Speech-to-text bridge — `stt.transcribe`.
 *
 * In Tauri this runs the optional faster-whisper engine inside the Python
 * core (install extra: pip install ".[stt]"). When the engine is missing the
 * core answers honestly with `available: false` and an install hint. Under
 * the echo transport (browser preview / tests) the result is a clearly
 * flagged demo.
 */

import type { BridgeClient } from './client';
import { echoSttTranscribe } from './echo-stt';

/** Shape of `stt.transcribe` (snake_case fields from the Python core). */
export interface SttTranscribeResult {
  success: boolean;
  /** False when faster-whisper is not installed in the core. */
  available?: boolean;
  engine?: string | null;
  text?: string;
  language?: string;
  duration?: number;
  simulated?: boolean;
  error?: string;
  /** Present only on echo-transport demo results. */
  demo?: boolean;
  note?: string;
}

/** Transcribe one audio file (fa / en / auto). */
export function sttTranscribe(
  client: BridgeClient,
  filePath: string,
  language: 'fa' | 'en' | 'auto' = 'fa',
): Promise<SttTranscribeResult> {
  if (!filePath.trim()) {
    return Promise.reject(new Error('file path must not be empty'));
  }
  if (client.transportKind === 'echo') {
    return Promise.resolve(echoSttTranscribe(filePath, language));
  }
  return client.call<SttTranscribeResult>('stt.transcribe', {
    file_path: filePath,
    language,
  });
}
