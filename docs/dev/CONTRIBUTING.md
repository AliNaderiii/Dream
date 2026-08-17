# Contributing

## PR workflow

1. Branch from `main`; open the PR against `main` (never an intermediate
   `feat/*`).
2. Keep the author of your commit `Ali Naderi <alinaderi@users.noreply.github.com>`.
3. Run the full gate suite locally before pushing (see below); CI runs the same
   gates.

## Commit rules (`tools/check_commit.py`)

CI enforces, on the PR head commit:

- author name == `Ali Naderi`
- author email == `alinaderi@users.noreply.github.com`
- **no** `Co-authored-by:` trailer
- **no** AI-tooling words in the message (arena, claude, chatgpt, openai,
  gemini, grok, qwen, kimi, copilot, anthropic, llm, ai-authored, …)

To fix an offending commit, rewrite its message with `git commit --amend
--no-verify --reset-author` (never `git stash`, never `git reset --hard`, never
`git push --force`; use `--force-with-lease` at most).

## Coding standards

- **Python:** `from __future__ import annotations`, `dataclass(..., slots=True)`,
  type hints and docstrings everywhere, `logging` instead of `print()`. Ruff
  config is `E, F, I, UP, B`, line-length 100.
- **TypeScript/React:** functional components, typed bridge wrappers, hooks for
  side effects. Strings must go through i18n (`useTranslation()`), never
  hard-coded.

## Test expectations

- Python: `python -m pytest -q` — the suite must not shrink
  (`tools/check_suite_count.py` enforces the floor).
- Frontend: `npx vitest run` — new behaviour ships with tests.
- New i18n strings must exist in all eight locales (`apps/desktop/scripts/generate-locales.mjs`
  is the source of truth; run it after editing).

## The full gate suite

```bash
ruff check .
python -m pytest -q

cd apps/desktop
npx tsc --noEmit
npx eslint . --ext .ts,.tsx
npx prettier --check "src/**/*.{ts,tsx,css}"
npx vitest run
npm run build
```

## Security

Never commit credentials of any shape. API keys belong in the OS keychain.
Run `bandit -r dream/ -q` and keep high/critical findings at zero.
