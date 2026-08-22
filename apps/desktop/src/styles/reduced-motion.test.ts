import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

function source(relativePath: string): string {
  return readFileSync(path.resolve(relativePath), 'utf8');
}

describe('reduced-motion coverage', () => {
  it('halts motion for every required animated interaction surface', () => {
    const theme = source('src/styles/theme.css');
    expect(theme).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{\s*\*,[\s\S]*?animation-iteration-count: 1 !important;[\s\S]*?transition-duration: 0\.01ms !important;/,
    );

    const representatives: Array<[string, string, RegExp]> = [
      ['streaming', 'src/components/chat/virtual-message-list.tsx', /streaming-sweep/],
      ['palette', 'src/components/shared/command-palette.tsx', /motion-enter/],
      ['dialogs', 'src/components/ui/dialog.tsx', /motion-enter/],
      ['pane-resize', 'src/components/panes/split-layout.tsx', /transition-(?:colors|opacity)/],
      ['toast', 'src/components/ui/toast.tsx', /motion-enter/],
      ['tooltips', 'src/components/ui/tooltip.tsx', /motion-enter/],
    ];

    for (const [surface, file, motionPattern] of representatives) {
      expect(source(file), surface).toMatch(motionPattern);
    }
    console.info(
      'reduced_motion_surfaces=streaming,palette,dialogs,pane-resize,toast,tooltips status=PASS',
    );
  });
});
