import re

with open('dream/memory.py') as f:
    src = f.read()

# Add user-id column to schema
old_mem = "    source       TEXT    NOT NULL DEFAULT '',\n    archived     INTEGER NOT NULL DEFAULT 0"
new_mem = "    user_id      TEXT    NOT NULL DEFAULT 'local',\n    source       TEXT    NOT NULL DEFAULT '',\n    archived     INTEGER NOT NULL DEFAULT 0,\n    superseded_by INTEGER"
src = src.replace(old_mem, new_mem)

# Add superseded_by index
src = src.replace(
    "CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);",
    "CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);\nCREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);"
)

# Add journal user_id
old_journal = "    session_id TEXT NOT NULL DEFAULT ''\n);"
new_journal = "    session_id TEXT NOT NULL DEFAULT '',\n    user_id     TEXT    NOT NULL DEFAULT 'local'\n);"
src = src.replace(old_journal, new_journal)

with open('dream/memory.py', 'w') as f:
    f.write(src)
print('updated')
