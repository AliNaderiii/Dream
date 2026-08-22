# UI-B — Component library and Ladle catalog

**Date:** 2026-08-22  
**Stage owners:** MASON (UI platform), FLUX (interaction), SCRIBE (catalog)  
**Branch:** `arena/01a02863-dream`

## Outcome

Gate B passed. The Shadcn-mappable library now covers the core control, form, surface, overlay, navigation, loading, switch, toast, and status primitives. All use Rooya semantic tokens and density-aware control dimensions.

## Implementation

- Button: five variants, sm/md/lg + icon, in-place no-shift loading state, safe Radix `asChild` behavior.
- New primitives: labelled Input/Textarea, Card family, Skeleton/SkeletonCard, keyboard Tabs, RTL Switch, semantic ToastViewport.
- Existing Dialog, Dropdown, and Tooltip now consume shared entrance behavior; Dialog close copy is localized and menus are height-bounded.
- Ladle 5 is a **development-only** dependency selected over Storybook to keep production runtime unchanged. `npm run storybook` serves it; `npm run storybook:build` verifies production catalog generation.
- `ui.stories.tsx` catalogs every primitive through the shared 3 themes × LTR/RTL × comfortable/dense matrix (12 cells per story).
- 30 committed DOM visual-contract snapshots protect the highest-value variants and states.
- axe-core runs in Vitest for representative interactive primitives. Token contrast remains a separate source-level check because jsdom has no paint engine.

## Gate evidence

- Ladle production build: **pass**, 13 catalog entries, 1.45 MiB static development assets (not shipped in Dream).
- Theme matrix smoke: **3 themes × 2 directions × 2 densities = 12 cells; pass**.
- Visual contracts: **30 snapshots committed; pass**.
- axe-core representative interactive primitive set: **0 violations**.
- Full Vitest: **47 files, 415 tests passed**.
- TypeScript / ESLint / Prettier / Vite build: pass (ESLint retains 11 pre-existing warnings, 0 errors).
- Runtime dependency delta: **0**; Ladle and axe-core are devDependencies only.

## Review note

The first full-suite run exposed a Radix Slot regression in the new loading wrapper. The stage was not closed until `asChild` again received one direct element and all existing data-workbench tests passed. No existing test was changed or weakened.
