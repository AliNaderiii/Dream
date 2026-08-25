# Workspace, projects, and agent modes

Dream’s workbench is a **local-first workspace**. A project points at a real folder on disk. Importing a folder registers that path; the files stay where they are.

## Import a folder in place

1. Open **Workspace** (or **Projects** → New project).
2. Choose the folder. Leave **Import folder in place** checked if you want a pointer, not a copy.
3. The file tree shows the real contents. Edit a file on disk and it appears here.

Nothing is copied. A badge reads **In place — never copied**.

## File browser and preview

- Click a file to preview it. CSV and TSV show a table and a bar chart from the same rows.
- HTML is shown with scripts removed. Notebooks are text-only and are never executed.
- The context menu copies the path or opens a nested folder.
- Large folders load a page at a time.

## Agent modes

On **Agents**:

- **/plan** (Persian `/برنامه`) drafts a plan. Press **Continue** to execute.
- **/goal** (Persian `/هدف`) takes an objective and one acceptance criterion per line. If a criterion needs the network or other off capabilities, the report says **could not meet …**.
- **/stop** (Persian `/توقف`) cancels the running turn. The badge shows live server state, not a stuck spinner.

The side panel lists live subagents with their latest action and progress.

## Chat references

In the composer you can type:

- `@sales.csv` — attach or summarise a workspace file
- `#sess_…` — point at another conversation
- `/plan` `/goal` `/stop` `/status` — command palette
- `!ls` — propose a sandboxed shell command (approval-gated, network off)

## Keyboard

See the shortcuts appendix. From the command palette (`⌘ K` / `Ctrl K`) search **Workspace** or **Agents**.
