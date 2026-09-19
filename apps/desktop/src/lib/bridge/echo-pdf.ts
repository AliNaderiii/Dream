/**
 * Echo runtime for the PDF report bridge (`pdf.*`) — honest deterministic
 * demo results for the browser preview, where no Python sidecar runs.
 */

import type { PdfExportResult } from './pdf';

/** Deterministic demo of `pdf.export_report` for the echo transport. */
export function echoPdfExportReport(outputPath: string): PdfExportResult {
  return {
    success: true,
    demo: true,
    file_path: outputPath,
    pages: 1,
    size_bytes: 0,
    note: 'Browser preview — the Persian PDF engine (fpdf2 + Vazirmatn) runs in the Python core (desktop app).',
  };
}
