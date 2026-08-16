/**
 * Skills manager.
 *
 * A master/detail layout: the list on the inline-start edge with optimistic
 * enable/disable toggles, the selected skill's file rendered (and editable) on
 * the other side. Import goes through a validating dialog; export writes a
 * single `.dream-skill.txt` or a ZIP of the checked rows.
 */

import { Download, Package, Save, Trash2, Upload, Wrench } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ConfirmDialog } from '@/components/shared/confirm-dialog';
import { EmptyState } from '@/components/shared/empty-state';
import { SkillCard } from '@/components/skills/skill-card';
import { SkillCode } from '@/components/skills/skill-code';
import {
  SkillImportDialog,
  type SkillImportRequest,
} from '@/components/skills/skill-import-dialog';
import { Button } from '@/components/ui/button';
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
import type { BridgeSkillDetail, BridgeSkillEx, BridgeSkillProblem } from '@/lib/bridge/types';
import { absoluteDate } from '@/utils/time';

export function SkillsRoute() {
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

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const result = await listSkills(client);
      setSkills(result.skills);
      setProblems(result.problems);
      setStatus(`${result.skills.length} skills loaded`);
      return result.skills;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load skills.');
      return [];
    }
  }, [client]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        await refresh();
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [refresh]);

  // Load the full file whenever the selection changes.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!selectedName) {
        setDetail(null);
        return;
      }
      try {
        const match = await getSkill(client, selectedName);
        if (cancelled) return;
        setDetail(match);
        setDraft(match?.content ?? '');
        setEditing(false);
        setSaveError(null);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load the skill.');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [client, selectedName]);

  /** Optimistic toggle: flip locally, roll back if the bridge refuses. */
  const toggleEnabled = async (skill: BridgeSkillEx, enabled: boolean) => {
    setSkills((prev) => prev.map((s) => (s.name === skill.name ? { ...s, enabled } : s)));
    setStatus(`${skill.name} ${enabled ? 'enabled' : 'disabled'}`);
    try {
      await setSkillEnabled(client, skill.name, enabled);
    } catch (err) {
      setSkills((prev) =>
        prev.map((s) => (s.name === skill.name ? { ...s, enabled: !enabled } : s)),
      );
      setError(err instanceof Error ? err.message : `Could not ${enabled ? 'enable' : 'disable'}.`);
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
      setSaveError(validation.errors.join(' '));
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await installSkill(client, draft, { overwrite: true });
      const updated = await refresh();
      const stillThere = updated.find((s) => s.name === validation.parsed?.name);
      setSelectedName(stillThere?.name ?? selectedName);
      setEditing(false);
      setStatus(`${validation.parsed?.name ?? 'Skill'} saved`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save this skill.');
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
      setStatus(`${detail.name} deleted`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete this skill.');
    }
  };

  const handleExportOne = async (name: string) => {
    try {
      const result = await exportSkill(client, name);
      downloadFile(exportFilename(result.name), result.content);
      setStatus(`${result.name} exported`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export this skill.');
    }
  };

  const handleExportZip = async () => {
    try {
      const names = [...checked];
      const files = await Promise.all(names.map((name) => exportSkill(client, name)));
      const zip = buildSkillZip(files.map((f) => ({ name: f.name, content: f.content })));
      downloadFile('dream-skills.zip', zip as BlobPart, 'application/zip');
      setStatus(`${files.length} skills exported`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export the selected skills.');
    }
  };

  const sorted = useMemo(() => [...skills].sort((a, b) => a.name.localeCompare(b.name)), [skills]);

  return (
    <section aria-label="Skills manager" className="flex h-full min-h-0">
      <section
        aria-label="Installed skills"
        className="flex w-[min(24rem,45%)] shrink-0 flex-col border-e border-border-default"
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-border-default px-3 py-2">
          <Button size="sm" variant="primary" onClick={() => setImportOpen(true)}>
            <Upload aria-hidden />
            Import
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={checked.size === 0}
            onClick={() => void handleExportZip()}
          >
            <Package aria-hidden />
            Export {checked.size > 0 ? `(${checked.size})` : 'ZIP'}
          </Button>
        </div>

        <p aria-live="polite" className="sr-only">
          {status}
        </p>

        {error && (
          <p
            role="alert"
            className="border-b border-danger-fg bg-danger-bg px-3 py-2 text-caption text-danger-fg"
          >
            {error}
          </p>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {loading ? (
            <p className="p-6 text-center text-body text-fg-muted">Loading skills…</p>
          ) : sorted.length === 0 ? (
            <EmptyState
              icon={Wrench}
              title="No skills installed"
              description="Skills are reusable procedures Dream can follow. Import one to get started."
              action={{ label: 'Import a skill', onClick: () => setImportOpen(true) }}
            />
          ) : (
            <ul className="flex flex-col gap-2">
              {sorted.map((skill) => (
                <li key={skill.filename}>
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
                </li>
              ))}
            </ul>
          )}

          {problems.length > 0 && (
            <div className="mt-3 rounded-md border border-warning-fg bg-warning-bg p-2 text-caption text-warning-fg">
              <p className="font-semibold">Some skill files could not be read:</p>
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

      <section aria-label="Skill detail" className="flex min-w-0 flex-1 flex-col">
        {!detail ? (
          <EmptyState
            icon={Wrench}
            title="Select a skill"
            description="Pick a skill from the list to read its steps, edit it, or export it."
          />
        ) : (
          <>
            <header className="flex flex-wrap items-center gap-2 border-b border-border-default px-4 py-3">
              <div className="min-w-0">
                <h2 className="truncate text-h3 font-semibold">{detail.name}</h2>
                <p className="text-caption text-fg-secondary">
                  {detail.description}
                  {detail.created_at ? ` · added ${absoluteDate(detail.created_at)}` : ''}
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
                      {saving ? 'Saving…' : 'Save'}
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
                      Cancel
                    </Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void handleExportOne(detail.name)}
                    >
                      <Download aria-hidden />
                      Export
                    </Button>
                    <Button
                      size="sm"
                      variant="danger-outline"
                      onClick={() => setConfirmDelete(true)}
                    >
                      <Trash2 aria-hidden />
                      Delete
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
                  aria-label={`Edit ${detail.name}`}
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
        title={`Delete ${detail?.name ?? 'this skill'}?`}
        description="The skill file is removed from disk. This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => void handleDelete()}
      />
    </section>
  );
}
