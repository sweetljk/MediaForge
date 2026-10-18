from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from mediaforge.services.settings import data_dir


class HistoryStore:
    def __init__(self, settings=None, path: Path | None = None):
        self.path = path or data_dir() / "history.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created_at TEXT, data TEXT NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def record(self, job):
        with closing(self._connect()) as connection, connection:
            connection.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?, ?)",
                               (job.id, job.created_at, json.dumps(job.to_dict(), ensure_ascii=False)))

    def load(self, limit: int = 500) -> list[dict]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT data FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]
