import type { ReactNode } from 'react';

const THEMES = ['light', 'warm', 'dark'] as const;
const DIRECTIONS = ['ltr', 'rtl'] as const;
const DENSITIES = ['comfortable', 'dense'] as const;

export const MATRIX_SIZE = THEMES.length * DIRECTIONS.length * DENSITIES.length;

/** Every primitive story renders all required visual-system axes side by side. */
export function ThemeMatrix({ children }: { children: ReactNode }) {
  return (
    <div className="grid gap-3 bg-canvas p-3 xl:grid-cols-2">
      {THEMES.flatMap((theme) =>
        DIRECTIONS.flatMap((direction) =>
          DENSITIES.map((density) => (
            <section
              key={`${theme}-${direction}-${density}`}
              data-theme={theme}
              data-accent="violet"
              data-density={density}
              dir={direction}
              lang={direction === 'rtl' ? 'fa' : 'en'}
              data-testid="theme-cell"
              className="min-w-0 rounded-xl border border-border-default bg-canvas p-4 font-sans text-fg-primary"
            >
              <p className="mb-3 text-micro font-semibold text-fg-muted">
                {theme} · {direction} · {density}
              </p>
              {children}
            </section>
          )),
        ),
      )}
    </div>
  );
}
