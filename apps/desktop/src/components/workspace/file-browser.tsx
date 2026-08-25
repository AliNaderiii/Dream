import { FileText, Folder } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import type { WorkspaceEntry } from '@/lib/bridge/workspace';

export function FileBrowser({
  entries,
  onOpen,
  onPreview,
  onCopyPath,
}: {
  entries: WorkspaceEntry[];
  onOpen: (entry: WorkspaceEntry) => void;
  onPreview: (entry: WorkspaceEntry) => void;
  onCopyPath: (entry: WorkspaceEntry) => void;
}) {
  const { t } = useTranslation('workspace');
  const [menu, setMenu] = useState<string | null>(null);

  if (!entries.length) {
    return <p className="text-body text-fg-muted">{t('browser.empty')}</p>;
  }

  return (
    <ul className="flex flex-col gap-1" aria-label={t('browser.title')}>
      {entries.map((entry) => (
        <li key={entry.path} className="relative">
          <div className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-surface-2">
            {entry.is_dir ? (
              <Folder className="size-4 shrink-0" aria-hidden />
            ) : (
              <FileText className="size-4 shrink-0" aria-hidden />
            )}
            <button
              type="button"
              className="min-w-0 flex-1 truncate text-start text-body"
              onClick={() => (entry.is_dir ? onOpen(entry) : onPreview(entry))}
            >
              {entry.name}
            </button>
            <span className="text-micro text-fg-muted">{entry.type}</span>
            <Button
              variant="ghost"
              size="sm"
              aria-haspopup="menu"
              aria-expanded={menu === entry.path}
              onClick={() => setMenu(menu === entry.path ? null : entry.path)}
            >
              {t('browser.menu')}
            </Button>
          </div>
          {menu === entry.path && (
            <div
              role="menu"
              className="absolute end-2 z-10 mt-1 flex flex-col rounded-md border border-border-default bg-overlay p-1 shadow-e2"
            >
              <button
                type="button"
                role="menuitem"
                className="px-3 py-1 text-start text-caption"
                onClick={() => onPreview(entry)}
              >
                {t('browser.preview')}
              </button>
              <button
                type="button"
                role="menuitem"
                className="px-3 py-1 text-start text-caption"
                onClick={() => onCopyPath(entry)}
              >
                {t('browser.copyPath')}
              </button>
              <button
                type="button"
                role="menuitem"
                className="px-3 py-1 text-start text-caption"
                onClick={() => onOpen(entry)}
              >
                {t('browser.open')}
              </button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
