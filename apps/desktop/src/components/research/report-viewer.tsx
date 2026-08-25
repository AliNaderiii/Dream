/**
 * Report viewer — renders the Markdown report with sanitized HTML.
 *
 * Security: ALL interpolated text is escaped via escapeHtml. Raw HTML tags
 * are stripped from the source first. No unsanitized interpolation.
 *
 * After COMPLETE, uses research.get → report.markdown_path. In echo mode,
 * serves markdown text directly. Against the sidecar, calls research.export.
 */

import { Download, FileJson, FileText, Image as ImageIcon, Scale } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { researchExport, redactSecrets } from '@/lib/bridge/research';
import { echoGetMarkdown } from '@/lib/bridge/echo-research';
import { useBridge } from '@/lib/bridge/hooks';
import type { Finding } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

import { FigureGallery } from './figure-gallery';
import { EvidenceIntegrity } from './evidence-integrity';

type ReportView = 'report' | 'figures' | 'integrity';

// --------------------------------------------------------------------------- //
// Sanitized Markdown renderer — ALL text is escaped
// --------------------------------------------------------------------------- //

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Strip raw HTML tags from source, then render markdown safely. */
function stripHtmlTags(text: string): string {
  return text.replace(/<[^>]*>/g, '');
}

function renderMarkdown(md: string): string {
  // Step 1: redact secrets
  let text = redactSecrets(md);
  // Step 2: strip ALL raw HTML tags (prevents <script>, <img onerror>, etc.)
  text = stripHtmlTags(text);

  let html = text;

  // Code blocks (fenced) — escape the code content
  html = html.replace(
    /```(\w+)?\n([\s\S]*?)```/g,
    (_, lang: string | undefined, code: string) =>
      `<pre class="overflow-x-auto rounded-lg bg-surface-2 p-3 my-3"><code class="font-mono text-micro${lang ? ` language-${escapeHtml(lang)}` : ''}">${escapeHtml(code.trim())}</code></pre>`,
  );

  // Tables — escape every cell
  html = html.replace(
    /^\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)*)/gm,
    (_, headerRow: string, bodyRows: string) => {
      const headers = headerRow
        .split('|')
        .map((c: string) => escapeHtml(c.trim()))
        .filter(Boolean);
      const headerHtml = headers
        .map(
          (h: string) =>
            `<th class="border-b border-border-default px-3 py-2 text-start text-caption font-semibold">${h}</th>`,
        )
        .join('');
      const rows = bodyRows
        .trim()
        .split('\n')
        .map((row: string) => {
          const cells = row
            .split('|')
            .map((c: string) => escapeHtml(c.trim()))
            .filter(Boolean);
          return `<tr>${cells.map((c: string) => `<td class="border-b border-border-default px-3 py-1.5 text-caption">${c}</td>`).join('')}</tr>`;
        })
        .join('');
      return `<div class="my-3 overflow-x-auto"><table class="w-full border-collapse rounded-lg border border-border-default"><thead><tr>${headerHtml}</tr></thead><tbody>${rows}</tbody></table></div>`;
    },
  );

  // Headings — escape the heading text
  html = html.replace(
    /^### (.+)$/gm,
    (_, text: string) => `<h3 class="text-h3 font-bold mt-6 mb-2">${escapeHtml(text)}</h3>`,
  );
  html = html.replace(
    /^## (.+)$/gm,
    (_, text: string) => `<h2 class="text-h2 font-bold mt-8 mb-3">${escapeHtml(text)}</h2>`,
  );
  html = html.replace(
    /^# (.+)$/gm,
    (_, text: string) => `<h1 class="text-h1 font-bold mt-6 mb-4">${escapeHtml(text)}</h1>`,
  );

  // Bold — escape the bold text
  html = html.replace(
    /\*\*(.+?)\*\*/g,
    (_, text: string) => `<strong>${escapeHtml(text)}</strong>`,
  );

  // Italic — escape the italic text
  html = html.replace(/\*(.+?)\*/g, (_, text: string) => `<em>${escapeHtml(text)}</em>`);

  // Inline code — escape the code
  html = html.replace(
    /`([^`]+)`/g,
    (_, text: string) =>
      `<code class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-micro">${escapeHtml(text)}</code>`,
  );

  // Ordered lists — escape the item text
  html = html.replace(
    /^(\d+)\. (.+)$/gm,
    (_, _num: string, text: string) =>
      `<li class="ms-4 list-decimal text-caption">${escapeHtml(text)}</li>`,
  );

  // Unordered lists — escape the item text
  html = html.replace(
    /^- (.+)$/gm,
    (_, text: string) => `<li class="ms-4 list-disc text-caption">${escapeHtml(text)}</li>`,
  );

  // Paragraphs — escape remaining lines
  html = html.replace(
    /^(?!<[a-z])((?!^\s*$).+)$/gm,
    (_, text: string) => `<p class="text-caption leading-relaxed my-1">${escapeHtml(text)}</p>`,
  );

  return html;
}

function ExportBar({ sessionId, isEcho }: { sessionId: string; isEcho: boolean }) {
  const { t } = useTranslation('research');
  const { client } = useBridge();
  const [busy, setBusy] = useState(false);

  const handleExport = (format: string) => {
    if (format === 'markdown' && isEcho) {
      const md = echoGetMarkdown();
      const blob = new Blob([md], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'research-report.md';
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    if (format === 'provenance' && isEcho) {
      // Generate a simple provenance JSON from echo data
      const provenance = { session_id: sessionId, generated_at: new Date().toISOString() };
      const blob = new Blob([JSON.stringify(provenance, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'provenance.json';
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    // For PDF/ZIP or non-echo: call research.export
    if (!isEcho) {
      setBusy(true);
      researchExport(client, sessionId)
        .then(() => {
          // Export succeeded — the sidecar wrote the files
        })
        .catch(() => {})
        .finally(() => setBusy(false));
    }
  };

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-lg border border-border-default bg-surface p-3"
      role="toolbar"
      aria-label={t('report.exportBar')}
    >
      <Button variant="ghost" size="sm" onClick={() => handleExport('markdown')}>
        <FileText aria-hidden />
        {t('report.exportMarkdown')}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handleExport('pdf')}
        disabled={isEcho}
        title={isEcho ? t('report.pdfEchoOnly') : undefined}
      >
        <Download aria-hidden />
        {t('report.exportPdf')}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handleExport('zip')}
        disabled={isEcho}
        title={isEcho ? t('report.zipEchoOnly') : undefined}
      >
        <Download aria-hidden />
        {t('report.exportZip')}
      </Button>
      <Button variant="ghost" size="sm" onClick={() => handleExport('provenance')}>
        <FileJson aria-hidden />
        {t('report.exportProvenance')}
      </Button>
      {busy && <span className="text-micro text-fg-muted">{t('report.exporting')}</span>}
    </div>
  );
}

export function ReportViewer() {
  const { t } = useTranslation('research');
  const { client } = useBridge();
  const { activeRecord, setView } = useResearchStore();
  const [view, setReportView] = useState<ReportView>('report');

  const isEcho = client.transportKind === 'echo';
  const record = activeRecord;
  const report = record?.report;
  const sections = record?.plan.sections ?? [];
  const findings: Finding[] = sections.flatMap((s) => s.findings);
  const charts: string[] = sections.flatMap((s) => s.charts);

  if (!record) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-8">
        <p className="text-body text-fg-muted">{t('report.notAvailable')}</p>
        <Button variant="ghost" onClick={() => setView('list')}>
          {t('backToList')}
        </Button>
      </div>
    );
  }

  // Get markdown: echo mode uses the seeded text, sidecar uses the path
  const markdown = isEcho
    ? echoGetMarkdown()
    : `# ${record.topic}\n\nReport available at: ${report?.markdown_path ?? 'N/A'}`;

  return (
    <div className="flex flex-col gap-4 overflow-y-auto">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setView('list')}
          className="text-caption text-fg-muted hover:text-fg-primary"
        >
          ← {t('backToList')}
        </button>
        <h3 className="min-w-0 flex-1 truncate text-body font-semibold">{record.topic}</h3>
      </div>

      {/* View tabs */}
      <div className="flex gap-1 rounded-lg bg-surface-2 p-1" role="tablist">
        {[
          { id: 'report' as const, label: t('report.view'), icon: FileText },
          { id: 'figures' as const, label: t('report.figures'), icon: ImageIcon },
          { id: 'integrity' as const, label: t('report.integrity'), icon: Scale },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={view === tab.id}
            onClick={() => setReportView(tab.id)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-caption font-semibold transition-colors',
              view === tab.id
                ? 'bg-surface text-fg-primary shadow-sm'
                : 'text-fg-muted hover:text-fg-secondary',
            )}
          >
            <tab.icon className="size-3.5" aria-hidden />
            {tab.label}
          </button>
        ))}
      </div>

      <ExportBar sessionId={record.session_id} isEcho={isEcho} />

      {view === 'report' && (
        <article className="prose-research flex flex-col gap-2">
          <div
            dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }}
            className="flex flex-col"
          />
        </article>
      )}

      {view === 'figures' && <FigureGallery charts={charts} sections={sections} />}
      {view === 'integrity' && <EvidenceIntegrity findings={findings} />}
    </div>
  );
}
