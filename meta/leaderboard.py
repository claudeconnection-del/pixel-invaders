"""Local top-10 leaderboards, stored per game+mode in the profile."""
from datetime import datetime, timezone

MAX_ENTRIES = 10


def board_key(game_id, mode):
    return f"{game_id}:{mode}"


def entries(profile, game_id, mode):
    return profile["leaderboard"].get(board_key(game_id, mode), [])


def qualifies(profile, game_id, mode, score):
    if score <= 0:
        return False
    board = entries(profile, game_id, mode)
    if len(board) < MAX_ENTRIES:
        return True
    return score > board[-1]["score"]


def submit(profile, game_id, mode, name, score, extra=None):
    """Insert a score; returns its 1-based rank."""
    board = list(entries(profile, game_id, mode))
    entry = {
        "name": (name or "???")[:3].upper(),
        "score": int(score),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    if extra:
        entry.update(extra)
    board.append(entry)
    board.sort(key=lambda e: e["score"], reverse=True)
    board = board[:MAX_ENTRIES]
    profile["leaderboard"][board_key(game_id, mode)] = board
    try:
        return board.index(entry) + 1
    except ValueError:
        return MAX_ENTRIES + 1  # fell off the board
