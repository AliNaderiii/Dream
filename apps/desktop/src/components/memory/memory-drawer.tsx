/**
 * Slide-in drawer for viewing, editing and creating a memory.
 *
 * The drawer is a Radix dialog anchored to the inline edge, which gives it
 * focus trapping, `Escape` to dismiss and focus restore for free. Closing with
 * unsaved edits raises a confirmation instead of silently discarding them.
 */

import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Save, Trash2, X } from 'lucide-react';
import { useMemo, useState } from 'react';

import { ConfirmDialog } from '@/components/shared/confirm-dialog';
import { ImportanceSlider, ImportanceStars } from '@/components/memory/importance-stars';
import { KindBadge } from '@/components/memory/kind-badge';
import { MemoryScore } from '@/components/memory/memory-score';
import { Button } from '@/components/ui/button';
import { DialogOverlay } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  byteLength,
  formatBytes,
  MAX_MEMORY_CONTENT_BYTES,
  sanitizeMemoryText,
  toStars,
} from '@/lib/bridge/memory';
import { MEMORY_KINDS } from '@/lib/bridge/types';
import type { BridgeMemory, MemoryKind } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { absoluteTime, relativeTime } from '@/utils/time';

/** The editable fields, in UI units (importance is stars 0–10). */
export interface MemoryDraft {
  content: string;
  kind: MemoryKind;
  stars: number;
}

interface MemoryDrawerProps {
  /** `null` closes the drawer; `'new'` opens the create form. */
  memory: BridgeMemory | 'new' | null;
  onClose: () => void;
  onSave: (draft: MemoryDraft, memory: BridgeMemory | null) => Promise<void>;
  onDelete: (memory: BridgeMemory) => Promise<void>;
  /** Server-side failure to surface inside the drawer. */
  error?: string | null;
}

function draftFrom(memory: BridgeMemory | 'new' | null): MemoryDraft {
  if (!memory || memory === 'new') return { content: '', kind: 'semantic', stars: 5 };
  return {
    content: memory.content,
    kind: (MEMORY_KINDS as readonly string[]).includes(memory.kind)
      ? (memory.kind as MemoryKind)
      : 'semantic',
    stars: toStars(memory.importance),
  };
}

export function MemoryDrawer({ memory, onClose, onSave, onDelete, error }: MemoryDrawerProps) {
  const { t } = useTranslation('memory');
  const isNew = memory === 'new';
  const record = memory && memory !== 'new' ? memory : null;

  // The route remounts this component (via `key`) whenever the target memory
  // changes, so initialising from props here is the whole reset story — no
  // synchronising effect is needed.
  const [editing, setEditing] = useState(isNew);
  const [draft, setDraft] = useState<MemoryDraft>(() => draftFrom(memory));
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const pristine = useMemo(() => draftFrom(memory), [memory]);
  const dirty =
    editing &&
    (draft.content !== pristine.content ||
      draft.kind !== pristine.kind ||
      draft.stars !== pristine.stars);

  const contentBytes = byteLength(draft.content);
  const overLimit = contentBytes > MAX_MEMORY_CONTENT_BYTES;

  const requestClose = () => {
    if (dirty) setConfirmDiscard(true);
    else onClose();
  };

  const save = async () => {
    if (!draft.content.trim()) {
      setLocalError(t('drawer.validationEmpty'));
      return;
    }
    if (overLimit) {
      setLocalError(t('drawer.validationSize', { used: formatBytes(contentBytes) }));
      return;
    }
    setSaving(true);
    setLocalError(null);
    try {
      await onSave(draft, record);
    } finally {
      setSaving(false);
    }
  };

  const shownError = localError ?? error ?? null;

  return (
    <>
      <DialogPrimitive.Root
        open={memory !== null}
        onOpenChange={(next) => {
          if (!next) requestClose();
        }}
      >
        <DialogPrimitive.Portal>
          <DialogOverlay />
          <DialogPrimitive.Content
            aria-describedby={undefined}
            onEscapeKeyDown={(event) => {
              if (dirty) {
                event.preventDefault();
                setConfirmDiscard(true);
              }
            }}
            className="fixed end-0 top-0 z-50 flex h-full w-[min(30rem,94vw)] flex-col border-s border-border-default bg-surface shadow-e3"
          >
            <header className="flex items-center gap-2 border-b border-border-default px-4 py-3">
              <DialogPrimitive.Title className="text-h3 font-semibold">
                {isNew ? t('drawer.newTitle') : t('drawer.detailTitle')}
              </DialogPrimitive.Title>
              <Button
                size="icon-sm"
                variant="ghost"
                className="ms-auto"
                aria-label={t('drawer.close')}
                onClick={requestClose}
              >
                <X aria-hidden />
              </Button>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              {shownError && (
                <p
                  role="alert"
                  className="mb-3 rounded-md border border-danger-fg bg-danger-bg px-3 py-2 text-caption text-danger-fg"
                >
                  {shownError}
                </p>
              )}

              {editing ? (
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="memory-content" className="text-caption font-medium">
                      {t('drawer.content')}
                    </label>
                    <textarea
                      id="memory-content"
                      value={draft.content}
                      rows={10}
                      onChange={(event) => setDraft({ ...draft, content: event.target.value })}
                      className="selectable min-h-40 w-full resize-y rounded-md border border-border-default bg-canvas p-2.5 text-body text-fg-primary"
                    />
                    <p
                      className={
                        overLimit ? 'text-micro text-danger-fg' : 'text-micro text-fg-muted'
                      }
                    >
                      {t('drawer.size', { used: formatBytes(contentBytes) })}
                    </p>
                  </div>

                  <div className="flex items-center justify-between gap-4">
                    <span className="text-caption font-medium">{t('drawer.kind')}</span>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" variant="secondary">
                          {t(`kind.${draft.kind}`)}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {MEMORY_KINDS.map((kind) => (
                          <DropdownMenuCheckboxItem
                            key={kind}
                            checked={draft.kind === kind}
                            onCheckedChange={() => setDraft({ ...draft, kind })}
                          >
                            {t(`kind.${kind}`)}
                          </DropdownMenuCheckboxItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>

                  <div className="flex items-center justify-between gap-4">
                    <span className="text-caption font-medium">{t('drawer.importance')}</span>
                    <ImportanceSlider
                      label={t('drawer.importance')}
                      value={draft.stars}
                      onChange={(stars) => setDraft({ ...draft, stars })}
                    />
                  </div>
                </div>
              ) : (
                record && (
                  <div className="flex flex-col gap-4">
                    <p className="selectable whitespace-pre-wrap break-words text-body text-fg-primary">
                      {sanitizeMemoryText(record.content)}
                    </p>
                    <MemoryScore memory={record} />
                    <dl className="flex flex-col gap-2 border-t border-border-default pt-3 text-caption">
                      <Field label={t('drawer.kind')}>
                        <KindBadge kind={record.kind} />
                      </Field>
                      <Field label={t('drawer.importance')}>
                        <ImportanceStars value={toStars(record.importance)} />
                      </Field>
                      <Field label={t('drawer.created')}>
                        <span title={absoluteTime(record.created_at)}>
                          {relativeTime(record.created_at)}
                        </span>
                      </Field>
                      <Field label={t('drawer.lastUsed')}>
                        <span title={absoluteTime(record.last_used_at)}>
                          {record.last_used_at ? relativeTime(record.last_used_at) : '—'}
                        </span>
                      </Field>
                      <Field label={t('drawer.source')}>
                        <span className="ltr-island text-caption">{record.source || '—'}</span>
                      </Field>
                      <Field label={t('drawer.used')}>
                        <span className="tabular">{record.use_count}×</span>
                      </Field>
                      {record.tags.length > 0 && (
                        <Field label={t('drawer.tags')}>
                          <span className="flex flex-wrap gap-1">
                            {record.tags.map((tag) => (
                              <span
                                key={tag}
                                className="rounded-full bg-surface-2 px-2 py-0.5 text-micro text-fg-muted"
                              >
                                {tag}
                              </span>
                            ))}
                          </span>
                        </Field>
                      )}
                    </dl>
                  </div>
                )
              )}
            </div>

            <footer className="flex items-center gap-2 border-t border-border-default px-4 py-3">
              {editing ? (
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={saving || overLimit || !draft.content.trim()}
                    onClick={() => void save()}
                  >
                    <Save aria-hidden />
                    {saving ? t('drawer.saving') : t('drawer.save')}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      if (isNew) requestClose();
                      else if (dirty) setConfirmDiscard(true);
                      else setEditing(false);
                    }}
                  >
                    {t('drawer.cancel')}
                  </Button>
                </>
              ) : (
                record && (
                  <>
                    <Button variant="primary" size="sm" onClick={() => setEditing(true)}>
                      {t('drawer.edit')}
                    </Button>
                    <Button
                      variant="danger-outline"
                      size="sm"
                      className="ms-auto"
                      onClick={() => setConfirmDelete(true)}
                    >
                      <Trash2 aria-hidden />
                      {t('drawer.delete')}
                    </Button>
                  </>
                )
              )}
            </footer>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('drawer.deleteTitle')}
        description={t('drawer.deleteDescription')}
        confirmLabel={t('drawer.delete')}
        onConfirm={() => {
          if (record) void onDelete(record);
        }}
      />

      <ConfirmDialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title={t('drawer.discardTitle')}
        description={t('drawer.discardDescription')}
        confirmLabel={t('drawer.discard')}
        onConfirm={() => {
          setDraft(pristine);
          setEditing(false);
          onClose();
        }}
      />
    </>
  );
}

/** One `<dt>`/`<dd>` pair in the detail list. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-fg-secondary">{children}</dd>
    </div>
  );
}
