import {
  CheckCircle2,
  Download,
  FileText,
  Filter,
  GitBranch,
  Layers,
  List,
  Search,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import { ArtifactDetailPanel } from '@/components/provenance/artifact-detail-panel';
import { ArtifactTreeView } from '@/components/provenance/artifact-tree-view';
import { ProvenanceTimeline } from '@/components/provenance/provenance-timeline';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getBridgeClient } from '@/lib/bridge/client';
import type { ArtifactDto, ProvenanceRecordDto, ProvenanceTreeDto } from '@/lib/bridge/types';

export function ProvenanceRoute() {
  const [activeTab, setActiveTab] = useState<'timeline' | 'tree' | 'artifacts'>('timeline');
  const [records, setRecords] = useState<ProvenanceRecordDto[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactDto[]>([]);
  const [treeData, setTreeData] = useState<ProvenanceTreeDto>({ nodes: [], edges: [], count: 0 });
  const [selectedRecord, setSelectedRecord] = useState<ProvenanceRecordDto | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactDto | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEventType, setSelectedEventType] = useState<string>('all');
  const [selectedSessionId, setSelectedSessionId] = useState<string>('all');
  const [sessions, setSessions] = useState<string[]>([]);

  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyStatus, setVerifyStatus] = useState<{
    valid: boolean;
    records_checked: number;
    error?: string | null;
  } | null>(null);

  const [isExporting, setIsExporting] = useState(false);
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  const client = getBridgeClient();

  useEffect(() => {
    let ignore = false;

    const loadData = async () => {
      try {
        // 1. Load provenance records
        const recRes = await client.call<{ records: ProvenanceRecordDto[]; total: number }>(
          'provenance.list',
          {
            search: searchQuery || undefined,
            event_type: selectedEventType !== 'all' ? selectedEventType : undefined,
            session_id: selectedSessionId !== 'all' ? selectedSessionId : undefined,
          },
        );
        if (ignore) return;
        setRecords(recRes.records || []);

        // Extract unique session IDs for filter
        const allSess = Array.from(new Set((recRes.records || []).map((r) => r.agent_id)));
        setSessions(allSess);

        // 2. Load lineage tree
        const treeRes = await client.call<ProvenanceTreeDto>('provenance.tree', {
          session_id: selectedSessionId !== 'all' ? selectedSessionId : undefined,
        });
        if (ignore) return;
        setTreeData(treeRes || { nodes: [], edges: [], count: 0 });

        // 3. Load artifacts
        const artRes = await client.call<{ artifacts: ArtifactDto[] }>('artifact.list', {});
        if (ignore) return;
        setArtifacts(artRes.artifacts || []);
      } catch {
        // fallback or ignore
      }
    };

    void loadData();
    return () => {
      ignore = true;
    };
  }, [client, searchQuery, selectedEventType, selectedSessionId]);

  const handleVerifyChain = async () => {
    setIsVerifying(true);
    try {
      const res = await client.call<{
        valid: boolean;
        records_checked: number;
        broken_at?: string | null;
        error?: string | null;
      }>('provenance.verify', {});
      setVerifyStatus(res);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleExport = async (artifactPath?: string) => {
    setIsExporting(true);
    try {
      const res = await client.call<{
        filename: string;
        size: number;
        records_count: number;
        base64_data?: string;
        file_path?: string;
      }>('provenance.export', {
        session_id: selectedSessionId !== 'all' ? selectedSessionId : undefined,
        artifact_path: artifactPath,
      });

      if (res.base64_data) {
        // Trigger browser download
        const blob = new Blob([Uint8Array.from(atob(res.base64_data), (c) => c.charCodeAt(0))], {
          type: 'application/zip',
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = res.filename;
        a.click();
        URL.revokeObjectURL(url);
      }
      setExportNotice(`Exported ${res.filename} (${res.records_count} records)`);
      setTimeout(() => setExportNotice(null), 4000);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface-2 p-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-default pb-4">
        <div>
          <h2 className="text-h2 font-semibold text-fg-primary flex items-center gap-2">
            <GitBranch className="size-6 text-accent" />
            Provenance
          </h2>
          <p className="text-caption text-fg-secondary">
            Tamper-evident SHA-256 logs linking artifacts to exact code, data snapshots, and model
            configurations.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {verifyStatus && (
            <Badge
              variant={verifyStatus.valid ? 'success' : 'danger'}
              className="flex items-center gap-1.5 py-1 px-3"
            >
              {verifyStatus.valid ? (
                <ShieldCheck className="size-4" />
              ) : (
                <XCircle className="size-4" />
              )}
              {verifyStatus.valid
                ? `SHA-256 Chain Verified (${verifyStatus.records_checked} events)`
                : `Chain Tampered: ${verifyStatus.error}`}
            </Badge>
          )}

          <Button
            variant="secondary"
            size="sm"
            disabled={isVerifying}
            onClick={() => void handleVerifyChain()}
          >
            <ShieldCheck className="size-4 text-accent" />
            {isVerifying ? 'Verifying...' : 'Verify Chain'}
          </Button>

          <Button
            variant="primary"
            size="sm"
            disabled={isExporting}
            onClick={() => void handleExport()}
          >
            <Download className="size-4" />
            {isExporting ? 'Exporting...' : 'Export Reproducibility'}
          </Button>
        </div>
      </div>

      {exportNotice && (
        <div className="mt-3 rounded-lg border border-accent/40 bg-accent-soft/30 p-2.5 text-caption font-medium text-accent-text flex items-center gap-2">
          <CheckCircle2 className="size-4" />
          {exportNotice}
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute start-3 top-2.5 size-4 text-fg-muted" />
          <input
            type="text"
            placeholder="Search provenance records by tool, query, file, or hash..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-border-default bg-surface ps-9 pe-4 py-2 text-body text-fg-primary placeholder:text-fg-muted focus:border-accent focus:outline-none"
          />
        </div>

        {/* Event Type Filter */}
        <div className="flex items-center gap-2">
          <Filter className="size-4 text-fg-muted" />
          <select
            value={selectedEventType}
            onChange={(e) => setSelectedEventType(e.target.value)}
            className="rounded-lg border border-border-default bg-surface px-3 py-2 text-body text-fg-primary focus:border-accent focus:outline-none"
          >
            <option value="all">All Event Types</option>
            <option value="tool_call">Tool Calls</option>
            <option value="code_execution">Code Executions</option>
            <option value="file_write">File Writes</option>
            <option value="model_response">Model Responses</option>
            <option value="user_message">User Messages</option>
            <option value="subagent_spawn">Subagents</option>
          </select>
        </div>

        {/* Session Filter */}
        {sessions.length > 0 && (
          <select
            value={selectedSessionId}
            onChange={(e) => setSelectedSessionId(e.target.value)}
            className="rounded-lg border border-border-default bg-surface px-3 py-2 text-body text-fg-primary focus:border-accent focus:outline-none"
          >
            <option value="all">All Sessions</option>
            {sessions.map((sid) => (
              <option key={sid} value={sid}>
                Session: {sid.slice(0, 16)}
              </option>
            ))}
          </select>
        )}

        {/* View Mode Tabs */}
        <div className="flex rounded-lg border border-border-default bg-surface p-1">
          <button
            type="button"
            onClick={() => setActiveTab('timeline')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-caption font-medium transition-all ${
              activeTab === 'timeline'
                ? 'bg-accent text-fg-inverse shadow-xs'
                : 'text-fg-secondary hover:text-fg-primary'
            }`}
          >
            <List className="size-4" />
            Timeline
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('tree')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-caption font-medium transition-all ${
              activeTab === 'tree'
                ? 'bg-accent text-fg-inverse shadow-xs'
                : 'text-fg-secondary hover:text-fg-primary'
            }`}
          >
            <Layers className="size-4" />
            Lineage Tree
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('artifacts')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-caption font-medium transition-all ${
              activeTab === 'artifacts'
                ? 'bg-accent text-fg-inverse shadow-xs'
                : 'text-fg-secondary hover:text-fg-primary'
            }`}
          >
            <Sparkles className="size-4" />
            Artifacts ({artifacts.length})
          </button>
        </div>
      </div>

      {/* Main Tab Content Area */}
      <div className="mt-4 flex-1 overflow-y-auto">
        {activeTab === 'timeline' && (
          <ProvenanceTimeline
            records={records}
            selectedRecordId={selectedRecord?.record_id}
            onSelectRecord={(rec) => setSelectedRecord(rec)}
          />
        )}

        {activeTab === 'tree' && (
          <ArtifactTreeView
            tree={treeData}
            onSelectNode={(node) => {
              const matched = records.find((r) => r.record_id === node.id);
              if (matched) setSelectedRecord(matched);
            }}
          />
        )}

        {activeTab === 'artifacts' && (
          <div className="space-y-6">
            {selectedArtifact ? (
              <div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedArtifact(null)}
                  className="mb-4"
                >
                  ← Back to Artifacts List
                </Button>
                <ArtifactDetailPanel
                  artifact={selectedArtifact}
                  onExportReproducibility={(path) => void handleExport(path)}
                />
              </div>
            ) : artifacts.length === 0 ? (
              <div className="flex h-64 flex-col items-center justify-center text-fg-secondary">
                <Sparkles className="mb-2 size-8 opacity-40" />
                <p className="text-body font-medium">No Artifacts Generated Yet</p>
                <p className="text-caption text-fg-muted">
                  Figures, charts, datasets, and reports written by tools will appear here with full
                  provenance lineage.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {artifacts.map((art) => (
                  <div
                    key={art.artifact_path}
                    onClick={() => setSelectedArtifact(art)}
                    className="cursor-pointer rounded-xl border border-border-default bg-surface p-4 transition-all hover:border-accent hover:shadow-md"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex size-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
                        {art.artifact_path.endsWith('.png') ||
                        art.artifact_path.endsWith('.jpg') ? (
                          <Sparkles className="size-5" />
                        ) : (
                          <FileText className="size-5" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <h4 className="truncate text-body font-semibold text-fg-primary">
                          {art.artifact_path.split('/').pop()}
                        </h4>
                        <p className="font-mono text-micro text-fg-muted truncate">
                          {art.artifact_path}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 space-y-1 text-caption text-fg-secondary">
                      <div className="flex justify-between">
                        <span>Tool:</span>
                        <span className="font-medium text-fg-primary">{art.tool_name}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Model:</span>
                        <span>{art.model}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Size:</span>
                        <span>{art.size} bytes</span>
                      </div>
                    </div>

                    <div className="mt-3 border-t border-border-default pt-2 flex justify-end">
                      <Button variant="ghost" size="sm">
                        View Lineage →
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
