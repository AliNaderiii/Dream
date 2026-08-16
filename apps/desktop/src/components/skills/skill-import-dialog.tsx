/**
 * Skill import flow: choose a source, validate, preview, then confirm.
 *
 * A file picked with `<input type="file">` opens the OS dialog under Tauri as
 * well as in the browser, so one code path covers both. Validation runs in the
 * renderer first (size, absolute paths, dangerous imports, required sections)
 * and the server re-checks everything; a name collision comes back as a
 * `conflict` result, which promotes the dialog to the resolve step.
 */

import { AlertTriangle, FileUp, Upload } from 'lucide-react';
import { useRef, useState } from 'react';

import { SkillCode } from '@/components/skills/skill-code';
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
import { renderSkillText, validateSkillContent, type ParsedSkill } from '@/lib/bridge/skills';
import type { SkillInstallResult } from '@/lib/bridge/types';

/** What the dialog asks the route to do once the user confirms. */
export interface SkillImportRequest {
  content: string;
  overwrite: boolean;
  /** Set when the user chose to rename rather than overwrite. */
  name?: string;
}

interface SkillImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Performs the install; resolves with the bridge's result. */
  onInstall: (request: SkillImportRequest) => Promise<SkillInstallResult>;
  /** Called after a successful install so the route can refresh. */
  onInstalled: () => void;
}

type Step = 'source' | 'preview' | 'conflict';

export function SkillImportDialog({
  open,
  onOpenChange,
  onInstall,
  onInstalled,
}: SkillImportDialogProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [content, setContent] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [parsed, setParsed] = useState<ParsedSkill | null>(null);
  const [step, setStep] = useState<Step>('source');
  const [renameTo, setRenameTo] = useState('');
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setContent('');
    setErrors([]);
    setParsed(null);
    setStep('source');
    setRenameTo('');
    setServerError(null);
    setBusy(false);
  };

  const close = () => {
    reset();
    onOpenChange(false);
  };

  const validate = (text: string) => {
    const result = validateSkillContent(text);
    setErrors(result.errors);
    setParsed(result.parsed ?? null);
    if (result.ok) setStep('preview');
    return result.ok;
  };

  const readFile = async (file: File) => {
    const text = await file.text();
    setContent(text);
    validate(text);
  };

  const install = async (overwrite: boolean, name?: string) => {
    setBusy(true);
    setServerError(null);
    try {
      const body = name && parsed ? renderSkillText({ ...parsed, name }) : content;
      const result = await onInstall({ content: body, overwrite, ...(name ? { name } : {}) });
      if (result.status === 'conflict') {
        setRenameTo(`${parsed?.name ?? result.name} (copy)`);
        setStep('conflict');
        return;
      }
      onInstalled();
      close();
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'The skill could not be installed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
        else onOpenChange(true);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import a skill</DialogTitle>
          <DialogDescription>
            Choose a <span className="ltr-island">.dream-skill.txt</span> file or paste its
            contents. Skills are validated before they are installed.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="flex flex-col gap-4">
          {(errors.length > 0 || serverError) && (
            <div
              role="alert"
              className="flex gap-2 rounded-md border border-danger-fg bg-danger-bg px-3 py-2 text-caption text-danger-fg"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <ul className="flex flex-col gap-1">
                {serverError && <li>{serverError}</li>}
                {errors.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            </div>
          )}

          {step === 'source' && (
            <>
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,text/plain"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void readFile(file);
                    event.target.value = '';
                  }}
                />
                <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>
                  <FileUp aria-hidden />
                  Choose file…
                </Button>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="skill-paste" className="text-caption font-medium">
                  Or paste the skill
                </label>
                <textarea
                  id="skill-paste"
                  rows={10}
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  placeholder={'name: weekly report\ndescription: …\nsteps:\n- first step'}
                  className="selectable ltr-island min-h-44 w-full resize-y rounded-md border border-border-default bg-canvas p-2.5 text-code text-fg-primary"
                />
              </div>
            </>
          )}

          {step === 'preview' && parsed && (
            <div className="flex flex-col gap-3">
              <dl className="flex flex-col gap-1 text-caption">
                <div className="flex gap-2">
                  <dt className="text-fg-muted">Name</dt>
                  <dd className="font-medium">{parsed.name}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-fg-muted">Steps</dt>
                  <dd className="tabular">{parsed.steps.length}</dd>
                </div>
              </dl>
              <SkillCode content={content} className="max-h-64" />
            </div>
          )}

          {step === 'conflict' && (
            <div className="flex flex-col gap-3">
              <p className="text-body text-fg-secondary">
                A skill named <strong>{parsed?.name}</strong> already exists. Overwrite it, install
                under a different name, or cancel.
              </p>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="skill-rename" className="text-caption font-medium">
                  New name
                </label>
                <input
                  id="skill-rename"
                  value={renameTo}
                  onChange={(event) => setRenameTo(event.target.value)}
                  className="selectable h-8 w-full rounded-md border border-border-default bg-canvas px-2 text-body"
                />
              </div>
            </div>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="secondary" onClick={close} disabled={busy}>
            Cancel
          </Button>

          {step === 'source' && (
            <Button variant="primary" disabled={!content.trim()} onClick={() => validate(content)}>
              Validate
            </Button>
          )}

          {step === 'preview' && (
            <>
              <Button variant="secondary" onClick={() => setStep('source')} disabled={busy}>
                Back
              </Button>
              <Button variant="primary" disabled={busy} onClick={() => void install(false)}>
                <Upload aria-hidden />
                {busy ? 'Installing…' : 'Install'}
              </Button>
            </>
          )}

          {step === 'conflict' && (
            <>
              <Button
                variant="secondary"
                disabled={busy || !renameTo.trim()}
                onClick={() => void install(false, renameTo.trim())}
              >
                Install as new name
              </Button>
              <Button variant="destructive" disabled={busy} onClick={() => void install(true)}>
                Overwrite
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
