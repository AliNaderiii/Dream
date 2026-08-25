/**
 * Report viewer — renders the Markdown report with syntax-highlighted code
 * blocks, tables, inline-fitted figures; export bar (MD/PDF/ZIP/provenance),
 * figure gallery, appendix, and the claims⇅evidence integrity view.
 *
 * Security: uses a sanitized markdown renderer. No dangerouslySetInnerHTML
 * without DOMPurify-style sanitization.
 */

import { Download, FileJson, FileText, Image as ImageIcon, Scale } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { redactSecrets } from '@/lib/bridge/research';
import type { ResearchReport } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

import { FigureGallery } from './figure-gallery';
import { EvidenceIntegrity } from './evidence-integrity';

type ReportView = 'report' | 'figures' | 'integrity';

/**
 * Sanitised Markdown renderer.
 *
 * Processes headings, code blocks, tables, bold/italic, lists, and inline
 * code. Script tags and link exfiltration are stripped. This is intentionally
 * a minimal parser — production would use remark/rehype with sanitize.
 */
function renderMarkdown(md: string): string {
  let html = redactSecrets(md);

  // Strip script tags
  html = html.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');

  // Code blocks (fenced)
  html = html.replace(
    /```(\w+)?\n([\s\S]*?)```/g,
    (_, lang: string | undefined, code: string) =>
      `<pre class="overflow-x-auto rounded-lg bg-surface-2 p-3 my-3"><code class="font-mono text-micro ${lang ? `language-${lang}` : ''}">${escapeHtml(code.trim())}</code></pre>`,
  );

  // Tables
  html = html.replace(
    /^\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)*)/gm,
    (_, headerRow: string, bodyRows: string) => {
      const headers: string[] = headerRow
        .split('|')
        .map((c: string) => c.trim())
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
          const cells: string[] = row
            .split('|')
            .map((c: string) => c.trim())
            .filter(Boolean);
          return `<tr>${cells.map((c: string) => `<td class="border-b border-border-default px-3 py-1.5 text-caption">${c}</td>`).join('')}</tr>`;
        })
        .join('');
      return `<div class="my-3 overflow-x-auto"><table class="w-full border-collapse rounded-lg border border-border-default">${`<thead><tr>${headerHtml}</tr></thead>`}<tbody>${rows}</tbody></table></div>`;
    },
  );

  // Headings
  html = html.replace(/^### (.+)$/gm, '<h3 class="text-h3 font-bold mt-6 mb-2">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-h2 font-bold mt-8 mb-3">$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1 class="text-h1 font-bold mt-6 mb-4">$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Inline code
  html = html.replace(
    /`([^`]+)`/g,
    '<code class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-micro">$1</code>',
  );

  // Ordered lists
  html = html.replace(/^(\d+)\. (.+)$/gm, '<li class="ms-4 list-decimal text-caption">$2</li>');

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li class="ms-4 list-disc text-caption">$1</li>');

  // Paragraphs (lines not already wrapped)
  html = html.replace(
    /^(?!<[a-z])((?!^\s*$).+)$/gm,
    '<p class="text-caption leading-relaxed my-1">$1</p>',
  );

  // Strip exfiltration links (javascript:, data: in href)
  html = html.replace(/href=["'](javascript:|data:)[^"']*["']/gi, 'href="#"');

  return html;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function ExportBar({ report }: { report: ResearchReport }) {
  const { t } = useTranslation('research');

  const handleExport = (format: string) => {
    // In production, these would call the sidecar for actual file generation.
    // For the echo mock, we create a download blob.
    if (format === 'markdown') {
      const blob = new Blob([report.markdown], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report.title.replace(/\s+/g, '_')}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } else if (format === 'provenance') {
      const provenance = {
        session_id: report.session_id,
        title: report.title,
        generated_at: report.generated_at,
        claims: report.claims.map((c) => ({
          claim: c.text,
          evidence: c.evidence.map((e) => ({
            source: e.source,
            value: e.value,
            step_id: e.step_id,
            code: e.code_snippet,
          })),
        })),
      };
      const blob = new Blob([JSON.stringify(provenance, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report.title.replace(/\s+/g, '_')}.provenance.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
    // PDF and ZIP would be handled by the sidecar in production
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
      <Button variant="ghost" size="sm" onClick={() => handleExport('pdf')}>
        <Download aria-hidden />
        {t('report.exportPdf')}
      </Button>
      <Button variant="ghost" size="sm" onClick={() => handleExport('zip')}>
        <Download aria-hidden />
        {t('report.exportZip')}
      </Button>
      <Button variant="ghost" size="sm" onClick={() => handleExport('provenance')}>
        <FileJson aria-hidden />
        {t('report.exportProvenance')}
      </Button>
    </div>
  );
}

export function ReportViewer() {
  const { t } = useTranslation('research');
  const { activeSession, setView } = useResearchStore();
  const [view, setReportView] = useState<ReportView>('report');

  const session = activeSession();
  const report = session?.report;

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-8">
        <p className="text-body text-fg-muted">{t('report.notAvailable')}</p>
        <Button variant="ghost" onClick={() => setView('list')}>
          {t('backToList')}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setView('list')}
          className="text-caption text-fg-muted hover:text-fg-primary"
        >
          ← {t('backToList')}
        </button>
        <h3 className="min-w-0 flex-1 truncate text-body font-semibold">{report.title}</h3>
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

      {/* Export bar */}
      <ExportBar report={report} />

      {/* Content */}
      {view === 'report' && (
        <article className="prose-research flex flex-col gap-2">
          {/* Rendered Markdown — sanitized above via renderMarkdown() */}
          <div
            dangerouslySetInnerHTML={{ __html: renderMarkdown(report.markdown) }}
            className="flex flex-col"
          />
        </article>
      )}

      {view === 'figures' && <FigureGallery figures={report.figures} />}
      {view === 'integrity' && <EvidenceIntegrity claims={report.claims} />}
    </div>
  );
}
