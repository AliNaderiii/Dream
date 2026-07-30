"""Dream: a personal assistant with first-class Persian language support.

The core package depends on the Python standard library only.
"""

from __future__ import annotations

from dream.memory import Memory, MemoryStore, normalize_fa

__version__ = "0.1.0"

__all__ = ["Memory", "MemoryStore", "normalize_fa", "__version__"]
