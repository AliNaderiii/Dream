# UI-A — Token and theme foundation

**Date:** 2026-08-22  
**Stage owners:** LUMEN (design systems), MASON (UI platform)  
**Branch:** `arena/01a02863-dream`

## Outcome

Gate A passed. Rooya 2 now has one repository-owned Tokens Studio v2 source, a canonical CSS export imported directly by the desktop app, 3 complete themes, 4 accents, density, UI zoom, Persian numerals, and both OS/in-app reduced motion.

## Decisions made to preserve trust

- `system` resolves to Light/Dark because operating systems expose light/dark, not a “warm” preference. Warm is an explicit persistent selection.
- The repository's actual locale generator is `apps/desktop/scripts/generate-locales.mjs` (not the stale root path in the brief). It remains the only writer of all eight locale trees.
- English fallback is explicit and produces `src/locales/TODO-i18n.md`. English and Persian are complete; the six other locales have identical generated key trees and clearly reported fallback leaves.
- Arena fixes this session to one branch. Instead of unsafe parallel PR branches, stages are isolated as reviewable commits on the required branch and the final PR links every handoff.

## Files and implementation

- `docs/design/tokens/dream.tokens.json`: DTCG `$type`/`$value`, `$themes`, `$metadata.tokenSetOrder`, 12 theme/accent combinations.
- `docs/design/tokens/dream.css`: canonical runtime aliases for color, type, spacing, shape, depth, motion, density, layering, and shell geometry.
- `apps/desktop/src/styles/theme.css`: Tailwind semantic bridge importing canonical tokens; no app color literals.
- `use-app-store.ts`, `use-theme.ts`, `main.tsx`: persisted Warm/accent/dense/80–150 zoom/motion/numerals, legacy compact migration, synchronous pre-paint root attributes.
- `settings.tsx` + generated locale settings files: complete appearance controls with English/Persian copy.
- `validate-tokens.mjs`: structural alias/theme validation plus 108 WCAG AA checks.
- `visual-language.md`, `design-system.md`: Rooya 2 direction and implementation contract.

## Gate evidence

- Tokens Studio structure: `npm run tokens:check` → **12 sets, 12 themes, 108 AA checks; pass**.
- Lowest measured required contrast: **4.68:1** (Light muted text on canvas).
- Raw hex in `apps/desktop/src`: **0**.
- TypeScript: `npm run typecheck` → pass.
- ESLint: `npm run lint` → 0 errors (11 pre-existing warnings).
- Prettier: `npm run format:check` → pass.
- Vitest: **43 files, 377 tests passed** (baseline was 42/373).
- Vite production build: pass.

The test runner still emits pre-existing React `act()` diagnostics from asynchronous legacy route tests; they are warnings and no assertion failed.
