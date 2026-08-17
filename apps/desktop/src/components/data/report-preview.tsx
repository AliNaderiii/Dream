/**
 * Report preview: renders the generated markdown (headings, paragraphs,
 * chart embeds) in a scrollable pane with a PDF download action. The
 * renderer is a tiny purpose-built markdown subset — headings, images, and
 * paragraphs — so no HTML from the file is ever injected.
 */

import { Download, FileText, RefreshCw } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';
import { Button } from '@/components/ui/button';

interface ReportPreviewProps {
  markdown: string | null;
  pdfPath: string | null;
  onGenerate: () => void;
  generating: boolean;
  /** Resolves a sidecar-relative file path to a URL the webview can load. */
  resolveFileUrl?: (path: string) => string | null;
}

interface Block {
  kind: 'h1' | 'h2' | 'image' | 'paragraph';
  text: string;
  src?: string;
}

/** Parse the markdown subset the report generator emits. */
export function parseReportMarkdown(markdown: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) {
      blocks.push({ kind: 'paragraph', text: paragraph.join('\n') });
      paragraph = [];
    }
  };
  for (const line of markdown.split('\n')) {
    const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(line.trim());
    if (line.startsWith('## ')) {
      flush();
      blocks.push({ kind: 'h2', text: line.slice(3).trim() });
    } else if (line.startsWith('# ')) {
      flush();
      blocks.push({ kind: 'h1', text: line.slice(2).trim() });
    } else if (image) {
      flush();
      blocks.push({ kind: 'image', text: image[1], src: image[2] });
    } else if (!line.trim()) {
      flush();
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}

export function ReportPreview({
  markdown,
  pdfPath,
  onGenerate,
  generating,
  resolveFileUrl,
}: ReportPreviewProps) {
  if (!markdown) {
    return (
      <EmptyState
        icon={FileText}
        title="No report yet"
        description="Generate a PDF report with an abstract, data summary, results, and the charts from this session."
        action={{ label: generating ? 'Generating…' : 'Generate report', onClick: onGenerate }}
      />
    );
  }

  const blocks = parseReportMarkdown(markdown);
  const pdfUrl = pdfPath ? resolveFileUrl?.(pdfPath) : null;

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onGenerate} disabled={generating}>
          <RefreshCw aria-hidden />
          Regenerate
        </Button>
        <Button asChild size="sm" variant="primary" aria-label="Download PDF">
          <a href={pdfUrl ?? '#'} download="report.pdf">
            <Download aria-hidden />
            Download PDF
          </a>
        </Button>
      </div>
      <article
        aria-label="Report preview"
        className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-border-default bg-surface p-6"
      >
        {blocks.map((block, index) => {
          switch (block.kind) {
            case 'h1':
              return (
                <h1 key={index} className="mb-3 text-h1 font-bold">
                  {block.text}
                </h1>
              );
            case 'h2':
              return (
                <h2 key={index} className="mb-2 mt-5 text-h2 font-semibold">
                  {block.text}
                </h2>
              );
            case 'image': {
              const src = block.src ? resolveFileUrl?.(block.src) : null;
              return src ? (
                <img
                  key={index}
                  src={src}
                  alt={block.text || 'Report chart'}
                  className="my-3 max-h-96 rounded-md border border-border-default"
                />
              ) : (
                <p key={index} className="my-2 text-caption text-fg-muted">
                  [chart: {block.src}]
                </p>
              );
            }
            default:
              return (
                <p key={index} className="mb-2 whitespace-pre-wrap text-body text-fg-secondary">
                  {block.text}
                </p>
              );
          }
        })}
      </article>
    </div>
  );
}
