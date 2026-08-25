/**
 * Projects — folders for your work (S06).
 *
 * A project is a folder-like grouping, not a CRM record: it owns a name, an
 * optional workspace folder (linked in place, nothing is copied), and the
 * sessions grouped under it. Deleting a project confirms first and ungroups
 * its sessions — it never deletes a conversation.
 *
 * Session grouping goes through the bridge (`project.*` RPCs); the add picker
 * offers sessions that no project claims yet, and a session always belongs to
 * exactly one project.
 */

import { FolderKanban, FolderOpen, FolderPlus, Plus, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ConfirmDialog } from '@/components/shared/confirm-dialog';
import { EmptyState } from '@/components/shared/empty-state';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useBridge } from '@/lib/bridge/hooks';
import {
  addSessionToProject,
  createProject,
  deleteProject,
  listProjects,
  removeSessionFromProject,
} from '@/lib/bridge/projects';
import { workspaceImportFolder, workspaceProjectSettings } from '@/lib/bridge/workspace';
import type { BridgeProject } from '@/lib/bridge/types';
import type { BridgeSession } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { dialogApi } from '@/lib/tauri';
import { isTauri } from '@/utils/platform';
import { relativeTime } from '@/utils/time';

export function ProjectsRoute() {
  const { t } = useTranslation('common');
  const { t: tp } = useTranslation('projects');
  const { client } = useBridge();
  const navigate = useNavigate();

  const [projects, setProjects] = useState<BridgeProject[]>([]);
  const [sessions, setSessions] = useState<BridgeSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleting, setDeleting] = useState<BridgeProject | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [projectResult, sessionResult] = await Promise.all([
        listProjects(client),
        client.call<{ sessions: BridgeSession[] }>('session.list', {}),
      ]);
      setProjects(projectResult.projects);
      setSessions(sessionResult.sessions);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('projects.loadError'));
    }
  }, [client, t]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        await refresh();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const groupedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const project of projects) for (const id of project.session_ids) ids.add(id);
    return ids;
  }, [projects]);

  const sessionById = useMemo(
    () => new Map(sessions.map((session) => [session.id, session])),
    [sessions],
  );

  const onCreate = async (draft: { name: string; folder: string | null; inPlace?: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      if (draft.inPlace && draft.folder) {
        await workspaceImportFolder(client, draft.folder, draft.name);
      } else {
        await createProject(client, draft);
      }
      setCreateOpen(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('projects.loadError'));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      await deleteProject(client, deleting.id);
      setDeleting(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('projects.loadError'));
    } finally {
      setBusy(false);
    }
  };

  const onAddSession = async (projectId: string, sessionId: string) => {
    if (!sessionId) return;
    try {
      await addSessionToProject(client, projectId, sessionId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('projects.loadError'));
    }
  };

  const onRemoveSession = async (projectId: string, sessionId: string) => {
    try {
      await removeSessionFromProject(client, projectId, sessionId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('projects.loadError'));
    }
  };

  const onNewSessionHere = async (project: BridgeProject) => {
    try {
      const created = await client.call<{ session_id: string }>('session.create', {
        title: project.name,
      });
      await addSessionToProject(client, project.id, created.session_id);
      await refresh();
      void navigate(`/chat/${created.session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('projects.loadError'));
    }
  };

  const ungrouped = sessions.filter((session) => !groupedIds.has(session.id));

  return (
    <section aria-label={t('projects.title')} className="mx-auto w-full max-w-5xl p-6">
      <header className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-h2 font-semibold">{t('projects.title')}</h2>
          <p className="text-body text-fg-secondary">{t('projects.description')}</p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" aria-hidden />
          {t('projects.new')}
        </Button>
      </header>

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-md border border-border-default bg-surface p-3 text-caption text-fg-secondary"
        >
          {error}
        </p>
      )}

      {!loading && projects.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title={t('projects.title')}
          description={t('projects.description')}
          action={{ label: t('projects.new'), onClick: () => setCreateOpen(true) }}
        />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {projects.map((project) => (
            <li
              key={project.id}
              className="flex flex-col gap-3 rounded-xl border border-border-default bg-surface p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate text-h3 font-semibold">{project.name}</h3>
                  {project.folder && (
                    <p
                      dir="ltr"
                      className="ltr-island mt-0.5 flex items-center gap-1 truncate text-caption text-fg-muted"
                    >
                      <FolderOpen className="size-3.5 shrink-0" aria-hidden />
                      {project.folder}
                    </p>
                  )}
                  {project.folder && (
                    <p className="mt-1 text-micro text-fg-muted">{tp('v2.inPlaceBadge')}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`${t('projects.deleteProject')}: ${project.name}`}
                  onClick={() => setDeleting(project)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </div>

              <div>
                <p className="mb-1 text-micro font-semibold uppercase text-fg-muted">
                  {t('projects.sessionsHeading')} ·{' '}
                  {t('projects.sessionCount', { count: project.session_ids.length })}
                </p>
                {project.session_ids.length === 0 ? (
                  <p className="text-caption text-fg-muted">{t('projects.sessionsEmpty')}</p>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {project.session_ids.map((sessionId) => {
                      const session = sessionById.get(sessionId);
                      return (
                        <li
                          key={sessionId}
                          className="flex items-center gap-2 rounded-md px-2 py-1 text-body hover:bg-surface-2"
                        >
                          <button
                            type="button"
                            className="min-w-0 flex-1 truncate text-start"
                            title={t('projects.openSession')}
                            onClick={() => void navigate(`/chat/${sessionId}`)}
                          >
                            {session?.title ?? sessionId}
                          </button>
                          {session && (
                            <span className="shrink-0 text-micro text-fg-muted">
                              {relativeTime(session.updated_at)}
                            </span>
                          )}
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`${t('projects.removeSession')}: ${session?.title ?? sessionId}`}
                            onClick={() => void onRemoveSession(project.id, sessionId)}
                          >
                            <X className="size-3.5" aria-hidden />
                          </Button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="mt-auto flex items-center gap-2">
                <select
                  aria-label={`${t('projects.addSession')}: ${project.name}`}
                  className="h-8 min-w-0 flex-1 rounded-md border border-border-default bg-canvas px-2 text-caption"
                  value=""
                  onChange={(event) => void onAddSession(project.id, event.target.value)}
                >
                  <option value="" disabled>
                    {ungrouped.length === 0
                      ? t('projects.addSessionNone')
                      : t('projects.addSession')}
                  </option>
                  {ungrouped.map((session) => (
                    <option key={session.id} value={session.id}>
                      {session.title}
                    </option>
                  ))}
                </select>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void onNewSessionHere(project)}
                >
                  <FolderPlus className="size-4" aria-hidden />
                  {t('projects.newSession')}
                </Button>
                {project.folder && (
                  <Button variant="ghost" size="sm" onClick={() => void navigate('/workspace')}>
                    {tp('v2.openWorkspace')}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    void workspaceProjectSettings(client, project.id, { default_mode: 'plan' })
                  }
                >
                  {tp('v2.settings')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* The key remounts the dialog on every open/close, so its fields start
          blank each time without a reset effect. */}
      <CreateProjectDialog
        key={createOpen ? 'open' : 'closed'}
        open={createOpen}
        busy={busy}
        onOpenChange={setCreateOpen}
        onCreate={onCreate}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t('projects.confirmDeleteTitle')}
        description={t('projects.confirmDeleteDesc')}
        confirmLabel={t('projects.deleteProject')}
        onConfirm={() => void onDelete()}
      />
    </section>
  );
}

/** Name + workspace folder. In Tauri the folder comes from the native picker. */
function CreateProjectDialog({
  open,
  busy,
  onOpenChange,
  onCreate,
}: {
  open: boolean;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (draft: {
    name: string;
    folder: string | null;
    inPlace?: boolean;
  }) => Promise<void> | void;
}) {
  const { t } = useTranslation('common');
  const { t: tp } = useTranslation('projects');
  const [name, setName] = useState('');
  const [folder, setFolder] = useState('');
  const [inPlace, setInPlace] = useState(false);

  const browse = async () => {
    if (!isTauri()) return; // the text input is the browser fallback
    const picked = await dialogApi.selectFolder({ title: t('projects.folderLabel') });
    if (picked) setFolder(picked);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(30rem,92vw)]">
        <DialogHeader>
          <DialogTitle>{t('projects.new')}</DialogTitle>
          <DialogDescription>{t('projects.description')}</DialogDescription>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-caption font-medium">
            {t('projects.nameLabel')}
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('projects.namePlaceholder')}
              className="h-9 rounded-md border border-border-default bg-canvas px-3 text-body outline-none focus:border-accent"
            />
          </label>
          <label className="flex flex-col gap-1 text-caption font-medium">
            {t('projects.folderLabel')}
            <span className="flex gap-2">
              <input
                value={folder}
                onChange={(event) => setFolder(event.target.value)}
                placeholder={t('projects.folderPlaceholder')}
                dir="ltr"
                className="ltr-island h-9 min-w-0 flex-1 rounded-md border border-border-default bg-canvas px-3 text-body outline-none focus:border-accent"
              />
              <Button variant="secondary" onClick={() => void browse()}>
                {t('projects.folderBrowse')}
              </Button>
            </span>
            <span className="text-micro font-normal text-fg-muted">
              {t('projects.folderOptional')}
            </span>
          </label>
          <label className="flex items-center gap-2 text-caption font-medium">
            <input
              type="checkbox"
              checked={inPlace}
              onChange={(event) => setInPlace(event.target.checked)}
            />
            {tp('v2.importInPlace')}
          </label>
          <p className="text-micro text-fg-muted">{tp('v2.importHelp')}</p>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            {t('projects.cancel')}
          </Button>
          <Button
            variant="primary"
            disabled={busy || !name.trim()}
            onClick={() =>
              void onCreate({ name: name.trim(), folder: folder.trim() || null, inPlace })
            }
          >
            {t('projects.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
