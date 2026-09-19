/**
 * Vision & OCR studio — real file browser (v4.4).
 *
 * Replaces manual path typing: roots come from `workspace.roots_list`,
 * directory listings from `workspace.files_list`, and inline registration
 * from `workspace.import_folder`. Selecting a file joins the root's absolute
 * path with the entry's relative path and hands the result to the studio,
 * which runs `ocr.extract` on it. In the browser preview the echo runtime
 * serves the same listing shape deterministically — flagged honestly.
 */

import { useEffect, useState } from 'react';
import { ChevronLeft, FileText, Folder, Image as ImageIcon, RefreshCw } from 'lucide-react';

import type { BridgeClient } from '@/lib/bridge/client';
import {
  workspaceFilesList,
  workspaceImportFolder,
  workspaceRootsList,
} from '@/lib/bridge/workspace';
import type { WorkspaceEntry, WorkspaceRoot } from '@/lib/bridge/workspace';
import { joinWorkspacePath } from '@/lib/workspace/join-path';

/** Entry types the OCR engine can meaningfully extract — badged in the list. */
const OCR_TYPES = new Set(['image', 'pdf', 'text', 'csv', 'tsv', 'markdown', 'json']);

function formatSize(size: number): string {
  if (size <= 0) return '—';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function entryIcon(entry: WorkspaceEntry, active: boolean) {
  if (entry.is_dir)
    return <Folder className={`size-3.5 ${active ? 'text-fuchsia-300' : 'text-zinc-500'}`} />;
  if (entry.type === 'image')
    return <ImageIcon className="size-3.5 text-sky-400" aria-hidden="true" />;
  return <FileText className="size-3.5 text-zinc-500" aria-hidden="true" />;
}

export function VisionFileBrowser({
  client,
  selectedPath,
  onSelect,
}: {
  client: BridgeClient;
  selectedPath: string;
  onSelect: (path: string) => void;
}) {
  const [roots, setRoots] = useState<WorkspaceRoot[]>([]);
  const [activeRootId, setActiveRootId] = useState('');
  const [browsePath, setBrowsePath] = useState('');
  const [entries, setEntries] = useState<WorkspaceEntry[]>([]);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [manualOpen, setManualOpen] = useState(false);
  const [importDraft, setImportDraft] = useState('');
  const [importing, setImporting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const activeRoot = roots.find((root) => root.root_id === activeRootId) ?? null;

  // Roots load once per mount (and after an explicit refresh — the refresh
  // handler flips `loading` itself, so this effect only mutates state from
  // async callbacks, never synchronously in its body).
  useEffect(() => {
    let cancelled = false;
    workspaceRootsList(client)
      .then((listed) => {
        if (cancelled) return;
        setRoots(listed.roots);
        setActiveRootId((current) => {
          if (current && listed.roots.some((root) => root.root_id === current)) return current;
          return listed.roots[0]?.root_id ?? '';
        });
        setError('');
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, reloadKey]);

  // The active directory listing follows root + path selection. When no root
  // is active the listing is derived empty at render time instead of being
  // reset synchronously here.
  useEffect(() => {
    if (!activeRootId) return;
    let cancelled = false;
    workspaceFilesList(client, activeRootId, browsePath)
      .then((listing) => {
        if (cancelled) return;
        setEntries(listing.entries);
        setNextCursor(listing.next_cursor);
        setError('');
      })
      .catch((reason) => {
        if (cancelled) return;
        setEntries([]);
        setNextCursor(null);
        setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client, activeRootId, browsePath]);

  const listingEntries = activeRootId ? entries : [];
  const listingCursor = activeRootId ? nextCursor : null;
  const sorted = [...listingEntries].sort((a, b) =>
    a.is_dir === b.is_dir ? a.name.localeCompare(b.name) : a.is_dir ? -1 : 1,
  );

  const segments = browsePath ? browsePath.split('/') : [];

  const handleImport = () => {
    const folder = importDraft.trim();
    if (!folder || importing) return;
    setImporting(true);
    workspaceImportFolder(client, folder)
      .then((imported) => workspaceRootsList(client).then((listed) => ({ imported, listed })))
      .then(({ imported, listed }) => {
        setRoots(listed.roots);
        setActiveRootId(imported.root.root_id);
        setBrowsePath('');
        setImportDraft('');
        setError('');
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => setImporting(false));
  };

  const handleLoadMore = () => {
    if (!activeRootId || nextCursor === null) return;
    workspaceFilesList(client, activeRootId, browsePath, { cursor: nextCursor })
      .then((listing) => {
        setEntries((previous) => [...previous, ...listing.entries]);
        setNextCursor(listing.next_cursor);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  };

  return (
    <div className="rounded-xl border border-white/[0.08] bg-zinc-950/40 p-4" dir="rtl">
      {/* Header */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] pb-3">
        <div className="flex items-center gap-2">
          <Folder className="size-3.5 text-fuchsia-300" aria-hidden="true" />
          <span className="text-xs font-bold text-zinc-200">مرورگر فایل واقعی</span>
          <span className="font-mono text-[10px] text-zinc-500">workspace.files_list</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full border px-2 py-0.5 font-mono text-[9px] ${
              client.transportKind === 'tauri'
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
            }`}
          >
            {client.transportKind === 'tauri'
              ? '● LIVE FILES · PYTHON CORE'
              : '● ECHO LISTING · BROWSER PREVIEW'}
          </span>
          <button
            onClick={() => {
              setLoading(true);
              setReloadKey((key) => key + 1);
            }}
            title="بارگذاری مجدد ریشه‌ها"
            className="rounded-md border border-white/10 p-1 text-zinc-400 transition-colors hover:text-white"
          >
            <RefreshCw className={`size-3 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Root pills */}
      {roots.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          {roots.map((root) => (
            <button
              key={root.root_id}
              onClick={() => {
                setActiveRootId(root.root_id);
                setBrowsePath('');
              }}
              title={root.path}
              className={`max-w-56 truncate rounded-lg border px-2.5 py-1 text-[11px] transition-all ${
                root.root_id === activeRootId
                  ? 'border-fuchsia-500/40 bg-fuchsia-500/15 text-fuchsia-200'
                  : 'border-white/10 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {root.name}
            </button>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && roots.length === 0 && (
        <p className="mb-3 rounded-lg border border-dashed border-white/15 bg-zinc-900/40 px-3 py-2.5 text-[11px] leading-relaxed text-zinc-500">
          هنوز پوشه‌ای ثبت نشده است. مسیر یک پوشه را در کادر زیر وارد کنید تا فایل‌هایش قابل مرور
          شود (ثبت درجا انجام می‌شود و هیچ فایلی کپی نمی‌گردد).
        </p>
      )}

      {/* Inline folder registration */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={importDraft}
          onChange={(e) => setImportDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleImport();
          }}
          placeholder="C:\Users\alina\Documents — مسیر پوشه برای ثبت"
          className="min-w-48 flex-1 rounded-lg border border-white/10 bg-zinc-900 px-2.5 py-1.5 font-mono text-[11px] text-zinc-300 placeholder-zinc-600 focus:outline-none"
          dir="ltr"
        />
        <button
          onClick={handleImport}
          disabled={!importDraft.trim() || importing}
          className="rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 text-[11px] font-medium text-zinc-200 transition-all hover:bg-white/10 disabled:opacity-40"
        >
          {importing ? 'در حال ثبت…' : 'ثبت پوشه (import_folder)'}
        </button>
      </div>

      {/* Breadcrumbs */}
      {activeRoot && (
        <div className="mb-2 flex flex-wrap items-center gap-1 text-[11px]" dir="ltr">
          <button
            onClick={() => setBrowsePath('')}
            className={`rounded px-1.5 py-0.5 font-mono transition-colors ${
              browsePath === '' ? 'bg-white/10 text-white' : 'text-fuchsia-300 hover:bg-white/5'
            }`}
          >
            {activeRoot.name}
          </button>
          {segments.map((segment, index) => (
            <span key={segments.slice(0, index + 1).join('/')} className="flex items-center gap-1">
              <ChevronLeft className="size-3 text-zinc-600" aria-hidden="true" />
              <button
                onClick={() => setBrowsePath(segments.slice(0, index + 1).join('/'))}
                className={`rounded px-1.5 py-0.5 font-mono transition-colors ${
                  index === segments.length - 1
                    ? 'bg-white/10 text-white'
                    : 'text-fuchsia-300 hover:bg-white/5'
                }`}
              >
                {segment}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Directory listing */}
      <div className="max-h-64 space-y-0.5 overflow-y-auto rounded-lg border border-white/[0.06] bg-zinc-900/40 p-1.5">
        {loading && (
          <p className="px-2 py-3 text-center text-[11px] text-zinc-500">در حال بارگذاری…</p>
        )}
        {!loading && sorted.length === 0 && !error && (
          <p className="px-2 py-3 text-center text-[11px] text-zinc-600">این مسیر خالی است.</p>
        )}
        {sorted.map((entry) => {
          const joined = activeRoot ? joinWorkspacePath(activeRoot.path, entry.path) : entry.path;
          const isSelected = joined === selectedPath;
          return (
            <button
              key={entry.path}
              onClick={() => {
                if (entry.is_dir) setBrowsePath(entry.path);
                else onSelect(joined);
              }}
              className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-right transition-all ${
                isSelected ? 'bg-fuchsia-500/15 ring-1 ring-fuchsia-500/40' : 'hover:bg-white/5'
              }`}
            >
              {entryIcon(entry, isSelected)}
              <span
                className="min-w-0 flex-1 truncate font-mono text-[11px] text-zinc-300"
                dir="ltr"
              >
                {entry.name}
              </span>
              {!entry.is_dir && OCR_TYPES.has(entry.type) && (
                <span className="rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-px font-mono text-[9px] text-sky-300">
                  OCR
                </span>
              )}
              <span className="shrink-0 font-mono text-[9px] text-zinc-600" dir="ltr">
                {entry.is_dir ? 'DIR' : formatSize(entry.size)}
              </span>
            </button>
          );
        })}
        {listingCursor !== null && (
          <button
            onClick={handleLoadMore}
            className="w-full rounded-md px-2 py-1.5 text-center text-[11px] text-fuchsia-300 transition-colors hover:bg-white/5"
          >
            موارد بیشتر…
          </button>
        )}
      </div>

      {/* Selected path */}
      {selectedPath && (
        <div className="mt-2.5 flex items-center gap-2 rounded-lg border border-fuchsia-500/25 bg-fuchsia-500/[0.07] px-2.5 py-1.5">
          <span className="shrink-0 text-[10px] text-zinc-400">فایل انتخاب‌شده:</span>
          <span
            className="min-w-0 flex-1 truncate font-mono text-[11px] text-fuchsia-200"
            dir="ltr"
          >
            {selectedPath}
          </span>
        </div>
      )}

      {/* Manual path fallback */}
      <div className="mt-2.5 border-t border-white/[0.06] pt-2.5">
        <button
          onClick={() => setManualOpen((open) => !open)}
          className="text-[11px] text-zinc-500 transition-colors hover:text-zinc-300"
        >
          {manualOpen ? '▾' : '▸'} ورود مسیر دستی (فایل خارج از ریشه‌های ثبت‌شده)
        </button>
        {manualOpen && (
          <input
            value={selectedPath}
            onChange={(e) => onSelect(e.target.value)}
            placeholder="C:\screens\error.png — مسیر کامل فایل"
            className="mt-2 w-full rounded-lg border border-white/10 bg-zinc-900 px-2.5 py-1.5 font-mono text-[11px] text-zinc-300 placeholder-zinc-600 focus:outline-none"
            dir="ltr"
          />
        )}
      </div>

      {/* Error */}
      {error && (
        <p
          className="mt-2.5 rounded-lg border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-300"
          dir="ltr"
        >
          ⚠ {error}
        </p>
      )}
    </div>
  );
}
