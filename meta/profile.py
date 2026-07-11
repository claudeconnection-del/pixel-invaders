"""Persistent player profile: schema-versioned JSON with atomic writes.

One local file (profile.json, gitignored) survives restarts and stores
scores, lifetime stats, unlocked skins, achievements, and settings.
"""
import copy
import json
import os
import tempfile

SCHEMA_VERSION = 1

DEFAULT_PROFILE = {
    "version": SCHEMA_VERSION,
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
    "settings": {
        "crt": True,
        "music": True,
    },
}


def default_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile.json")


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
    for key, value in saved.items():
        if key in ("lifetime", "settings") and isinstance(value, dict):
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
