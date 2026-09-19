/**
 * Print-safe Persian report rendering (v4.6).
 *
 * The browser/WebView text engine shapes Persian perfectly, so the universal
 * export path renders the report as a standalone print document (A4, RTL,
 * Vazirmatn/system font stack) inside a hidden iframe and opens the native
 * print dialog — where "Save as PDF" produces a pixel-perfect Persian PDF
 * with zero dependencies.
 */

/** One report section: heading + paragraphs and/or KPI grid and/or a table. */
export interface ReportSection {
  heading: string;
  paragraphs?: string[];
  kpis?: Array<{ label: string; value: string }>;
  table?: { columns: string[]; rows: string[][] };
}

/** Full report content shared by the print path and the PDF bridge path. */
export interface ReportContent {
  title: string;
  subtitle?: string;
  sections: ReportSection[];
}

/** Escape a string for safe embedding inside the print document. */
export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Build the complete standalone print document (inline CSS, no network). */
export function buildPrintHtml(report: ReportContent): string {
  const esc = escapeHtml;
  const sections = (report.sections ?? [])
    .map((section) => {
      const parts = [`<h2>${esc(section.heading)}</h2>`];
      for (const paragraph of section.paragraphs ?? []) {
        if (paragraph.trim()) parts.push(`<p>${esc(paragraph)}</p>`);
      }
      const kpis = section.kpis ?? [];
      if (kpis.length > 0) {
        parts.push(
          '<div class="kpis">' +
            kpis
              .map(
                (kpi) =>
                  `<div class="kpi"><span class="kpi-label">${esc(kpi.label)}</span>` +
                  `<span class="kpi-value">${esc(kpi.value)}</span></div>`,
              )
              .join('') +
            '</div>',
        );
      }
      if (section.table && section.table.columns.length > 0) {
        const head = section.table.columns.map((column) => `<th>${esc(column)}</th>`).join('');
        const body = (section.table.rows ?? [])
          .map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join('')}</tr>`)
          .join('');
        parts.push(`<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
      }
      return `<section>${parts.join('')}</section>`;
    })
    .join('');

  return `<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>${esc(report.title)}</title>
<style>
  @page { size: A4; margin: 16mm 14mm; }
  * { box-sizing: border-box; }
  body {
    font-family: 'Vazirmatn', 'Segoe UI', Tahoma, 'Iranian Sans', sans-serif;
    color: #111; background: #fff; margin: 0; font-size: 11.5pt; line-height: 1.9;
  }
  h1 { font-size: 19pt; text-align: center; margin: 0 0 4mm; }
  .subtitle { text-align: center; color: #555; font-size: 9.5pt; margin-bottom: 8mm; }
  h2 { font-size: 13.5pt; border-bottom: 0.6mm solid #333; padding-bottom: 1.5mm; margin: 7mm 0 3mm; }
  p { margin: 0 0 3mm; text-align: justify; }
  section { page-break-inside: avoid; }
  .kpis { display: flex; flex-wrap: wrap; gap: 3mm; margin: 2mm 0 4mm; }
  .kpi { border: 0.3mm solid #999; border-radius: 2mm; padding: 2mm 4mm; min-width: 34mm; }
  .kpi-label { display: block; color: #555; font-size: 8.5pt; }
  .kpi-value { display: block; font-size: 12.5pt; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 10pt; }
  th, td { border: 0.3mm solid #888; padding: 1.6mm 2.4mm; text-align: right; }
  th { background: #f0f0f0; }
  tbody tr:nth-child(even) { background: #fafafa; }
  tfoot, .print-only { display: block; }
  .footer { margin-top: 10mm; border-top: 0.3mm solid #999; padding-top: 2mm;
            color: #666; font-size: 8.5pt; text-align: center; }
  @media print { .no-print { display: none; } }
</style>
</head>
<body>
<h1>${esc(report.title)}</h1>
${report.subtitle ? `<div class="subtitle">${esc(report.subtitle)}</div>` : ''}
${sections}
<div class="footer">این گزارش توسط دستیار دریم تولید شده است · Dream Core Report Engine</div>
</body>
</html>`;
}

/**
 * Render the report into a hidden iframe and open the print dialog.
 * In the dialog, "Save as PDF / ذخیره به‌صورت PDF" writes a real PDF file.
 * Returns true when the print frame was launched.
 */
export function printReport(report: ReportContent): boolean {
  if (typeof document === 'undefined') return false;
  const frame = document.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  frame.title = 'dream-report-print';
  frame.style.position = 'fixed';
  frame.style.inset = 'auto 0 0 auto';
  frame.style.width = '0';
  frame.style.height = '0';
  frame.style.border = '0';
  frame.srcdoc = buildPrintHtml(report);
  frame.addEventListener('load', () => {
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } finally {
      // Keep the frame alive while the dialog is open; clean up afterwards.
      window.setTimeout(() => frame.remove(), 120_000);
    }
  });
  document.body.appendChild(frame);
  return true;
}
