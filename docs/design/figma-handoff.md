# Figma and Tokens Studio handoff

**Version 1.0 · 2026-08-22 · Owners: Product Design Systems + Desktop UI**

The repository, not a cloud file, is the source of truth. The canonical token document is [`tokens/dream.tokens.json`](./tokens/dream.tokens.json); [`tokens/dream.css`](./tokens/dream.css) is its reviewed runtime projection. No binary design asset is required to reproduce the system.

## Tokens Studio round trip

### Import from the repository into Figma

1. Check out the reviewed branch and run:

   ```bash
   cd apps/desktop
   npm ci
   npm run tokens:check
   ```

   Continue only when the validator reports 12 sets, 208 tokens, 12 themes, 108 contrast checks, and Light muted/canvas ≥5.0 for Violet, Ocean, Forest, and Ember.

2. Open the target Figma file and launch **Tokens Studio for Figma**.
3. In Tokens Studio, open **Settings → Import/Export** and choose **Import JSON** (single-file mode).
4. Select `docs/design/tokens/dream.tokens.json`. Choose **Replace** for a clean mirror. Use **Merge** only when reviewing a proposed delta and never make the merged Figma state authoritative by itself.
5. Confirm the imported set order is exactly:
   1. `core`
   2. `semantic/light`
   3. `semantic/warm`
   4. `semantic/dark`
   5. `accent/violet-light`
   6. `accent/violet-dark`
   7. `accent/ocean-light`
   8. `accent/ocean-dark`
   9. `accent/forest-light`
   10. `accent/forest-dark`
   11. `accent/ember-light`
   12. `accent/ember-dark`
6. Open **Themes** and confirm the `Dream` group contains 12 combinations: Light, Warm, and Dark × Violet, Ocean, Forest, and Ember. `core` must be `source`; one semantic set and one matching accent set must be enabled in each theme.
7. Apply tokens to Figma variables/styles by semantic name. Components bind to `color.text.*`, `color.surface.*`, `color.border.*`, `color.accent.*`, status, typography, spacing, radius, elevation, motion, control, and shell aliases—not palette literals.
8. Spot-check the Light/Violet, Warm/Forest, and Dark/Ember frames against the source-rendered reference matrix in `apps/desktop/src/stories/ui.stories.tsx`.

Tokens Studio screens can change labels between plugin releases; the required operation remains **single JSON import → replace clean mirror → verify 12 ordered sets and 12 Dream themes**.

### Export a reviewed proposal back to the repository

1. In Tokens Studio, export **all sets and themes** as one JSON document using the Tokens Studio schema, preserving aliases rather than resolving them to raw values.
2. Save the proposal outside the canonical path first, for example `/tmp/dream.tokens.proposal.json`.
3. Diff the proposal against `docs/design/tokens/dream.tokens.json`. Reject unexplained changes to `$schema`, `$themes`, `$metadata.tokenSetOrder`, token types, or aliases.
4. Copy only the approved changes into `dream.tokens.json` and make the equivalent runtime mapping in `dream.css`. Generated CSS is never edited without the token-source edit in the same change.
5. Run:

   ```bash
   cd apps/desktop
   npm run tokens:check
   npm run typecheck
   npm run storybook:build
   ```

6. Review Light/Warm/Dark in LTR/RTL and comfortable/dense modes. If color changed, paste the validator’s contrast output into the stage handoff.
7. Commit JSON, CSS, tests, and the proposal rationale together. Do not attach a `.fig`, screenshot binary, or plugin-local cache as the source of truth.

## Ownership map

| Area                              | Designer owns                                  | Engineer owns                                        | Joint approval required                             |
| --------------------------------- | ---------------------------------------------- | ---------------------------------------------------- | --------------------------------------------------- |
| Emotional direction and restraint | Intent, hierarchy, theme rationale             | Feasibility feedback                                 | Any change to calm/precise/trustworthy principles   |
| Semantic token model              | Naming proposal, usage semantics               | Alias graph, schema validity, CSS projection         | New semantic category or renamed public token       |
| Palette and contrast              | Visual candidate and contextual review         | Programmatic WCAG calculation                        | Any text/status/focus color change                  |
| Typography                        | Pairing, hierarchy, language rhythm            | Font loading, fallbacks, locale application          | Base size, line height, or script-specific behavior |
| Spacing/radius/elevation          | System rhythm                                  | Runtime utilities and responsive constraints         | New scale step                                      |
| Motion                            | Purpose and storyboard                         | CSS implementation, frame and reduced-motion budgets | New expressive pattern or duration                  |
| Components                        | Anatomy, states, content guidance              | Semantics, keyboard behavior, bridge lifecycle       | New primitive or changed interaction contract       |
| RTL and localization              | Reading/order review, translated-layout intent | Logical properties, `dir`/`lang`, normalized data    | Direction-specific exception                        |
| Performance/accessibility gates   | Review scenarios                               | Executable tests and CI artifact                     | Budget or threshold change                          |

## Proposing a new token

A token proposal must include:

1. **Problem:** which repeated semantic decision cannot be expressed by an existing token.
2. **Scope:** components, themes, states, directions, and densities affected.
3. **Name and type:** a semantic path and Tokens Studio `$type`; no component-specific raw-color alias unless it represents a stable product concept.
4. **Values and aliases:** values for every applicable theme/accent, preferring aliases to duplicate literals.
5. **Evidence:** reference frames or source-rendered Ladle states plus contrast/motion calculations where applicable.
6. **Migration:** old token users, CSS custom-property mapping, and compatibility impact.
7. **Tests:** validator update if the contract changed and representative component coverage.

The reviewer first asks whether an existing semantic token can solve the problem. A new token is accepted only when it removes repeated magic values or establishes a reusable meaning. One-off visual tuning remains a component composition of existing tokens.

## Reference surfaces

- Live design prototype: [`prototype/index.html`](./prototype/index.html)
- Implemented story matrix: `apps/desktop/src/stories/ui.stories.tsx`
- Theme/direction/density matrix: `apps/desktop/src/stories/theme-matrix.tsx`
- DOM visual contracts: `apps/desktop/src/stories/__snapshots__/ui.visual.test.tsx.snap`
- Runtime theme mapping: `apps/desktop/src/styles/theme.css`
- Gate evidence: [`../handoff/UI-GATES.md`](../handoff/UI-GATES.md)
