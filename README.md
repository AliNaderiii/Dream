# Dream

A personal AI assistant with first-class Persian language support.

The core package `dream/` imports the Python standard library only. That is an
architectural commitment: memory is a single SQLite file, search is SQLite FTS5,
and Persian text handling is written here rather than pulled from a dependency.

## Why Persian normalisation matters

`مي‌خواهم` and `می‌خواهم` render identically but are different byte sequences —
the first uses Arabic yeh (U+064A), the second Farsi yeh (U+06CC). A store that
does not unify them looks like it works and silently returns nothing. Dream
normalises on write and on read:

- NFKC
- Persian (U+06F0–U+06F9) and Arabic-Indic (U+0660–U+0669) digits folded to ASCII
- Arabic letter forms unified to Persian ones (yeh, kaf, teh marbuta, hamza forms)
- Diacritics, superscript alef and tatweel stripped
- ZWNJ turned into a space, whitespace collapsed

A light suffix stemmer lets a query for `استارتاپم` reach a stored `استارتاپ`.

## Memory model

Three kinds of memory:

| kind | holds |
| --- | --- |
| `semantic` | durable facts and preferences |
| `episodic` | timestamped events |
| `procedural` | instructions and learned rules |

Raw conversation goes to a separate `journal` table, kept apart from distilled
memory.

`recall()` blends four signals:

```
score = 0.55 * relevance    (BM25, normalised against the top hit)
      + 0.20 * recency      (exponential decay, 30-day half-life)
      + 0.15 * importance
      + 0.10 * usage        (1 - exp(-use_count / 5))
```

Recency keeps "my current job" ahead of "my job in 2019"; usage is a cheap
learning loop that promotes what gets retrieved often.

## Usage

```python
from dream import MemoryStore

store = MemoryStore("data/dream.db")
store.remember("استارتاپ من درباره هوش مصنوعی است", kind="semantic", importance=0.8)

for hit in store.recall("استارتاپم"):
    print(round(hit.score, 3), hit.content)

store.log("user", "سلام", session_id="s1")
store.close()
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

See [LICENSE](LICENSE).
