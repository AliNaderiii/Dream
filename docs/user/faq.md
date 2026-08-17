# FAQ

## Installation & running

1. **What Python do I need?** 3.10 or later. `python --version` to check.
2. **Do I need an API key?** No — `dream --demo` and `dream --backend echo` run
   offline. A key is only needed for a cloud provider.
3. **Which model providers work?** OpenAI-compatible endpoints, Ollama, and a
   built-in offline echo backend for demos/tests.
4. **Where is my data stored?** Memory, skills and datasets are local — under
   your workspace and Dream's data directory. Nothing is uploaded.
5. **How do I run the desktop app?** `cd apps/desktop && npm install && npm run
   dev` (see quick-start.md).

## Language

6. **Why does Dream reply in Persian?** It follows the language of your most
   recent message by design.
7. **How many languages does the UI support?** Eight: English, Persian,
   Simplified Chinese, Japanese, Spanish, German, French, Korean.
8. **Can I force English?** Yes — Settings → Language → English; your choice is
   remembered.
9. **Why is the layout right-to-left sometimes?** Persian is RTL. Only `fa`
   flips the layout; other languages stay LTR.

## Memory

10. **Will it remember «میخواهم» if I wrote «می‌خواهم»?** Yes — Persian spelling
    variants are normalised before storing and searching.
11. **Can I delete a memory?** Yes, from the memory explorer (select → delete).
12. **Can I add a memory by hand?** Yes — "New memory" in the explorer.
13. **What are the star ratings?** Importance, 0–1. Higher stars surface first
    in recall.

## Skills & subagents

14. **What is a skill?** A reusable text procedure Dream can follow, stored as a
    `.dream-skill.txt` file.
15. **How do I share a skill?** Export it (single file or ZIP) and import it
    elsewhere.
16. **What is a subagent?** An isolated child agent with its own memory and a
    restricted tool grant — used for delegated tasks.
17. **Can a subagent read my whole memory?** No. It only sees what it is
    granted; un-granted tool names are refused.

## Security & privacy

18. **Does Dream run shell commands on its own?** Never silently — `run_shell`
    is a *dangerous* tool that requires explicit approval.
19. **Where are my API keys?** In the OS keychain, not in settings files or
    logs.
20. **Is the web gateway safe?** It requires a per-device token; read tokens
    cannot change anything.
21. **Where can I read the security audit?** `docs/security/audit-report.md`
    (0 critical, 0 high).
22. **What is the Docker sandbox for?** Untrusted code (and all data work) runs
    in an isolated, network-disabled container.

## Data science

23. **What file formats can I load?** CSV, TSV, Excel, JSON, YAML, XML, SQLite,
    Parquet.
24. **Is there a size limit?** Ingestion is capped at 500 MB; files over 100 MB
    are profiled in a single pass.
25. **Can I export a chart?** Yes — PNG/SVG/PDF, plus interactive HTML.

## Miscellaneous

26. **Where are the keyboard shortcuts?** `docs/user/keyboard-shortcuts.md`.
27. **How do I report a bug?** Open an issue with `dream --debug` output (it
    never contains secrets).
28. **What does `dream --version` tell me?** Your exact build/version for
    support.
