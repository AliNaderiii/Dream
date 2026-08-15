import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { Paperclip, Send, Square, X } from 'lucide-react';
import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';

import { cn } from '@/utils/cn';
import { isTauri } from '@/utils/platform';

export interface PendingAttachment {
  name: string;
  path?: string;
  type?: string;
}
const MAX_LENGTH = 100_000;

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: (attachments: PendingAttachment[]) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
}) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const element = textarea.current;
    if (!element) return;
    element.style.height = '0';
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
  }, [value]);

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    setAttachments((current) => [
      ...current,
      ...Array.from(files).map((file) => ({
        name: file.name,
        path: (file as File & { path?: string }).path,
        type: file.type,
      })),
    ]);
  };
  const submit = () => {
    if (!value.trim() || value.length > MAX_LENGTH || streaming || disabled) return;
    onSend(attachments);
    setAttachments([]);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  };
  const chooseFiles = async () => {
    if (!isTauri()) {
      fileInput.current?.click();
      return;
    }
    const selected = await openDialog({ multiple: true, directory: false });
    const paths = selected ? (Array.isArray(selected) ? selected : [selected]) : [];
    setAttachments((current) => [
      ...current,
      ...paths.map((path) => ({ name: path.split(/[\\/]/).pop() ?? path, path })),
    ]);
  };
  return (
    <div className="shrink-0 bg-gradient-to-t from-canvas via-canvas to-transparent px-4 pb-4 pt-2">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'mx-auto max-w-4xl rounded-xl border border-border-default bg-surface p-2 shadow-e1 transition-all duration-base focus-within:border-accent focus-within:shadow-e2',
          dragging && 'border-accent bg-accent-soft/40',
        )}
      >
        {!!attachments.length && (
          <div className="flex flex-wrap gap-1.5 p-1">
            {attachments.map((file, index) => (
              <span
                key={`${file.name}-${index}`}
                className="flex items-center gap-1 rounded-md bg-surface-2 px-2 py-1 text-caption"
              >
                📎 {file.name}
                <button
                  type="button"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => setAttachments((all) => all.filter((_, item) => item !== index))}
                >
                  <X className="size-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <input
            ref={fileInput}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => {
              addFiles(event.target.files);
              event.target.value = '';
            }}
          />
          <button
            type="button"
            aria-label="Attach files"
            title="Attach files"
            onClick={() => void chooseFiles()}
            className="rounded-md p-2 text-fg-muted hover:bg-surface-2 hover:text-fg-primary"
          >
            <Paperclip className="size-5" />
          </button>
          <textarea
            ref={textarea}
            rows={1}
            value={value}
            maxLength={MAX_LENGTH}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={disabled ? 'Bridge disconnected' : 'Message Dream…'}
            aria-label="Message Dream"
            className="selectable max-h-44 min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-body outline-none placeholder:text-fg-muted disabled:cursor-not-allowed"
          />
          {streaming ? (
            <button
              type="button"
              aria-label="Stop generation"
              onClick={onStop}
              className="rounded-md bg-danger-bg p-2 text-danger-fg hover:brightness-95"
            >
              <Square className="size-5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              aria-label="Send message"
              disabled={!value.trim() || disabled}
              onClick={submit}
              className="rounded-md bg-accent p-2 text-fg-inverse transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="size-5 rtl:rotate-180" />
            </button>
          )}
        </div>
        <div className="flex justify-between px-2 pt-1 text-micro text-fg-muted">
          <span>Enter to send · Shift+Enter for newline</span>
          <span className={cn(value.length > 90_000 && 'text-warning-fg')}>
            {value.length.toLocaleString()} / {MAX_LENGTH.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
}
