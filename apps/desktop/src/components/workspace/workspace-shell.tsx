import { FolderPlus } from 'lucide-react';
import { useEffect, useState } from 'react';

import { FileBrowser } from '@/components/workspace/file-browser';
import { FilePreview } from '@/components/workspace/file-preview';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  workspaceFilesList,
  workspaceFilesPreview,
  workspaceImportFolder,
  workspaceRootsList,
  type WorkspaceEntry,
  type WorkspacePreview,
  type WorkspaceRoot,
} from '@/lib/bridge/workspace';
import { useTranslation } from '@/lib/i18n';

export function WorkspaceShell() {
  const { t } = useTranslation('workspace');
  const { client } = useBridge();
  const [roots, setRoots] = useState<WorkspaceRoot[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState<WorkspaceEntry[]>([]);
  const [preview, setPreview] = useState<WorkspacePreview | null>(null);
  const [folder, setFolder] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [copiedNotice, setCopiedNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void workspaceRootsList(client)
      .then(async (result) => {
        if (cancelled) return;
        setRoots(result.roots);
        const rootId = result.roots[0]?.root_id;
        if (!rootId) return;
        const listing = await workspaceFilesList(client, rootId, '');
        if (cancelled) return;
        setActive(rootId);
        setEntries(listing.entries);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : t('errors.unknown'));
      });
    return () => {
      cancelled = true;
    };
  }, [client, t]);

  const onImport = async () => {
    setError(null);
    try {
      const imported = await workspaceImportFolder(client, folder, name || undefined);
      setActive(imported.root.root_id);
      setPath('');
      setEntries(imported.listing.entries);
      const listed = await workspaceRootsList(client);
      setRoots(listed.roots);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('errors.unknown'));
    }
  };

  const loadListing = async (rootId: string, rel: string) => {
    try {
      const listing = await workspaceFilesList(client, rootId, rel);
      setEntries(listing.entries);
      setPath(rel);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('errors.unknown'));
    }
  };

  const onPreview = async (entry: WorkspaceEntry) => {
    if (!active) return;
    if (entry.is_dir) {
      setPreview(null);
      await loadListing(active, entry.path);
      return;
    }
    try {
      setPreview(await workspaceFilesPreview(client, active, entry.path));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('errors.traversal'));
    }
  };

  const onCopy = async (entry: WorkspaceEntry) => {
    try {
      await navigator.clipboard.writeText(entry.path);
      setCopiedNotice(entry.path);
    } catch {
      setCopiedNotice(entry.path);
    }
  };

  const current = roots.find((root) => root.root_id === active);

  return (
    <main
      className="flex h-full flex-col gap-4 overflow-y-auto p-4"
      aria-labelledby="workspace-title"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 id="workspace-title" className="text-h2 font-semibold">
            {t('title')}
          </h1>
          <p className="text-body text-fg-muted">{t('subtitle')}</p>
        </div>
        {current && (
          <Badge variant="success">
            {current.copied ? t('roots.copied') : t('roots.neverCopied')}
          </Badge>
        )}
      </header>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('roots.import')}</h2>
          <CardDescription>{t('roots.importHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <Input
            label={t('roots.pathLabel')}
            value={folder}
            onChange={(event) => setFolder(event.target.value)}
          />
          <Input
            label={t('roots.nameLabel')}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button className="self-end" onClick={() => void onImport()} disabled={!folder.trim()}>
            <FolderPlus aria-hidden />
            {t('roots.register')}
          </Button>
        </CardContent>
      </Card>

      {error && (
        <p role="alert" className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg">
          {error}
        </p>
      )}
      {copiedNotice && (
        <p aria-live="polite" className="text-caption text-fg-muted">
          {t('browser.copied')}: {copiedNotice}
        </p>
      )}

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(240px,0.35fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <h2 className="text-h3 font-semibold">{t('browser.title')}</h2>
            <CardDescription>
              {current?.path ?? t('browser.global')}
              {path ? ` / ${path}` : ''}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {path && (
              <Button
                variant="ghost"
                size="sm"
                className="mb-2"
                onClick={() => {
                  if (active) void loadListing(active, '');
                }}
              >
                {t('browser.global')}
              </Button>
            )}
            <FileBrowser
              entries={entries}
              onOpen={(entry) => {
                if (!active) return;
                if (entry.is_dir) {
                  void loadListing(active, entry.path);
                  return;
                }
                void onPreview(entry);
              }}
              onPreview={(entry) => void onPreview(entry)}
              onCopyPath={(entry) => void onCopy(entry)}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <h2 className="text-h3 font-semibold">{t('preview.title')}</h2>
          </CardHeader>
          <CardContent>
            <FilePreview preview={preview} />
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
