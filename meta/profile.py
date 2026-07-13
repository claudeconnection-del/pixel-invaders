"""Persistent player profile: schema-versioned JSON with atomic writes.

v2 layout (multi-game cabinet): global settings + local leaderboards at the
top level; per-game progress under games.<game_id>.
"""
import copy
import json
import os
import tempfile

SCHEMA_VERSION = 2

GAME_SECTION_DEFAULT = {
    "selected_skin": "vanguard",
    "unlocked_skins": ["vanguard"],
    "achievements": {},  # id -> {"unlocked_at": iso8601}
    "lifetime": {
        "runs": 0,
        "wins": 0,
        "kills": 0,
        "deaths": 0,
        "shots": 0,
        "hits": 0,
        "grazes": 0,
        "powerups": 0,
        "bosses": 0,
        "playtime": 0.0,   # seconds
        "best_score": 0,
        "best_wave": 0,
    },
}

DEFAULT_PROFILE = {
    "version": SCHEMA_VERSION,
    "selected_game": "voxelhell",
    "games": {},  # game_id -> GAME_SECTION_DEFAULT copy, created on demand
    "leaderboard": {},  # "game:mode" -> [{name, score, wave, date}] top 10
    "outbox": [],  # queued score submissions awaiting server contact
    "settings": {
        "crt": True,
        "music": True,
        "fps_cap": 120,        # 0 = unlimited
        "vsync": True,
        "fullscreen": False,
        "bloom": "full",       # off | low | full
        "particles": "high",   # low | medium | high
        "music_vol": 0.45,
        "sfx_vol": 1.0,
        "show_fps": False,
        "mouse_sens": 1.0,        # look sensitivity multiplier (FPS games)
        "ghost": "personal",      # off | personal (race your best run's ghost)
        "game_music": "classic",  # classic | custom (Voxel Studio export)
        "player_name": "AAA",  # arcade initials
        "server_url": "",      # arcade backend, e.g. http://ubuntu-box:8083
    },
}


def default_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile.json")


def game_section(profile, game_id):
    """Fetch (creating if missing) a game's progress section."""
    if game_id not in profile["games"]:
        profile["games"][game_id] = copy.deepcopy(GAME_SECTION_DEFAULT)
    section = profile["games"][game_id]
    # merge any new default keys into old saves
    for key, value in GAME_SECTION_DEFAULT["lifetime"].items():
        section.setdefault("lifetime", {}).setdefault(key, value)
    for key, value in GAME_SECTION_DEFAULT.items():
        section.setdefault(key, copy.deepcopy(value))
    return section


def _migrate_v1(saved, profile):
    """v1 kept voxelhell's progress at the top level."""
    section = game_section(profile, "voxelhell")
    for key in ("selected_skin", "unlocked_skins", "achievements"):
        if key in saved:
            section[key] = saved[key]
    if isinstance(saved.get("lifetime"), dict):
        section["lifetime"].update(saved["lifetime"])
    if isinstance(saved.get("leaderboard"), dict):
        profile["leaderboard"].update(saved["leaderboard"])


def load(path=None):
    """Load the profile, merging defaults for any missing keys so old save
    files keep working as the schema grows."""
    path = path or default_path()
    profile = copy.deepcopy(DEFAULT_PROFILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return profile
    if not isinstance(saved, dict):
        return profile

    if saved.get("version", 1) < 2:
        if isinstance(saved.get("settings"), dict):
            profile["settings"].update(saved["settings"])
        _migrate_v1(saved, profile)
        return profile

    for key, value in saved.items():
        if key in ("settings", "leaderboard", "games") and isinstance(value, dict):
            profile[key].update(value)
        elif key in profile:
            profile[key] = value
    profile["version"] = SCHEMA_VERSION
    return profile


def save(profile, path=None):
    """Atomic write: temp file in the same directory, then os.replace, so a
    crash mid-write can never corrupt the existing save."""
    path = path or default_path()
    directory = os.path.dirname(path) or "."
    try:
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        pass  # saving is best-effort; never crash the game over it
