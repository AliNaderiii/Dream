# UI Stage F — design, accessibility, and mission close-out

- Date: 2026-08-22
- Branch: `arena/01a02863-dream` (Arena-fixed)
- Review PR: #74

## Delivered design handoff

- [`../design/visual-language.md`](../design/visual-language.md) — implemented calm/precise/trustworthy direction, three-theme rationale, semantic visual grammar, motion philosophy, and deliberate restraint rules.
- [`../design/figma-handoff.md`](../design/figma-handoff.md) — exact Tokens Studio import/export round trip, ordered sets/themes, designer/engineer ownership, proposal requirements, and repository-first source-of-truth policy.
- [`../design/accessibility-audit-v2.md`](../design/accessibility-audit-v2.md) — implementation audit with before/after contrast, keyboard, ARIA, RTL, reduced-motion, virtualization, five-surface axe, and honest manual native-screen-reader follow-ups.
- [`UI-E.md`](./UI-E.md) — Stage E implementation, test-edit audit, budgets, warning triage, and handoff evidence.
- [`UI-GATES.md`](./UI-GATES.md) — cumulative exact Gate A–F command evidence.

The design package remains code- and token-based. No binary design artifact was introduced.

## Source-rendered screenshot/reference manifest

These references replace stale binary screenshots with reproducible renders from the same source shipped to users.

| Reference          | Source                                                           | State or axes to capture                                                                                                        | Purpose                                |
| ------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Phase-0 comparison | `docs/design/prototype/index.html`                               | Light/Dark, EN-LTR/FA-RTL, comfortable/compact, happy/empty/loading/error                                                       | Original design baseline               |
| Primitive matrix   | `apps/desktop/src/stories/ui.stories.tsx` via Ladle              | Buttons, badges, inputs, cards, skeletons, dialogs, dropdowns, tooltips, tabs, switches, toasts, empty states, command palettes | Component visual review                |
| Theme matrix       | `apps/desktop/src/stories/theme-matrix.tsx`                      | Light/Warm/Dark × LTR/RTL × comfortable/dense                                                                                   | Theme and mirroring review             |
| DOM snapshots      | `apps/desktop/src/stories/__snapshots__/ui.visual.test.tsx.snap` | Top 30 primitive states                                                                                                         | Reviewable visual-structure regression |
| Session manager    | `/` in the Tauri/Vite app                                        | empty/loading/error/offline and 1,000-row fixture tests                                                                         | Stage D operational state              |
| Memory explorer    | `/memory`                                                        | list/timeline, score explanation, Persian RTL                                                                                   | Explainability and mixed direction     |
| Skills manager     | `/skills`                                                        | empty/loading/error/offline, import conflict, optimistic rollback                                                               | Operational recovery                   |
| Subagents          | `/subagents`                                                     | empty/loading/error/offline, live detail/log, council                                                                           | Lifecycle and bounded live output      |
| Scheduler          | `/scheduler`                                                     | bilingual preview, three Gregorian/Jalali rows, history, approval denial                                                        | Calendar and fail-closed state         |
| Transcript         | `/chat/:sessionId`                                               | 120/500-row virtual fixtures and active streaming row                                                                           | Variable-height bounded chat           |

Reviewers can run `npm run storybook` for the reference catalog or `npm run dev` for routes. The handoff records source paths and exact state axes so a new capture is tied to a commit and cannot silently drift from implementation.

## Definition-of-Done mapping

| Requirement                                                | Evidence                                      | Status                                             |
| ---------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------- |
| 3 themes × LTR/RTL × 2 densities                           | Ladle `ThemeMatrix`; theme tests              | Complete                                           |
| Persistent zoom 80–150%                                    | appearance store + document snapshot tests    | Complete                                           |
| Palette <100ms                                             | JSON performance report and app-shell guard   | Complete                                           |
| Five operational surfaces, all lifecycle states            | Stage D route/component/offline suites        | Complete                                           |
| Chat/session/log/history virtualization                    | 120/500/1,000-row fixtures, all <60 mounted   | Complete                                           |
| Every chunk <500kB; entry <250kB gzip                      | Vite build + perf report                      | Complete                                           |
| Light muted ≥5:1; other normal text ≥4.5:1                 | 108-check token validator                     | Complete                                           |
| Persian fallback count zero                                | locale gate                                   | Complete                                           |
| Perf report in CI                                          | Desktop CI artifact step                      | Complete                                           |
| axe clean on all five surfaces                             | accessibility gate                            | Complete                                           |
| Reduced motion on required surfaces                        | OS/manual and six-surface source-policy tests | Complete                                           |
| No telemetry, network analytics, or protocol change        | diff review and protected-path check          | Complete                                           |
| `dream/` and Python `tests/` untouched                     | final `git diff --stat -- dream/ tests/`      | Complete                                           |
| Native NVDA/Narrator, VoiceOver, forced-colors manual pass | audit-v2 remaining manual verification        | Release-environment follow-up; not falsely claimed |

## Truthful checklist and product documentation updates

`MASTER_CHECKLIST.md` marks only implemented Phase-2 items. Conversation, session, skills, and subagent dashboard items are complete. The combined memory/reminders item remains open because reminder authoring is not implemented; the combined scheduler edit item remains open because existing schedules do not yet expose a full edit flow.

`CHANGELOG.md` documents user-facing UI, performance, localization, accessibility, and offline/retry improvements under Unreleased. The top-level README desktop section now describes Light/Warm/Dark, RTL/density/zoom, bounded transcripts, accessibility gates, and the CI performance report without claiming native assistive-technology certification.

## Architecture boundary

The Stage E/F patch changes desktop UI, design/handoff docs, and CI only. It consumes protocol v3.16. It does not change the Python kernel, bridge protocol, metering, ledger logic, or Python tests.

## Gate decision

```text
stage_f_documents=PASS
protected_paths=PASS
diff_check=PASS
```

The final Gate E and Gate F blocks in `UI-GATES.md` contain the completed 505-test desktop run, 1,748/11 Python run, static/build/Ladle/performance/accessibility evidence, documentation checks, protected-path output, and orchestrator diff review.

**Gate F: GREEN.**
