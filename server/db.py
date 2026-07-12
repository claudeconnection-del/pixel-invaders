"""SQLite persistence for the arcade backend.

WAL mode, single file, safe under uvicorn's default worker. The DB path
comes from ARCADE_DB_PATH (docker-compose mounts a volume at /data).
"""
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.environ.get("ARCADE_DB_PATH", "./arcade.db")

_lock = threading.Lock()
_conn = None


def connection():
    global _conn
    if _conn is None:
        directory = os.path.dirname(os.path.abspath(DB_PATH))
        os.makedirs(directory, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL,
                mode TEXT NOT NULL,
                name TEXT NOT NULL,
                score INTEGER NOT NULL,
                wave INTEGER,
                created TEXT NOT NULL
            )
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scores_board
            ON scores (game, mode, score DESC)
        """)
        _conn.commit()
    return _conn


def insert_score(game, mode, name, score, wave=None):
    """Insert and return the score's 1-based rank on its board."""
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = connection()
        cur = conn.execute(
            "INSERT INTO scores (game, mode, name, score, wave, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (game, mode, name, score, wave, created))
        conn.commit()
        row_id = cur.lastrowid
        (rank,) = conn.execute(
            "SELECT COUNT(*) + 1 FROM scores "
            "WHERE game = ? AND mode = ? AND (score > ? OR (score = ? AND id < ?))",
            (game, mode, score, score, row_id)).fetchone()
    return row_id, rank


def top_scores(game, mode, limit=10):
    with _lock:
        rows = connection().execute(
            "SELECT name, score, wave, created FROM scores "
            "WHERE game = ? AND mode = ? "
            "ORDER BY score DESC, id ASC LIMIT ?",
            (game, mode, limit)).fetchall()
    return [
        {"rank": i + 1, "name": name, "score": score, "wave": wave,
         "date": created[:10]}
        for i, (name, score, wave, created) in enumerate(rows)
    ]


def boards():
    """Distinct (game, mode) pairs that have scores."""
    with _lock:
        rows = connection().execute(
            "SELECT DISTINCT game, mode FROM scores ORDER BY game, mode").fetchall()
    return [{"game": g, "mode": m} for g, m in rows]


def reset_for_tests():
    """Testing hook: wipe the table (used with a temp ARCADE_DB_PATH)."""
    with _lock:
        conn = connection()
        conn.execute("DELETE FROM scores")
        conn.commit()
