/**
 * Persian PDF report bridge — `pdf.export_report`.
 *
 * In Tauri this renders a real PDF in the Python core (fpdf2 + HarfBuzz text
 * shaping + the bundled Vazirmatn font) and writes it to the given path.
 * Under the echo transport (browser preview / tests) it returns a
 * clearly-flagged demo result instead.
 */

import type { BridgeClient } from './client';
import { echoPdfExportReport } from './echo-pdf';

/** One report section (mirrors the Python report model). */
export interface PdfReportSection {
  heading: string;
  paragraphs?: string[];
  kpis?: Array<{ label: string; value: string }>;
  table?: { columns: string[]; rows: string[][] };
}

/** Full report payload for `pdf.export_report`. */
export interface PdfReport {
  title: string;
  subtitle?: string;
  sections: PdfReportSection[];
}

/** Result of `pdf.export_report` (snake_case fields from core). */
export interface PdfExportResult {
  success: boolean;
  error?: string;
  /** Present only on echo-transport demo results. */
  demo?: boolean;
  file_path?: string;
  pages?: number;
  size_bytes?: number;
  note?: string;
}

/** Render a report to a Persian PDF file at `outputPath` (must end in .pdf). */
export function pdfExportReport(
  client: BridgeClient,
  report: PdfReport,
  outputPath: string,
): Promise<PdfExportResult> {
  if (!outputPath.trim()) {
    return Promise.reject(new Error('output path must not be empty'));
  }
  if (!outputPath.toLowerCase().endsWith('.pdf')) {
    return Promise.reject(new Error('output path must end with .pdf'));
  }
  if (client.transportKind === 'echo') {
    return Promise.resolve(echoPdfExportReport(outputPath));
  }
  return client.call<PdfExportResult>('pdf.export_report', {
    report,
    output_path: outputPath,
  });
}
