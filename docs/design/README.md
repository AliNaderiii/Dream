# Dream — Phase 0 Design Package (Prompt P-00)

Complete UI/UX design package for the Dream desktop application (Tauri 2 + React + Tailwind + Shadcn/ui target). Design-only: no product code was changed.

## 🎬 Start here

**Interactive hi-fi prototype:** open [`prototype/index.html`](prototype/index.html) in a browser
(or `python3 -m http.server -d docs/design` → http://localhost:8000/prototype/).
Top bar toggles: **Light/Dark · EN-LTR/فارسی-RTL · Comfortable/Compact · Happy/Empty/Loading/Error**, plus "Replay onboarding" and "Trigger approval". Resize below 768 px for the mobile gateway layout.

## Contents

| Path | Deliverable | Gate |
| --- | --- | --- |
| `research.md` | Personas (4), current-state audit, reference & competitor study, workflow inventory | G1 ✅ |
| `user-flows/` | Primary, project/memory/subagent, data science, settings + mobile + RTL flows (Mermaid) | G2 ✅ |
| `wireframes/` | 17 lo-fi SVG wireframes + `generate.py` | G3 ✅ |
| `design-system.md` | "Rooya" design system: color, type (Inter+Vazirmatn), spacing, elevation, motion, components | G4 ✅ |
| `tokens/dream.tokens.json` | Tokens Studio / Figma-importable token file (Light + Dark themes) | G4 ✅ |
| `tokens/dream.css` | CSS custom properties (drop-in for Tailwind v4) — used by the prototype | G4 ✅ |
| `prototype/` | Interactive hi-fi prototype (9 core screens, both themes, RTL, states) | G5–G6 ✅ |
| `animation-specs.md` | Micro-interactions, transitions, streaming, approval sheet motion | G6 ✅ |
| `accessibility-audit.md` | WCAG 2.1 AA audit with measured contrast + RTL verification checklist | G7–G8 ✅ |
| `figma-link.txt` | Figma import path (cloud not reachable from sandbox) | — |
| `approval-signoff.md` | Gate ledger + client sign-off checklist | G9 ⬜ |

Phase tracking: [`../../MASTER_CHECKLIST.md`](../../MASTER_CHECKLIST.md).

## Design headlines

- **Honest agent UI** — tool calls, risk tiers (safe/guarded/dangerous, never color-only), network status, and provenance are visible primitives.
- **Two scripts, one rhythm** — Inter + Vazirmatn co-primary; RTL is structural (logical properties, LTR islands for code/paths), fixing the Tkinter-era RLM hacks.
- **Approval as a calm sheet** above the composer (Deny / Allow once / Always allow), replacing the old flat refusal of dangerous tools.
- **House pattern:** destructive bulk actions are always dry-run → report → owner accepts (inherited from `desktop.py` M26).
- **Every screen** designs empty, loading, streaming, error, offline states.
