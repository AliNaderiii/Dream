/** Recursive binary split renderer with constrained pointer resizing. */

import { useRef } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

import { Pane } from '@/components/panes/pane';
import type { LayoutNode } from '@/stores/use-layout-store';
import { useLayoutStore } from '@/stores/use-layout-store';
import { cn } from '@/utils/cn';

const MIN_WIDTH = 300;
const MIN_HEIGHT = 200;

interface SplitLayoutProps {
  node: LayoutNode;
  activePaneId: string;
}

export function SplitLayout({ node, activePaneId }: SplitLayoutProps) {
  const resizeSplit = useLayoutStore((state) => state.resizeSplit);
  const splitRef = useRef<HTMLDivElement>(null);

  if (node.kind === 'pane') {
    return <Pane pane={node.pane} active={node.pane.id === activePaneId} />;
  }

  const horizontal = node.direction === 'horizontal';

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const container = splitRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const size = horizontal ? rect.width : rect.height;
    const minimum = horizontal ? MIN_WIDTH : MIN_HEIGHT;
    const minRatio = size >= minimum * 2 ? minimum / size : 0.1;
    const maxRatio = 1 - minRatio;

    const onMove = (moveEvent: PointerEvent) => {
      const position = horizontal ? moveEvent.clientX - rect.left : moveEvent.clientY - rect.top;
      resizeSplit(node.id, Math.min(maxRatio, Math.max(minRatio, position / size)));
    };
    const finish = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', finish);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = horizontal ? 'col-resize' : 'row-resize';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', finish, { once: true });
  };

  return (
    <div
      ref={splitRef}
      className={cn('flex size-full min-h-0 min-w-0', horizontal ? 'flex-row' : 'flex-col')}
      data-split-id={node.id}
    >
      <div
        className="min-h-0 min-w-0 overflow-hidden"
        style={{ flexBasis: `${node.ratio * 100}%`, flexGrow: 0, flexShrink: 1 }}
      >
        <SplitLayout node={node.first} activePaneId={activePaneId} />
      </div>
      <div
        role="separator"
        aria-orientation={horizontal ? 'vertical' : 'horizontal'}
        aria-label="Resize panes"
        onPointerDown={startResize}
        className={cn(
          'group relative z-10 shrink-0 bg-border-default transition-colors hover:bg-accent',
          horizontal ? 'w-1 cursor-col-resize' : 'h-1 cursor-row-resize',
        )}
      >
        <span
          className={cn(
            'absolute bg-accent opacity-0 transition-opacity group-hover:opacity-100',
            horizontal ? '-inset-x-0.5 inset-y-0' : 'inset-x-0 -inset-y-0.5',
          )}
        />
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <SplitLayout node={node.second} activePaneId={activePaneId} />
      </div>
    </div>
  );
}
