/**
 * Inline notebook renderer: markdown + code cells with their outputs, a
 * per-cell Run button (live execution when the kernel is reachable), and an
 * "Open in JupyterLab" action.
 */

import { BookOpen, ExternalLink, Play } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { NotebookCellDto, NotebookOutputDto } from '@/lib/bridge/types';

interface NotebookViewProps {
  notebookPath: string | null;
  cells: NotebookCellDto[];
  onRunCell: (index: number) => void;
  onOpenLab: () => void;
  running: boolean;
}

function Output({ output }: { output: NotebookOutputDto }) {
  if (output.type === 'error') {
    return (
      <pre className="overflow-auto rounded-md bg-danger-bg p-2 text-caption text-danger-fg">
        {output.ename}: {output.evalue}
        {output.traceback ? `\n${output.traceback}` : ''}
      </pre>
    );
  }
  if (output.image_data && output.image_mime) {
    return (
      <img
        src={`data:${output.image_mime};base64,${output.image_data}`}
        alt="Cell output"
        className="max-h-80 rounded-md border border-border-default"
      />
    );
  }
  if (output.html) {
    // Trusted sidecar output rendered as text to avoid HTML injection.
    return <pre className="overflow-auto rounded-md bg-sunken p-2 text-caption">{output.html}</pre>;
  }
  if (output.text !== undefined) {
    return (
      <pre className="overflow-auto rounded-md bg-sunken p-2 text-caption ltr-island">
        {output.text}
      </pre>
    );
  }
  return null;
}

function Cell({
  cell,
  index,
  onRun,
  running,
}: {
  cell: NotebookCellDto;
  index: number;
  onRun: () => void;
  running: boolean;
}) {
  if (cell.cell_type === 'markdown') {
    return (
      <li className="rounded-lg border border-border-default bg-surface p-3">
        <pre className="whitespace-pre-wrap font-sans text-body">{cell.source}</pre>
      </li>
    );
  }
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="text-micro text-fg-muted tabular ltr-island">
          In [{cell.execution_count ?? ' '}]
        </span>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label={`Run cell ${index}`}
          onClick={onRun}
          disabled={running}
        >
          <Play aria-hidden />
        </Button>
      </div>
      <pre className="overflow-auto rounded-md bg-sunken p-2 text-caption ltr-island">
        {cell.source}
      </pre>
      {(cell.outputs ?? []).map((output, i) => (
        <Output key={i} output={output} />
      ))}
    </li>
  );
}

export function NotebookView({
  notebookPath,
  cells,
  onRunCell,
  onOpenLab,
  running,
}: NotebookViewProps) {
  if (!notebookPath) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No notebook yet"
        description="The agent creates a notebook when an analysis needs one, or ask for one in chat."
      />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          <Badge variant="info">notebook</Badge>
          <span className="truncate text-caption text-fg-muted ltr-island">{notebookPath}</span>
        </span>
        <Button size="sm" variant="secondary" onClick={onOpenLab}>
          <ExternalLink aria-hidden />
          Open in JupyterLab
        </Button>
      </div>
      <ul className="flex flex-col gap-2">
        {cells.map((cell, index) => (
          <Cell
            key={index}
            cell={cell}
            index={index}
            running={running}
            onRun={() => onRunCell(index)}
          />
        ))}
      </ul>
    </div>
  );
}
