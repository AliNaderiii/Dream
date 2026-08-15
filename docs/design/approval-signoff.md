# Phase 0 — Design Approval & Sign-off (Gate G9)

Repo: AliNaderiii/Dream · Branch: `arena/01a005c5-dream` · Date prepared: 2026-08-15

## Gate ledger

| Gate | Description | Owner | Evidence | Status |
| --- | --- | --- | --- | --- |
| G1 | Research complete — personas, competitor analysis, workflows | UXR | `research.md` | ✅ Passed |
| G2 | Flows approved — 6 flows incl. mobile + RTL | DPM | `user-flows/` (4 docs, Mermaid diagrams) | ✅ Passed |
| G3 | Wireframes approved — 17 screens | DPM | `wireframes/` (SVG + generator + README) | ✅ Passed |
| G4 | Design system complete — tokens, components, dual-script type | UID | `design-system.md`, `tokens/dream.tokens.json`, `tokens/dream.css` | ✅ Passed |
| G5 | Mockups approved — hi-fi, light + dark | DPM | `prototype/` (live hi-fi screens stand in for static mockups; both themes, live toggle) | ✅ Passed* |
| G6 | Prototype functional — click-through of main flows | IMD | `prototype/index.html` — chat/streaming/approval/memory/subagents/provenance/data/settings/onboarding; automated smoke test passed | ✅ Passed |
| G7 | Accessibility — WCAG 2.1 AA, contrast measured, keyboard designed | UXR | `accessibility-audit.md` §1–6 (2 token corrections applied) | ✅ Passed |
| G8 | RTL verified — mirroring + overflow + LTR islands | UID | `accessibility-audit.md` §7; prototype فارسی toggle; wireframe 3.17 | ✅ Passed |
| G9 | Final client sign-off | DPM | this document | ⬜ **Awaiting client** |

\* G5 note: Figma being unreachable from the sandbox, the client-approved substitution (option "code-based design package") delivers hi-fi mockups as a live token-driven prototype plus Tokens Studio-importable JSON; `figma-link.txt` documents the import path for when a Figma mirror is created.

## Scope delivered vs. deferred

**Delivered in full:** research, 6 flow maps, 17 wireframes, complete token system (2 themes), component specs mapped to Shadcn/ui, motion specs, a11y audit with measured contrast, RTL verification, interactive prototype of the 9 core screens with light/dark × EN/FA-RTL × comfortable/compact × happy/empty/loading/error state matrix, responsive mobile behavior, onboarding flow.

**Deferred to P-01+ (documented, low risk):** static per-screen PNG exports of hi-fi mockups (prototype is the source); prototype coverage of skills manager, MCP config, file browser, project dashboard beyond wireframe level; Figma cloud mirror; audit open items in `accessibility-audit.md` §8.

## Sign-off checklist (client)

- [ ] Personas and workflows reflect intended users (incl. Persian-first use)
- [ ] Conversation turn anatomy (context chip / tool cards / approval sheet) approved
- [ ] Rooya palette, Inter + Vazirmatn typography, spacing/radius/motion tokens approved
- [ ] Risk-tier visual language (safe/guarded/dangerous, never color-only) approved
- [ ] Light + dark themes approved as shown in prototype
- [ ] RTL Persian mirroring approved as shown in prototype
- [ ] Mobile gateway direction (reduced command set, approvals-first) approved
- [ ] Deferred-scope list accepted

**Client signature:** ______________________  **Date:** ____________

> Per P-00 §7: once G9 is signed, Prompt P-01 (Desktop Shell — Tauri 2 + React + Tailwind + Shadcn/ui) may begin. The token files and prototype are the implementation contract; frontend must match within reason.
