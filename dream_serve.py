"""``dream-serve`` console script. Thin wrapper around ``dream.remotegw``."""

from __future__ import annotations

from dream.remotegw.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
