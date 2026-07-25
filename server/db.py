"""SQLite persistence for the arcade backend.

WAL mode, single file, safe under uvicorn's default worker. The DB path
comes from ARCADE_DB_PATH (docker-compose mounts a volume at /data).
"""
import base64
import json
import os
import sqlite3
import threading
import zlib
from datetime import datetime, timezone

DB_PATH = os.environ.get("ARCADE_DB_PATH", "./arcade.db")

# CAB-14: replays are kept only for score entries that are on, or beat, the
# current top-N of their (game, mode) board.
RETENTION_TOP_N = 10

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
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                code TEXT PRIMARY KEY,
                game TEXT NOT NULL,
                mode TEXT NOT NULL,
                seed INTEGER NOT NULL,
                host TEXT NOT NULL,
                created TEXT NOT NULL
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS session_players (
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                joined TEXT NOT NULL,
                score INTEGER,
                wave INTEGER,
                submitted TEXT,
                PRIMARY KEY (code, name)
            )
        """)
        # turn-based board matches: game-agnostic relay of an opaque state
        # blob, gated by whose turn it is and an optimistic version counter.
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                code TEXT PRIMARY KEY,
                game TEXT NOT NULL,
                state TEXT NOT NULL,
                turn TEXT,
                version INTEGER NOT NULL,
                host TEXT NOT NULL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS match_players (
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                joined TEXT NOT NULL,
                PRIMARY KEY (code, name)
            )
        """)
        # CAB-14: replays tied to leaderboard entries. The replay payload
        # (the CAB-13 signed dict, including its "sig") is stored zlib
        # compressed + base64-encoded in `blob`; (game, mode, name, score)
        # are denormalized copies of the matching scores row so listing and
        # retention pruning never need to inflate the blob.
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS replays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL,
                mode TEXT NOT NULL,
                name TEXT NOT NULL,
                score INTEGER NOT NULL,
                blob TEXT NOT NULL,
                created TEXT NOT NULL
            )
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_replays_board
            ON replays (game, mode, score DESC)
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
        # a new score can bump an older one off the top-N, taking its stored
        # replay (if any) with it — CAB-14 retention.
        _prune_replays(conn, game, mode)
        conn.commit()
    return row_id, rank


def score_rank(game, mode, name, score):
    """1-based rank of an existing scores row matching (game, mode, name,
    score) — ties broken the same way as insert_score (most recent id wins
    the tie for "found row", but rank itself only depends on score value).
    Returns None if no such row exists."""
    with _lock:
        conn = connection()
        row = conn.execute(
            "SELECT id FROM scores WHERE game = ? AND mode = ? AND name = ? "
            "AND score = ? ORDER BY id DESC LIMIT 1",
            (game, mode, name, score)).fetchone()
        if row is None:
            return None
        row_id = row[0]
        (rank,) = conn.execute(
            "SELECT COUNT(*) + 1 FROM scores "
            "WHERE game = ? AND mode = ? AND (score > ? OR (score = ? AND id < ?))",
            (game, mode, score, score, row_id)).fetchone()
    return rank


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


# ------------------------------------------------------ multiplayer sessions
SESSION_TTL_HOURS = 24
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L


def _purge_expired(conn):
    cutoff = datetime.now(timezone.utc).timestamp() - SESSION_TTL_HOURS * 3600
    cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat(
        timespec="seconds")
    old = [r[0] for r in conn.execute(
        "SELECT code FROM sessions WHERE created < ?", (cutoff_iso,))]
    for code in old:
        conn.execute("DELETE FROM sessions WHERE code = ?", (code,))
        conn.execute("DELETE FROM session_players WHERE code = ?", (code,))


def create_session(game, mode, host, seed):
    import random as _random
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = connection()
        _purge_expired(conn)
        for _ in range(50):
            code = "".join(_random.choices(_CODE_ALPHABET, k=4))
            exists = conn.execute("SELECT 1 FROM sessions WHERE code = ?",
                                  (code,)).fetchone()
            if not exists:
                break
        else:
            raise RuntimeError("could not allocate a session code")
        conn.execute(
            "INSERT INTO sessions (code, game, mode, seed, host, created) "
            "VALUES (?, ?, ?, ?, ?, ?)", (code, game, mode, seed, host, created))
        conn.execute(
            "INSERT INTO session_players (code, name, joined) VALUES (?, ?, ?)",
            (code, host, created))
        conn.commit()
    return code


def get_session(code):
    with _lock:
        conn = connection()
        _purge_expired(conn)
        row = conn.execute(
            "SELECT game, mode, seed, host, created FROM sessions "
            "WHERE code = ?", (code,)).fetchone()
        if row is None:
            return None
        players = conn.execute(
            "SELECT name, score, wave, submitted FROM session_players "
            "WHERE code = ? ORDER BY score IS NULL, score DESC, joined ASC",
            (code,)).fetchall()
    return {
        "code": code, "game": row[0], "mode": row[1], "seed": row[2],
        "host": row[3], "created": row[4],
        "players": [{"name": n, "score": s, "wave": w,
                     "submitted": bool(sub)}
                    for n, s, w, sub in players],
    }


def join_session(code, name):
    """Returns 'ok', 'taken', or None (no such session)."""
    joined = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = connection()
        if conn.execute("SELECT 1 FROM sessions WHERE code = ?",
                        (code,)).fetchone() is None:
            return None
        exists = conn.execute(
            "SELECT 1 FROM session_players WHERE code = ? AND name = ?",
            (code, name)).fetchone()
        if exists:
            return "taken"
        conn.execute(
            "INSERT INTO session_players (code, name, joined) VALUES (?, ?, ?)",
            (code, name, joined))
        conn.commit()
    return "ok"


def submit_session_score(code, name, score, wave=None):
    """Records the player's best score; returns False if not joined."""
    submitted = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = connection()
        row = conn.execute(
            "SELECT score FROM session_players WHERE code = ? AND name = ?",
            (code, name)).fetchone()
        if row is None:
            return False
        if row[0] is None or score > row[0]:
            conn.execute(
                "UPDATE session_players SET score = ?, wave = ?, submitted = ? "
                "WHERE code = ? AND name = ?",
                (score, wave, submitted, code, name))
            conn.commit()
    return True


# --------------------------------------------------- turn-based board matches
MATCH_TTL_HOURS = 24
MATCH_MAX_PLAYERS = 6


def _purge_expired_matches(conn):
    cutoff = datetime.now(timezone.utc).timestamp() - MATCH_TTL_HOURS * 3600
    cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat(
        timespec="seconds")
    old = [r[0] for r in conn.execute(
        "SELECT code FROM matches WHERE updated < ?", (cutoff_iso,))]
    for code in old:
        conn.execute("DELETE FROM matches WHERE code = ?", (code,))
        conn.execute("DELETE FROM match_players WHERE code = ?", (code,))


def _match_row(conn, code):
    row = conn.execute(
        "SELECT game, state, turn, version, host, created, updated "
        "FROM matches WHERE code = ?", (code,)).fetchone()
    if row is None:
        return None
    players = [r[0] for r in conn.execute(
        "SELECT name FROM match_players WHERE code = ? ORDER BY joined ASC",
        (code,))]
    return {
        "code": code, "game": row[0], "state": json.loads(row[1]),
        "turn": row[2], "version": row[3], "host": row[4],
        "created": row[5], "updated": row[6], "players": players,
    }


def create_match(game, host, state, turn):
    import random as _random
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = connection()
        _purge_expired_matches(conn)
        for _ in range(50):
            code = "".join(_random.choices(_CODE_ALPHABET, k=4))
            if not conn.execute("SELECT 1 FROM matches WHERE code = ?",
                                (code,)).fetchone():
                break
        else:
            raise RuntimeError("could not allocate a match code")
        conn.execute(
            "INSERT INTO matches (code, game, state, turn, version, host, "
            "created, updated) VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
            (code, game, json.dumps(state), turn, host, now, now))
        conn.execute(
            "INSERT INTO match_players (code, name, joined) VALUES (?, ?, ?)",
            (code, host, now))
        conn.commit()
        return _match_row(conn, code)


def get_match(code):
    with _lock:
        conn = connection()
        _purge_expired_matches(conn)
        return _match_row(conn, code)


def join_match(code, name):
    """Returns 'ok', 'taken', 'full', or None (no such match)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = connection()
        if conn.execute("SELECT 1 FROM matches WHERE code = ?",
                        (code,)).fetchone() is None:
            return None
        if conn.execute("SELECT 1 FROM match_players WHERE code = ? AND name = ?",
                        (code, name)).fetchone():
            return "taken"
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM match_players WHERE code = ?", (code,)).fetchone()
        if count >= MATCH_MAX_PLAYERS:
            return "full"
        conn.execute(
            "INSERT INTO match_players (code, name, joined) VALUES (?, ?, ?)",
            (code, name, now))
        conn.commit()
        return "ok"


def submit_move(code, name, base_version, state, turn):
    """Turn- and version-gated move. Returns (status, match) where status is
    'ok' | 'conflict' | 'forbidden' | 'notfound'."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = connection()
        row = conn.execute(
            "SELECT turn, version FROM matches WHERE code = ?", (code,)).fetchone()
        if row is None:
            return "notfound", None
        cur_turn, cur_version = row
        joined = conn.execute(
            "SELECT 1 FROM match_players WHERE code = ? AND name = ?",
            (code, name)).fetchone()
        if not joined or (cur_turn is not None and cur_turn != name):
            return "forbidden", _match_row(conn, code)
        if base_version != cur_version:
            return "conflict", _match_row(conn, code)
        conn.execute(
            "UPDATE matches SET state = ?, turn = ?, version = ?, updated = ? "
            "WHERE code = ?",
            (json.dumps(state), turn, cur_version + 1, now, code))
        conn.commit()
        return "ok", _match_row(conn, code)


# -------------------------------------------------------------- replays
def _pack_replay(replay):
    """zlib-compress + base64-encode a replay dict's canonical JSON so it
    stores compactly as sqlite TEXT (stdlib only)."""
    raw = json.dumps(replay, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(zlib.compress(raw, 9)).decode("ascii")


def _unpack_replay(blob):
    raw = zlib.decompress(base64.b64decode(blob))
    return json.loads(raw)


def _prune_replays(conn, game, mode):
    """Delete any stored replay for (game, mode) whose score no longer
    qualifies for the current top-N of that board. Called after every score
    insert (a new high score can bump an older one, and its replay, off the
    board) and after every replay insert (belt-and-braces)."""
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM scores WHERE game = ? AND mode = ?",
        (game, mode)).fetchone()
    if count < RETENTION_TOP_N:
        return
    row = conn.execute(
        "SELECT score FROM scores WHERE game = ? AND mode = ? "
        "ORDER BY score DESC, id ASC LIMIT 1 OFFSET ?",
        (game, mode, RETENTION_TOP_N - 1)).fetchone()
    if row is None:
        return
    threshold = row[0]
    conn.execute(
        "DELETE FROM replays WHERE game = ? AND mode = ? AND score < ?",
        (game, mode, threshold))


def insert_replay(game, mode, name, score, replay):
    """Store a verified replay tied to a (game, mode, name, score) entry.
    Returns the new replay's id."""
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    blob = _pack_replay(replay)
    with _lock:
        conn = connection()
        cur = conn.execute(
            "INSERT INTO replays (game, mode, name, score, blob, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (game, mode, name, score, blob, created))
        row_id = cur.lastrowid
        _prune_replays(conn, game, mode)
        conn.commit()
    return row_id


def list_replays(game, mode):
    """Available replays for a board, best score first."""
    with _lock:
        rows = connection().execute(
            "SELECT id, name, score, created FROM replays "
            "WHERE game = ? AND mode = ? ORDER BY score DESC, id ASC",
            (game, mode)).fetchall()
    return [
        {"id": rid, "name": name, "score": score, "date": created[:10]}
        for rid, name, score, created in rows
    ]


def get_replay(replay_id):
    """The stored replay dict for `replay_id`, or None if it doesn't exist
    (never existed, or was pruned by retention)."""
    with _lock:
        row = connection().execute(
            "SELECT blob FROM replays WHERE id = ?", (replay_id,)).fetchone()
    if row is None:
        return None
    return _unpack_replay(row[0])


def reset_for_tests():
    """Testing hook: wipe all tables (used with a temp ARCADE_DB_PATH)."""
    with _lock:
        conn = connection()
        for t in ("scores", "sessions", "session_players",
                  "matches", "match_players", "replays"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
