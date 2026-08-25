# Workspace RPC

P4 is an add-only Dream Bridge extension. All methods use JSON-RPC object params and the `workspace.*` namespace. Existing `project.*` methods are unchanged.

Folders are imported **in place**: the registry stores a path pointer. Files are never copied.

## Methods

| Method | Params | Result |
|---|---|---|
| `workspace.roots_list` | `project_id?`, `session_id?` | `{roots, count}` |
| `workspace.roots_register` | `folder`, `name?`, `adopt_project?` | root + listing, `copied: false` |
| `workspace.roots_unregister` | `root_id` | `{deleted, root_id}` |
| `workspace.import_folder` | same as register | same |
| `workspace.files_list` | `root_id`, `path?`, `cursor?`, `limit?` | bounded entries |
| `workspace.files_stat` | `root_id`, `path` | metadata |
| `workspace.files_preview` | `root_id`, `path` | sanitized preview; CSV includes `chart` |
| `workspace.files_read` | `root_id`, `path` | bounded text |
| `workspace.project_adopt` | `folder`, `name?` | project + root, never copied |
| `workspace.project_settings` | `project_id`, `settings?` | settings (`default_mode`, `language`) |
| `workspace.project_move_session` | `project_id`, `session_id` | updated project |
| `workspace.agentmode_plan` | `prompt`, `language?` | plan in `pending_approval` |
| `workspace.agentmode_continue` | `plan_id` | executed plan or cancelled |
| `workspace.agentmode_goal` | `objective`, `criteria[]` | honest completion or `could not meet …` |
| `workspace.agentmode_report` | `goal_id` | latest honest report |
| `workspace.agentmode_stop` | `plan_id?`, `goal_id?` | `{stopped: true, live: true}` |
| `workspace.agentmode_status` | none | live running/cancelled + plans/goals |
| `workspace.subagents_live` | none | per-subagent progress + latest action |
| `workspace.refs_parse` | `text` | `@file`, `#conversation`, `/commands`, `!shell` |
| `workspace.refs_file` | `root_id`, `path` | file summary |
| `workspace.refs_conversation` | `session_id` | conversation reference |
| `workspace.commands_list` | `query?` | slash palette (Persian aliases included) |
| `workspace.shell_propose` | `command`, `cwd?` | risk tier, `network: false`, not executed |
| `workspace.shell_execute` | `approval_id`, `approved?` | sandboxed run; refused without approval |

## Safety

- `..`, absolute paths, and symbolic links that leave a registered root are `INVALID_PARAMS`.
- Preview never executes. HTML scripts and event handlers are stripped. Secrets matching password/token/bearer shapes are redacted.
- Listings are capped (200 names, lazy cursor). Previews read at most 64 KiB.
- `!shell` is risk-tiered. Network is off. Dangerous commands require `approved: true`.

## Agent modes

`/plan` yields `pending_approval` then executes only on `workspace.agentmode_continue`. `/goal` records explicit acceptance criteria and reports `complete` or `unable` with `could not meet <criterion>`. `/stop` sets the engine cancellation token; `workspace.agentmode_status` reflects that live state.
