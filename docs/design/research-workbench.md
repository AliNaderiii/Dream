# Research Workbench — Design Specification

**Phase**: P2  
**Status**: Complete  
**Owner**: Agent-U (Frontend Lead)  

## Overview

The Research & Analysis workbench is Dream's autonomous data-science interface. It transforms the P1 research engine into a visible, auditable, beautiful experience — a live execution trace paired with a polished analyst-report viewer.

## Design Principles

1. **Trust through transparency**: Every number links to its source run. Claims have evidence. Tool calls show args and results.
2. **Beauty first**: This is a deliverable-grade UI. Sessions look like research papers, not dashboards.
3. **No-hang, no-surprises**: Streaming never stalls silently. Stop truly stops. Errors are recoverable.
4. **RTL-native**: Persian is a first-class citizen. Logical properties, mirrored layouts, proper line-height.
5. **Motion-respectful**: Every animation honors `prefers-reduced-motion`.

## Views

### 1. Session List (default view)

- Cards showing: topic, status badge, progress, dates, section count, claim count, model route
- "New Research" button (primary, top-right)
- Empty state with Microscope icon

### 2. Research Composer

- Topic input (text, 500 char max)
- Objective textarea (2000 char max)
- Data source picker (add/remove)
- Depth selector (simple/deep) — radio cards
- Model/route picker — dropdown with privacy sentence
- Cost estimate panel (tokens, USD, duration, breakdown)
- Start button (primary) + Cancel

### 3. Plan Approval

- Topic & objective summary
- Research questions (ordered list)
- Hypotheses (bulleted list)
- Methodology (paragraph)
- Outline tree (collapsible)
- Estimated cost/tokens
- Approve / Modify / Cancel buttons
- Inline editor on Modify (dialog-style)

### 4. Live Trace

- Overall progress bar + ETA
- Section timeline (mini progress bars per phase)
- Stop button (danger-red, prominent)
- Step cards (collapsible):
  - Phase icon (color-coded)
  - Title + status badge
  - Elapsed time, tokens, cost
  - Expandable: output, tool calls, error details
- Stale detection (15s heartbeat timeout → warning + restart)
- Trace inspector side panel (toggleable)

### 5. Report Viewer

- Three tabs: Report | Figures | Integrity
- Export bar (MD, PDF, ZIP, provenance JSON)
- Report: sanitized markdown rendering
- Figures: grid gallery with lightbox
- Integrity: claims-evidence cards with code snippets

## Color Coding

### Phase Icons
- Analyze: blue (Search)
- Plan: violet (Map)
- Discover: teal (FileSearch)
- Code: amber (Code2)
- Execute: green (PlayCircle)
- Observe: orange (Eye)
- Evidence: pink (Lightbulb)
- Section: indigo (Braces)

### Status Badges
- Pending: neutral (Clock)
- Running: accent (Loader2, spinning)
- Done: success (CheckCircle2)
- Failed: danger (XCircle)
- Blocked: warning (PauseCircle)

### Risk Tiers
- Safe: green (Shield)
- Caution: amber (ShieldAlert)
- Danger: red (AlertTriangle)

## Accessibility

- All interactive elements keyboard-navigable
- `aria-live=polite` on trace updates
- `aria-expanded` on collapsible cards
- `role="progressbar"` on progress bars
- `role="dialog"` on plan editor
- Focus management: plan editor auto-focuses first field
- Color never sole signal (always paired with icon)

## Motion

- Step card transitions: 220ms `--ds-ease-standard`
- Progress bar: 220ms width transition
- Loader spin: 1s linear infinite
- All disabled under `prefers-reduced-motion: reduce`

## Responsive

- Trace inspector: side panel on ≥1024px, hidden toggle on smaller
- Figure gallery: 1 col mobile, 2 col tablet, 3 col desktop
- Session cards: full-width, stack metadata on small screens

## Security

- Markdown: scripts stripped, `javascript:` links neutralized
- Secrets: `sk-*`, `ghp_*`, `xox*`, `AKIA*`, `eyJ*` patterns redacted
- `dangerouslySetInnerHTML` only on sanitized output
- Tool call args: JSON-stringified then redacted before display
