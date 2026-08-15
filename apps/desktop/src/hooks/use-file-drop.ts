/**
 * Drag-and-drop file detection.
 *
 * Tauri delivers OS drag-drop as a webview event carrying real filesystem paths;
 * those paths are validated in Rust before reaching the callback. In a plain
 * browser the hook stays inert, since paths are not available there.
 */

import { useEffect, useState } from 'react';
import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow';

import { dialogApi } from '@/lib/tauri';
import type { FileEntry } from '@/types';
import { isTauri } from '@/utils/platform';

interface FileDropResult {
  /** True while files are hovering over the window. */
  isDragging: boolean;
  /** Entries from the most recent drop that passed validation. */
  droppedFiles: FileEntry[];
  /** Number of paths rejected by validation in the most recent drop. */
  rejectedCount: number;
  /** Clears the last drop result. */
  clear: () => void;
}

/**
 * Subscribes to native drag-drop events.
 *
 * @param onDrop - optional callback fired with the validated entries.
 */
export function useFileDrop(onDrop?: (files: FileEntry[]) => void): FileDropResult {
  const [isDragging, setIsDragging] = useState(false);
  const [droppedFiles, setDroppedFiles] = useState<FileEntry[]>([]);
  const [rejectedCount, setRejectedCount] = useState(0);

  useEffect(() => {
    if (!isTauri()) return;

    let unlisten: (() => void) | undefined;
    let cancelled = false;

    void getCurrentWebviewWindow()
      .onDragDropEvent((event) => {
        if (event.payload.type === 'over' || event.payload.type === 'enter') {
          setIsDragging(true);
          return;
        }
        if (event.payload.type === 'leave') {
          setIsDragging(false);
          return;
        }
        if (event.payload.type === 'drop') {
          setIsDragging(false);
          const paths = event.payload.paths;
          // Validation happens in Rust; the listener itself must stay synchronous.
          void dialogApi.validatePaths(paths).then((valid) => {
            setDroppedFiles(valid);
            setRejectedCount(paths.length - valid.length);
            onDrop?.(valid);
          });
        }
      })
      .then((un) => {
        if (cancelled) un();
        else unlisten = un;
      });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [onDrop]);

  return {
    isDragging,
    droppedFiles,
    rejectedCount,
    clear: () => {
      setDroppedFiles([]);
      setRejectedCount(0);
    },
  };
}
