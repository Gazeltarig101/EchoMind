import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .config import DB_PATH

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chunks (
              id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
              text TEXT NOT NULL, started_at TEXT NOT NULL, created_at TEXT NOT NULL,
              embedding BLOB NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chunks_created_idx ON chunks(created_at);
            CREATE INDEX IF NOT EXISTS chunks_session_idx ON chunks(session_id);
            ''')
            # Files created by the first EchoMemory prototype had chunks but no
            # sessions table. Preserve them instead of making an upgrade fail.
            self.db.execute("""
                INSERT OR IGNORE INTO sessions(id, started_at, ended_at)
                SELECT session_id, MIN(started_at), MAX(created_at)
                FROM chunks GROUP BY session_id
            """)
            self.db.commit()

    def start_session(self, session_id: str):
        with self.lock:
            self.db.execute("INSERT INTO sessions(id,started_at) VALUES(?,?)", (session_id, now()))
            self.db.commit()

    def end_session(self, session_id: str):
        with self.lock:
            self.db.execute("UPDATE sessions SET ended_at=? WHERE id=?", (now(), session_id))
            self.db.commit()

    def add(self, session_id, text, embedding, started_at=None):
        text = " ".join(text.split())
        if not text:
            raise ValueError("A memory cannot be empty")
        stamp = now()
        packed = np.asarray(embedding, dtype=np.float32).tobytes()
        with self.lock:
            cursor = self.db.execute("INSERT INTO chunks(session_id,text,started_at,created_at,embedding) VALUES(?,?,?,?,?)",
                (session_id, text, started_at or stamp, stamp, packed))
            self.db.commit()
        return cursor.lastrowid

    def search(self, query, limit=6):
        with self.lock:
            rows = self.db.execute("SELECT * FROM chunks ORDER BY created_at DESC").fetchall()
        if not rows: return []
        q = np.asarray(query, dtype=np.float32)
        qn = np.linalg.norm(q) or 1.0
        scored = []
        for row in rows:
            v = np.frombuffer(row["embedding"], dtype=np.float32)
            if v.shape != q.shape:
                continue
            score = float(np.dot(q, v) / (qn * (np.linalg.norm(v) or 1.0)))
            scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": r["id"], "session_id": r["session_id"], "text": r["text"], "created_at": r["created_at"], "score": round(s, 3)} for s, r in scored[:limit]]

    def day(self, date=None):
        date = date or datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            rows = self.db.execute("SELECT id,text,created_at FROM chunks WHERE substr(created_at,1,10)=? ORDER BY created_at", (date,)).fetchall()
        return [dict(r) for r in rows]

    def recent(self, limit=40):
        with self.lock:
            rows = self.db.execute("SELECT id,session_id,text,created_at FROM chunks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def count(self):
        with self.lock:
            return int(self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def close(self):
        with self.lock:
            self.db.close()
