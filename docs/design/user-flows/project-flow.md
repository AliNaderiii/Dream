# Flow 2 — Project, Memory & Subagent Flow (Gate G2)

`Create project → add memory → spawn subagent → review output`

Owner: UXR · Reviewed & approved: DPM 2026-08-15

## 2.1 Create project and attach context

```mermaid
flowchart TD
    A[Sidebar → Projects → New project] --> B[Name + optional description\n+ instructions memory]
    B --> C[Project dashboard\nfiles · sessions · project memory tabs]
    C --> D[Add files: drag-drop or picker\n→ file browser rows with type icons]
    C --> E[Add memory: quick-add field\nkind selector semantic/episodic/procedural\nimportance slider]
    E --> F[Memory appears in project memory list\nwith normalized-form indicator if Persian]
    C --> G[Start session inside project\n→ conversation pre-scoped to project context]
```

## 2.2 Memory explorer (global and per-project)

```mermaid
flowchart LR
    A[Memory explorer] --> B[Search box\nnormalization-aware\nshows 'matched via normalized form']
    A --> C[Filter: kind / tag / importance / date]
    A --> D[List virtualized\nkind badge + content + age + usage]
    D --> E[Detail panel: full text, tags,\nimportance, retrieval stats,\n'turns that used this memory']
    E --> F[Edit / Pin importance / Delete]
    A --> G[Timeline view: episodic memories\non Jalali+Gregorian dual axis]
    A --> H[Dedupe: dry-run → report modal\npairs listed → owner accepts → apply]
```

House rule (from `desktop.py` M26): **every destructive bulk action is dry-run first** — report → explicit acceptance → apply → list redraws from store.

## 2.3 Spawn and review a subagent

```mermaid
sequenceDiagram
    actor U as User
    participant C as Conversation
    participant M as Subagent monitor
    participant S as Subagent

    U->>C: "Research X in the background" (or /spawn)
    C->>M: chip in transcript "Subagent #3 started" + rail badge count
    U->>M: opens monitor (rail icon or chip click)
    M->>U: dashboard cards: name, goal, status, elapsed,\ntokens, last activity line
    U->>S: open card → live log pane (tool calls + text)
    alt user cancels
        U->>S: Cancel → confirm → status "cancelled", partial log kept
    end
    S->>M: status "finished" + output summary
    M->>U: Review screen: output, artifacts, provenance link
    U->>C: Accept → result posted into parent conversation\nas a quoted, attributed block
```

**States:** monitor empty state teaches the `/spawn` command; a failed subagent card shows the failing tool call directly; all logs persist to run history.

## Acceptance (Gate G2 slice)

- A memory added in a project is retrievable from a project session immediately and visibly attributed in the context chip.
- Subagent status is glanceable (rail badge) without opening the monitor.
- Accepting subagent output records provenance linking parent turn ↔ subagent run.
