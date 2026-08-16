import {
  Calendar,
  CheckCircle2,
  Cpu,
  Download,
  FileCode,
  FileText,
  GitBranch,
  HardDrive,
  Hash,
  Sparkles,
  Wrench,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { ArtifactDto } from '@/lib/bridge/types';

interface ArtifactDetailPanelProps {
  artifact: ArtifactDto;
  onExportReproducibility?: (artifactPath: string) => void;
}

export function ArtifactDetailPanel({
  artifact,
  onExportReproducibility,
}: ArtifactDetailPanelProps) {
  const fileName = artifact.artifact_path.split('/').pop() || artifact.artifact_path;
  const isImage = /\.(png|jpg|jpeg|svg|webp|gif)$/i.test(artifact.artifact_path);
  const isCode = /\.(py|js|ts|tsx|jsx|json|sql|sh)$/i.test(artifact.artifact_path);

  return (
    <div className="space-y-6 rounded-xl border border-border-default bg-surface p-6 shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 border-b border-border-default pb-4">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
            {isImage ? (
              <Sparkles className="size-5" />
            ) : isCode ? (
              <FileCode className="size-5" />
            ) : (
              <FileText className="size-5" />
            )}
          </div>
          <div>
            <h2 className="text-h3 font-semibold text-fg-primary">{fileName}</h2>
            <p className="font-mono text-caption text-fg-muted">{artifact.artifact_path}</p>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          onClick={() => onExportReproducibility?.(artifact.artifact_path)}
        >
          <Download className="size-4" />
          Export Reproducibility Zip
        </Button>
      </div>

      {/* Verified Lineage Banner */}
      <div className="rounded-lg border border-accent/30 bg-accent-soft/20 p-4">
        <div className="flex items-center gap-2 text-body font-semibold text-accent-text">
          <CheckCircle2 className="size-4 text-accent" />
          Verified Artifact Lineage
        </div>
        <p className="mt-1 text-body-sm text-fg-primary leading-relaxed">
          {artifact.lineage_statement}
        </p>
      </div>

      {/* Metadata Grid */}
      <div className="grid grid-cols-2 gap-4 rounded-lg border border-border-default bg-surface-2 p-4 text-caption">
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-fg-muted">
            <Wrench className="size-3.5" />
            <span>Generating Tool</span>
          </div>
          <p className="font-medium text-fg-primary">{artifact.tool_name}</p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-fg-muted">
            <Cpu className="size-3.5" />
            <span>Model Provider</span>
          </div>
          <p className="font-medium text-fg-primary">{artifact.model}</p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-fg-muted">
            <Calendar className="size-3.5" />
            <span>Creation Time</span>
          </div>
          <p className="font-medium text-fg-primary">
            {new Date(artifact.created_at).toLocaleString()}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-fg-muted">
            <HardDrive className="size-3.5" />
            <span>File Size</span>
          </div>
          <p className="font-medium text-fg-primary">{artifact.size} bytes</p>
        </div>

        <div className="col-span-2 space-y-1">
          <div className="flex items-center gap-1.5 text-fg-muted">
            <Hash className="size-3.5" />
            <span>SHA-256 Checksum</span>
          </div>
          <p className="break-all font-mono text-micro text-fg-muted">{artifact.hash}</p>
        </div>
      </div>

      {/* Linked Record Details */}
      {artifact.generating_record && (
        <div className="space-y-2">
          <h4 className="text-body font-semibold text-fg-primary flex items-center gap-2">
            <GitBranch className="size-4 text-accent" />
            Generating Event Record ({artifact.generating_record.record_id})
          </h4>
          <pre className="max-h-48 overflow-auto rounded-lg border border-border-default bg-surface-2 p-3 font-mono text-micro text-fg-secondary">
            {JSON.stringify(artifact.generating_record.payload, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
