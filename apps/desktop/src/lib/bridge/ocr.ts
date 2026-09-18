/**
 * Document OCR bridge client — `ocr.extract` / `ocr.extract_invoice`.
 *
 * In Tauri these call the real Persian & multilingual OCR engine in the
 * Python core (text, blocks, tables, invoice key-value fields). Under the
 * echo transport (browser preview / tests) they return a deterministic,
 * clearly-flagged demo result instead.
 */

import type { BridgeClient } from './client';
import { echoOcrExtract } from './echo-ocr';

/** One recognized text block with spatial/directional metadata. */
export interface OcrBlockDto {
  text: string;
  confidence: number;
  direction?: string;
  line_number?: number;
  bbox?: { x: number; y: number; width: number; height: number };
}

/** Result shape of `ocr.extract` / `ocr.extract_invoice` (snake_case from core). */
export interface OcrExtractResult {
  success: boolean;
  error?: string;
  /** Present only on echo-transport demo results. */
  demo?: boolean;
  file_path?: string;
  document_type?: string;
  raw_text?: string;
  cleaned_text?: string;
  language?: string;
  confidence?: number;
  blocks_count?: number;
  blocks?: OcrBlockDto[];
  extracted_fields?: Record<string, unknown>;
  tables?: string[][][];
  metadata?: Record<string, unknown>;
}

/** Extract text and structured fields from a document or image file. */
export function ocrExtract(
  client: BridgeClient,
  filePath: string,
  documentType = 'general',
): Promise<OcrExtractResult> {
  if (!filePath.trim()) {
    return Promise.reject(new Error('file path must not be empty'));
  }
  if (client.transportKind === 'echo') {
    return Promise.resolve(echoOcrExtract(filePath, documentType));
  }
  return client.call<OcrExtractResult>('ocr.extract', {
    file_path: filePath,
    document_type: documentType,
  });
}

/** Extract invoice fields (total amount, date, tax, IBAN) from a file. */
export function ocrExtractInvoice(
  client: BridgeClient,
  filePath: string,
): Promise<OcrExtractResult> {
  if (!filePath.trim()) {
    return Promise.reject(new Error('file path must not be empty'));
  }
  if (client.transportKind === 'echo') {
    return Promise.resolve(echoOcrExtract(filePath, 'invoice'));
  }
  return client.call<OcrExtractResult>('ocr.extract_invoice', { file_path: filePath });
}
