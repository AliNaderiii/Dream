/**
 * Skills manager.
 *
 * A master/detail layout: the list on the inline-start edge with optimistic
 * enable/disable toggles, the selected skill's file rendered (and editable) on
 * the other side. Import goes through a validating dialog; export writes a
 * single `.dream-skill.txt` or a ZIP of the checked rows.
 */

import { Download, Package, Save, Trash2, Upload, Wrench } from 'lucide-react';
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';

import { BridgeOfflineBanner } from '@/components/shared/bridge-offline-banner';
import { ConfirmDialog } from '@/components/shared/confirm-dialog';
import { EmptyState } from '@/components/shared/empty-state';
import { VirtualList } from '@/components/shared/virtual-list';
import { SkillCard } from '@/components/skills/skill-card';
import { SkillCode } from '@/components/skills/skill-code';
import {
  selectedSkillAfterSave,
  sortSkills,
  validationMessageDescriptor,
  withSkillEnabled,
} from '@/components/skills/skills-model';
import {
  SkillImportDialog,
  type SkillImportRequest,
} from '@/components/skills/skill-import-dialog';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { useBridge } from '@/lib/bridge/hooks';
import {
  buildSkillZip,
  deleteSkill,
  downloadFile,
  exportFilename,
  exportSkill,
  getSkill,
  installSkill,
  listSkills,
  setSkillEnabled,
  validateSkillContent,
} from '@/lib/bridge/skills';
import type { RequestOptions } from '@/lib/bridge/client';
import type { BridgeSkillDetail, BridgeSkillEx, BridgeSkillProblem } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';
import { absoluteDate } from '@/utils/time';

// The learning workspace is code-split: the classic manager never loads it.
const SkillsV2 = lazy(() =>
  import('@/components/skills/skills-v2').then((m) => ({ default: m.SkillsV2 })),
);

/** Lightweight status shown while the workspace chunk streams in. */
function SkillsV2Fallback() {
  const { t } = useTranslation('skills');
  return (
    <div role="status" aria-label={t('v2.loading')} className="flex flex-col gap-2 p-4">
      <div className="skeleton-shape h-8 w-48 rounded-lg" />
      <div className="skeleton-shape h-24 w-full rounded-xl" />
    </div>
  );
}

export function SkillsRoute() {
  const { t } = useTranslation('skills');
  const { t: tc } = useTranslation('common');
  const { client } = useBridge();

  const [skills, setSkills] = useState<BridgeSkillEx[]>([]);
  const [problems, setProblems] = useState<BridgeSkillProblem[]>([]);
  const [detail, setDetail] = useState<BridgeSkillDetail | null>(null);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('');

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [importOpen, setImportOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [tab, setTab] = useState<'manager' | 'learn'>('manager');

  const refresh = useCallback(
    async (options?: RequestOptions) => {
      setError(null);
      try {
        const result = await listSkills(client, options);
        setSkills(result.skills);
        setProblems(result.problems);
        setStatus(t('loadedCount', { count: result.skills.length }));
        return result.skills;
      } catch (err) {
        if (!options?.signal?.aborted) {
          setError(err instanceof Error ? err.message : t('failedLoad'));
        }
        return [];
      }
    },
    [client, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      try {
        await refresh({ signal: controller.signal });
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [refresh]);

  // Load the full file whenever the selection changes.
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      if (!selectedName) {
        setDetail(null);
        return;
      }
      try {
        const match = await getSkill(client, selectedName, { signal: controller.signal });
        setDetail(match);
        setDraft(match?.content ?? '');
        setEditing(false);
        setSaveError(null);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : t('failedLoadDetail'));
        }
      }
    };
    void load();
    return () => controller.abort();
  }, [client, selectedName, t]);

  /** Optimistic toggle: flip locally, roll back if the bridge refuses. */
  const toggleEnabled = async (skill: BridgeSkillEx, enabled: boolean) => {
    setSkills((previous) => withSkillEnabled(previous, skill.name, enabled));
    setStatus(`${skill.name} ${enabled ? t('enabled') : t('disabled')}`);
    try {
      await setSkillEnabled(client, skill.name, enabled);
    } catch (err) {
      setSkills((previous) => withSkillEnabled(previous, skill.name, !enabled));
      setError(err instanceof Error ? err.message : t('failedToggle'));
    }
  };

  const toggleChecked = (skill: BridgeSkillEx, isChecked: boolean) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (isChecked) next.add(skill.name);
      else next.delete(skill.name);
      return next;
    });
  };

  const handleInstall = (request: SkillImportRequest) =>
    installSkill(client, request.content, {
      overwrite: request.overwrite,
      ...(request.name ? { name: request.name } : {}),
    });

  const handleSave = async () => {
    const validation = validateSkillContent(draft);
    if (!validation.ok) {
      setSaveError(
        validation.issues
          .map((issue) => {
            const message = validationMessageDescriptor(issue);
            return t(message.key, message.options);
          })
          .join(' '),
      );
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await installSkill(client, draft, { overwrite: true });
      const updated = await refresh();
      setSelectedName(selectedSkillAfterSave(updated, validation.parsed?.name, selectedName));
      setEditing(false);
      setStatus(`${validation.parsed?.name ?? tc('nav.skills')} ${t('saved')}`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : t('failedSave'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!detail) return;
    try {
      await deleteSkill(client, detail.name);
      setSelectedName(null);
      setDetail(null);
      setStatus(`${detail.name} ${t('deleted')}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedDelete'));
    }
  };

  const handleExportOne = async (name: string) => {
    try {
      const result = await exportSkill(client, name);
      downloadFile(exportFilename(result.name), result.content);
      setStatus(`${result.name} ${t('exported')}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedExport'));
    }
  };

  const handleExportZip = async () => {
    try {
      const names = [...checked];
      const files = await Promise.all(names.map((name) => exportSkill(client, name)));
      const zip = buildSkillZip(files.map((f) => ({ name: f.name, content: f.content })));
      downloadFile('dream-skills.zip', zip as BlobPart, 'application/zip');
      setStatus(t('exportedMany', { count: files.length }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedExportMany'));
    }
  };

  const sorted = useMemo(() => sortSkills(skills), [skills]);

  return (
    <section aria-label={t('title')} className="flex h-full min-h-0 flex-col">
      <div
        role="tablist"
        aria-label={t('title')}
        className="flex gap-1 border-b border-border-default px-4 pt-3"
      >
        {(
          [
            { id: 'manager', label: t('title') },
            { id: 'learn', label: t('v2.tab') },
          ] as const
        ).map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            onClick={() => setTab(entry.id)}
            className={cn(
              'rounded-t-lg border border-b-0 px-3 py-1.5 text-caption font-medium transition-colors duration-fast motion-reduce:transition-none',
              tab === entry.id
                ? 'border-border-default bg-surface text-fg-primary'
                : 'border-transparent text-fg-muted hover:bg-surface-2',
            )}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab === 'learn' ? (
        <div className="min-h-0 flex-1">
          <Suspense fallback={<SkillsV2Fallback />}>
            <SkillsV2 />
          </Suspense>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <section
            aria-label={t('installed')}
            className="flex w-[min(24rem,45%)] shrink-0 flex-col border-e border-border-default"
          >
            <div className="flex flex-wrap items-center gap-2 border-b border-border-default px-3 py-2">
              <Button size="sm" variant="primary" onClick={() => setImportOpen(true)}>
                <Upload aria-hidden />
                {t('import')}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={checked.size === 0}
                onClick={() => void handleExportZip()}
              >
                <Package aria-hidden />
                {checked.size > 0 ? `${tc('generic.export')} (${checked.size})` : t('exportZip')}
              </Button>
            </div>

            <p aria-live="polite" className="sr-only">
              {status}
            </p>

            <BridgeOfflineBanner compact />

            {error && (
              <div
                role="alert"
                className="flex items-center gap-2 border-b border-danger-fg bg-danger-bg px-3 py-2 text-caption text-danger-fg"
              >
                <span className="min-w-0 flex-1">{error}</span>
                <Button size="sm" variant="secondary" onClick={() => void refresh()}>
                  {t('retry')}
                </Button>
              </div>
            )}

            <div className="flex min-h-0 flex-1 flex-col p-3">
              {loading ? (
                <div role="status" aria-label={t('loading')} className="flex flex-col gap-2">
                  {Array.from({ length: 5 }, (_, index) => (
                    <div
                      key={index}
                      className="h-28 animate-pulse rounded-lg bg-surface-2 motion-reduce:animate-none"
                    />
                  ))}
                </div>
              ) : sorted.length === 0 ? (
                <EmptyState
                  icon={Wrench}
                  title={t('noSkills')}
                  description={t('noSkillsDesc')}
                  action={{ label: t('importSkill'), onClick: () => setImportOpen(true) }}
                />
              ) : (
                <VirtualList
                  items={sorted}
                  getKey={(skill) => skill.filename}
                  estimateSize={116}
                  ariaLabel={t('installed')}
                  className="flex-1"
                  renderItem={(skill) => (
                    <div className="h-full pb-2">
                      <SkillCard
                        skill={skill}
                        selected={selectedName === skill.name}
                        checked={checked.has(skill.name)}
                        {...(detail && detail.name === skill.name
                          ? { createdAt: detail.created_at }
                          : {})}
                        onSelect={(next) => setSelectedName(next.name)}
                        onToggleEnabled={(next, enabled) => void toggleEnabled(next, enabled)}
                        onToggleChecked={toggleChecked}
                      />
                    </div>
                  )}
                />
              )}

              {problems.length > 0 && (
                <div className="mt-3 rounded-md border border-warning-fg bg-warning-bg p-2 text-caption text-warning-fg">
                  <p className="font-semibold">{t('problems')}</p>
                  <ul className="ps-4">
                    {problems.map((problem) => (
                      <li key={problem.filename} className="list-disc">
                        <span className="ltr-island">{problem.filename}</span> — {problem.detail}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </section>

          <section aria-label={t('detail')} className="flex min-w-0 flex-1 flex-col">
            {!detail ? (
              <EmptyState
                icon={Wrench}
                title={t('selectSkill')}
                description={t('selectSkillDesc')}
              />
            ) : (
              <>
                <header className="flex flex-wrap items-center gap-2 border-b border-border-default px-4 py-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-h3 font-semibold">{detail.name}</h2>
                    <p className="text-caption text-fg-secondary">
                      {detail.description}
                      {detail.created_at
                        ? ` · ${t('added', { date: absoluteDate(detail.created_at) })}`
                        : ''}
                    </p>
                  </div>
                  <div className="ms-auto flex items-center gap-2">
                    {editing ? (
                      <>
                        <Button
                          size="sm"
                          variant="primary"
                          disabled={saving}
                          onClick={() => void handleSave()}
                        >
                          <Save aria-hidden />
                          {saving ? tc('generic.saving') : tc('generic.save')}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setDraft(detail.content);
                            setEditing(false);
                            setSaveError(null);
                          }}
                        >
                          {tc('generic.cancel')}
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                          {tc('generic.edit')}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void handleExportOne(detail.name)}
                        >
                          <Download aria-hidden />
                          {tc('generic.export')}
                        </Button>
                        <Button
                          size="sm"
                          variant="danger-outline"
                          onClick={() => setConfirmDelete(true)}
                        >
                          <Trash2 aria-hidden />
                          {tc('generic.delete')}
                        </Button>
                      </>
                    )}
                  </div>
                </header>

                <div className="min-h-0 flex-1 overflow-y-auto p-4">
                  {saveError && (
                    <p
                      role="alert"
                      className="mb-3 rounded-md border border-danger-fg bg-danger-bg px-3 py-2 text-caption text-danger-fg"
                    >
                      {saveError}
                    </p>
                  )}

                  {editing ? (
                    <textarea
                      value={draft}
                      rows={20}
                      aria-label={t('editAria', { name: detail.name })}
                      onChange={(event) => setDraft(event.target.value)}
                      className="selectable ltr-island min-h-80 w-full resize-y rounded-md border border-border-default bg-canvas p-3 text-code text-fg-primary"
                    />
                  ) : (
                    <SkillCode content={detail.content} />
                  )}
                </div>
              </>
            )}
          </section>

          <SkillImportDialog
            open={importOpen}
            onOpenChange={setImportOpen}
            onInstall={handleInstall}
            onInstalled={() => void refresh()}
          />

          <ConfirmDialog
            open={confirmDelete}
            onOpenChange={setConfirmDelete}
            title={t('deleteTitle', { name: detail?.name ?? '…' })}
            description={t('deleteDesc')}
            confirmLabel={tc('generic.delete')}
            onConfirm={() => void handleDelete()}
          />
        </div>
      )}
    </section>
  );
}
