/**
 * Spawn dialog — configures one subagent, or a chain of them.
 *
 * A pipeline is just an ordered list of the same stage form; each stage's
 * result becomes the next stage's context, so the order is the contract and
 * stages can be reordered before launch.
 */

import * as Dialog from '@radix-ui/react-dialog';
import { ArrowDown, ArrowUp, Plus, Trash2, X } from 'lucide-react';
import { useId, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { RpcParams } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

/** Sidecar defaults, mirrored from `dream/subagents.py`. */
const DEFAULT_TOOLS = ['calculate', 'get_datetime', 'remember_fact', 'search_memory'];
const DEFAULT_LIMITS = { max_turns: 8, max_tokens: 20_000, max_duration: 120 };

/** One stage of the form. `tools` is the grant handed to that child. */
export interface StageDraft {
  key: string;
  name: string;
  prompt: string;
  system_prompt: string;
  tools: string[];
  max_turns: number;
  max_tokens: number;
  max_duration: number;
}

let stageKey = 0;

function emptyStage(): StageDraft {
  return {
    key: `stage-${++stageKey}`,
    name: '',
    prompt: '',
    system_prompt: '',
    tools: [...DEFAULT_TOOLS],
    ...DEFAULT_LIMITS,
  };
}

/** Strips the local-only `key` and drops blank optional fields. */
function toParams(stage: StageDraft): RpcParams {
  const params: RpcParams = {
    prompt: stage.prompt.trim(),
    tools: stage.tools,
    max_turns: stage.max_turns,
    max_tokens: stage.max_tokens,
    max_duration: stage.max_duration,
  };
  if (stage.name.trim()) params['name'] = stage.name.trim();
  if (stage.system_prompt.trim()) params['system_prompt'] = stage.system_prompt.trim();
  return params;
}

const fieldClass =
  'selectable w-full rounded-md border border-border-default bg-surface px-2.5 py-1.5 text-body text-fg-primary placeholder:text-fg-muted focus:border-border-strong focus:outline-none';

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-caption font-medium text-fg-secondary">{label}</span>
      {children}
      {hint && <span className="text-micro text-fg-muted">{hint}</span>}
    </label>
  );
}

interface SpawnDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Tool names the parent is willing to delegate. */
  availableTools: string[];
  /** Receives one stage for a single spawn, or several for a pipeline. */
  onSpawn: (stages: RpcParams[], pipelineName: string) => Promise<void> | void;
}

/**
 * The form itself. It lives inside the portal, so Radix unmounts it on close
 * and every open starts from a clean single-stage draft with no reset effect.
 */
function SpawnForm({ onOpenChange, availableTools, onSpawn }: Omit<SpawnDialogProps, 'open'>) {
  const [stages, setStages] = useState<StageDraft[]>(() => [emptyStage()]);
  const [pipelineName, setPipelineName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  const isPipeline = stages.length > 1;

  const patch = (key: string, changes: Partial<StageDraft>) => {
    setStages((prev) => prev.map((s) => (s.key === key ? { ...s, ...changes } : s)));
  };

  const move = (index: number, delta: number) => {
    setStages((prev) => {
      const target = index + delta;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(index, 1);
      next.splice(target, 0, moved);
      return next;
    });
  };

  const submit = async () => {
    const filled = stages.filter((s) => s.prompt.trim());
    if (filled.length === 0) {
      setError('Give the subagent something to do.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSpawn(filled.map(toParams), pipelineName.trim());
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Content
      aria-labelledby={titleId}
      className="fixed start-1/2 top-12 z-50 flex max-h-[85vh] w-[min(44rem,92vw)] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-border-default bg-overlay shadow-e3 rtl:translate-x-1/2"
    >
      <header className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <div>
          <Dialog.Title id={titleId} className="text-h3 font-semibold">
            {isPipeline ? 'New pipeline' : 'New subagent'}
          </Dialog.Title>
          <Dialog.Description className="text-caption text-fg-secondary">
            Runs in isolation with its own memory and only the tools you grant.
          </Dialog.Description>
        </div>
        <Dialog.Close asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Close">
            <X aria-hidden />
          </Button>
        </Dialog.Close>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
        {isPipeline && (
          <Field label="Pipeline name" hint="Each stage receives the previous stage's result.">
            <input
              className={fieldClass}
              value={pipelineName}
              onChange={(e) => setPipelineName(e.target.value)}
              placeholder="Research and summarise"
            />
          </Field>
        )}

        {stages.map((stage, index) => (
          <section
            key={stage.key}
            className="flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-3"
          >
            <header className="flex items-center justify-between gap-2">
              <h3 className="text-body font-semibold">
                {isPipeline ? `Stage ${index + 1}` : 'Configuration'}
              </h3>
              {isPipeline && (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Move stage ${index + 1} up`}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                  >
                    <ArrowUp aria-hidden />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Move stage ${index + 1} down`}
                    disabled={index === stages.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    <ArrowDown aria-hidden />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove stage ${index + 1}`}
                    onClick={() => setStages((prev) => prev.filter((s) => s.key !== stage.key))}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              )}
            </header>

            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name">
                <input
                  className={fieldClass}
                  value={stage.name}
                  onChange={(e) => patch(stage.key, { name: e.target.value })}
                  placeholder="Researcher"
                />
              </Field>
              <Field label="Model">
                <input
                  className={cn(fieldClass, 'text-fg-muted')}
                  value="echo (local)"
                  readOnly
                  aria-readonly
                />
              </Field>
            </div>

            <Field label="Task">
              <textarea
                className={cn(fieldClass, 'min-h-16 resize-y')}
                value={stage.prompt}
                onChange={(e) => patch(stage.key, { prompt: e.target.value })}
                placeholder="Summarise the meeting notes in five bullets."
              />
            </Field>

            <Field label="System prompt" hint="Optional. Shapes how the child behaves.">
              <textarea
                className={cn(fieldClass, 'min-h-12 resize-y')}
                value={stage.system_prompt}
                onChange={(e) => patch(stage.key, { system_prompt: e.target.value })}
                placeholder="You are terse and precise."
              />
            </Field>

            <fieldset className="flex flex-col gap-1.5">
              <legend className="text-caption font-medium text-fg-secondary">Tools</legend>
              <div className="flex flex-wrap gap-1.5">
                {availableTools.map((tool) => {
                  const granted = stage.tools.includes(tool);
                  return (
                    <button
                      key={tool}
                      type="button"
                      aria-pressed={granted}
                      onClick={() =>
                        patch(stage.key, {
                          tools: granted
                            ? stage.tools.filter((t) => t !== tool)
                            : [...stage.tools, tool],
                        })
                      }
                      className={cn(
                        'rounded-full border px-2 py-0.5 text-micro font-semibold transition-colors duration-fast',
                        granted
                          ? 'border-accent bg-accent-soft text-accent-text'
                          : 'border-border-default text-fg-secondary hover:bg-surface-2',
                      )}
                    >
                      {tool}
                    </button>
                  );
                })}
              </div>
              <span className="text-micro text-fg-muted">
                {stage.tools.length} granted — the child can use nothing else.
              </span>
            </fieldset>

            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Max turns">
                <input
                  type="number"
                  min={1}
                  className={fieldClass}
                  value={stage.max_turns}
                  onChange={(e) =>
                    patch(stage.key, {
                      max_turns: Number(e.target.value) || DEFAULT_LIMITS.max_turns,
                    })
                  }
                />
              </Field>
              <Field label="Max tokens">
                <input
                  type="number"
                  min={1}
                  className={fieldClass}
                  value={stage.max_tokens}
                  onChange={(e) =>
                    patch(stage.key, {
                      max_tokens: Number(e.target.value) || DEFAULT_LIMITS.max_tokens,
                    })
                  }
                />
              </Field>
              <Field label="Max seconds">
                <input
                  type="number"
                  min={1}
                  className={fieldClass}
                  value={stage.max_duration}
                  onChange={(e) =>
                    patch(stage.key, {
                      max_duration: Number(e.target.value) || DEFAULT_LIMITS.max_duration,
                    })
                  }
                />
              </Field>
            </div>
          </section>
        ))}

        <Button
          variant="secondary"
          className="self-start"
          onClick={() => setStages((prev) => [...prev, emptyStage()])}
        >
          <Plus aria-hidden />
          Add stage
        </Button>

        {error && (
          <p role="alert" className="text-caption text-danger-fg">
            {error}
          </p>
        )}
      </div>

      <footer className="flex items-center justify-between gap-3 border-t border-border-default px-4 py-3">
        <Badge variant="neutral">{isPipeline ? `${stages.length} stages` : '1 subagent'}</Badge>
        <div className="flex gap-2">
          <Dialog.Close asChild>
            <Button variant="ghost">Cancel</Button>
          </Dialog.Close>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {busy ? 'Starting…' : isPipeline ? 'Run pipeline' : 'Spawn'}
          </Button>
        </div>
      </footer>
    </Dialog.Content>
  );
}

export function SpawnDialog({ open, onOpenChange, availableTools, onSpawn }: SpawnDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <SpawnForm onOpenChange={onOpenChange} availableTools={availableTools} onSpawn={onSpawn} />
      </Dialog.Portal>
    </Dialog.Root>
  );
}
