import {
  ArrowRight,
  Code2,
  Cpu,
  FileText,
  GitCommit,
  Layers,
  MessageSquare,
  Wrench,
} from 'lucide-react';
import React, { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import type { ProvenanceTreeDto, ProvenanceTreeNodeDto } from '@/lib/bridge/types';

interface ArtifactTreeViewProps {
  tree: ProvenanceTreeDto;
  onSelectNode?: (node: ProvenanceTreeNodeDto) => void;
}

export function ArtifactTreeView({ tree, onSelectNode }: ArtifactTreeViewProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  if (!tree || tree.nodes.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-fg-secondary">
        <Layers className="mb-2 size-8 opacity-40" />
        <p className="text-body font-medium">No Lineage Graph Available</p>
        <p className="text-caption text-fg-muted">
          Select a session or artifact to visualize its full provenance DAG.
        </p>
      </div>
    );
  }

  const getNodeIcon = (eventType: string) => {
    switch (eventType) {
      case 'tool_call':
        return <Wrench className="size-4 text-accent" />;
      case 'code_execution':
        return <Code2 className="size-4 text-info-fg" />;
      case 'file_write':
      case 'file_read':
        return <FileText className="size-4 text-warning-fg" />;
      case 'model_response':
        return <Cpu className="size-4 text-success-fg" />;
      case 'user_message':
      case 'agent_message':
        return <MessageSquare className="size-4 text-fg-secondary" />;
      default:
        return <GitCommit className="size-4 text-fg-muted" />;
    }
  };

  const handleNodeClick = (node: ProvenanceTreeNodeDto) => {
    setSelectedNodeId(node.id);
    onSelectNode?.(node);
  };

  return (
    <div className="space-y-6">
      {/* Visual Pipeline / DAG Flow */}
      <div className="rounded-xl border border-border-default bg-surface p-6 shadow-sm">
        <h3 className="mb-4 text-body font-semibold text-fg-primary flex items-center gap-2">
          <Layers className="size-4 text-accent" />
          Artifact Lineage & Execution Tree ({tree.nodes.length} nodes)
        </h3>

        <div className="flex flex-wrap items-center gap-3 overflow-x-auto p-2">
          {tree.nodes.map((node, i) => {
            const isSelected = selectedNodeId === node.id;
            return (
              <React.Fragment key={node.id}>
                {i > 0 && <ArrowRight className="size-4 shrink-0 text-fg-muted/60" />}
                <div
                  onClick={() => handleNodeClick(node)}
                  className={`cursor-pointer rounded-lg border p-3 transition-all duration-fast ${
                    isSelected
                      ? 'border-accent bg-accent-soft/30 shadow-md ring-2 ring-accent'
                      : 'border-border-default bg-surface-2 hover:border-border-hover hover:bg-surface-3'
                  } min-w-[200px] max-w-[240px] shrink-0`}
                >
                  <div className="flex items-center justify-between pb-1">
                    <div className="flex items-center gap-1.5">
                      {getNodeIcon(node.event_type)}
                      <span className="font-mono text-micro font-medium text-fg-muted">
                        {node.event_type}
                      </span>
                    </div>
                    {node.duration_ms && (
                      <span className="font-mono text-micro text-fg-muted">
                        {node.duration_ms}ms
                      </span>
                    )}
                  </div>

                  <p className="truncate text-body-sm font-semibold text-fg-primary">
                    {node.label}
                  </p>

                  <div className="mt-2 flex items-center justify-between text-micro text-fg-secondary">
                    <span className="font-mono truncate max-w-[120px]">{node.agent_id}</span>
                    <span>
                      {new Date(node.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>

                  {/* Input / Output Indicators */}
                  <div className="mt-2 flex gap-1">
                    {node.inputs.length > 0 && (
                      <Badge variant="neutral" className="text-micro">
                        In: {node.inputs.length}
                      </Badge>
                    )}
                    {node.outputs.length > 0 && (
                      <Badge variant="accent" className="text-micro">
                        Out: {node.outputs.length}
                      </Badge>
                    )}
                  </div>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}
