/**
 * PDF export row (v4.6) — shared by the Business Data and Vision studios.
 *
 * Two honest export paths:
 * 1. «چاپ / ذخیره PDF» — renders a print-safe A4 RTL document and opens the
 *    native print dialog (Save as PDF works in browser preview and desktop).
 * 2. «تولید فایل PDF» — calls the `pdf.export_report` bridge: in the desktop
 *    app the Python core (fpdf2 + HarfBuzz + Vazirmatn) writes a real PDF
 *    file; in the browser preview the result is a clearly-flagged demo.
 */

import { useState } from 'react';
import { FileDown, Printer } from 'lucide-react';

import type { BridgeClient } from '@/lib/bridge/client';
import { pdfExportReport } from '@/lib/bridge/pdf';
import type { PdfExportResult } from '@/lib/bridge/pdf';
import { printReport } from '@/lib/reporting/print';
import type { ReportContent } from '@/lib/reporting/print';

export function PdfExportRow({
  client,
  buildReport,
  defaultFileName,
}: {
  client: BridgeClient;
  buildReport: () => ReportContent;
  defaultFileName: string;
}) {
  const [outputPath, setOutputPath] = useState(`${defaultFileName}.pdf`);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PdfExportResult | null>(null);

  const handlePrint = () => {
    if (running) return;
    setResult(null);
    printReport(buildReport());
  };

  const handleGenerateFile = () => {
    const path = outputPath.trim();
    if (!path || running) return;
    setRunning(true);
    setResult(null);
    void pdfExportReport(client, buildReport(), path)
      .then((res) => setResult(res))
      .catch((reason) =>
        setResult({
          success: false,
          error: reason instanceof Error ? reason.message : String(reason),
        }),
      )
      .finally(() => setRunning(false));
  };

  return (
    <div className="rounded-xl border border-white/[0.08] bg-zinc-950/40 p-3.5" dir="rtl">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={handlePrint}
          disabled={running}
          className="flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-[11px] font-bold text-emerald-200 transition-all hover:bg-emerald-500/20 disabled:opacity-40"
        >
          <Printer className="size-3.5" aria-hidden="true" />
          چاپ / ذخیره PDF
        </button>
        <input
          value={outputPath}
          onChange={(e) => setOutputPath(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleGenerateFile();
          }}
          placeholder="C:\Users\alina\Documents\dream-report.pdf — مسیر کامل فایل"
          className="min-w-44 flex-1 rounded-lg border border-white/10 bg-zinc-900 px-2.5 py-1.5 font-mono text-[11px] text-zinc-300 placeholder-zinc-600 focus:outline-none"
          dir="ltr"
        />
        <button
          onClick={handleGenerateFile}
          disabled={!outputPath.trim().endsWith('.pdf') || running}
          className="flex items-center gap-1.5 rounded-lg border border-fuchsia-500/40 bg-fuchsia-500/10 px-3 py-1.5 text-[11px] font-bold text-fuchsia-200 transition-all hover:bg-fuchsia-500/20 disabled:opacity-40"
        >
          <FileDown className="size-3.5" aria-hidden="true" />
          {running ? 'در حال تولید…' : 'تولید فایل PDF'}
        </button>
      </div>
      {result && (
        <p
          className={`mt-2 font-mono text-[10px] ${
            result.success ? 'text-emerald-300' : 'text-rose-300'
          }`}
          dir={result.success ? 'rtl' : 'ltr'}
        >
          {result.success
            ? result.demo
              ? '● DEMO · موتور PDF (fpdf2 + Vazirmatn) در هسته پایتون دسکتاپ اجرا می‌شود — در پیش‌نمایش مرورگر فایل واقعی ساخته نمی‌شود'
              : `● PDF ساخته شد · ${result.pages ?? 1} صفحه · ${(result.file_path ?? '').slice(-60)}`
            : `⚠ ${result.error ?? 'تولید PDF ناموفق بود.'}`}
        </p>
      )}
    </div>
  );
}
