"""Run replays: a deterministic recording of a run as its seed + input
stream. Because every game is a pure seeded simulation, re-feeding the same
seed and per-frame inputs reconstructs the run exactly — so a replay is a
few KB (not a video), can be re-rendered at any resolution/framerate on
demand, watched later, or exported to GIF/MP4 client-side (tools/export_replay).

Compact format: booleans packed into one bitmask per frame; the analog fields
(mouse aim, strafe, look) are only stored for games that use them (the FPS /
aim games), so field-game replays are ~one int per frame.
"""
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time

from game.entities import InputState

SCHEMA = 1
REPLAY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "replays")

_BITS = (("left", 1), ("right", 2), ("up", 4), ("down", 8),
         ("focus", 16), ("fire", 32))


class ReplayRecorder:
    def __init__(self, game_id, mode, seed, analog):
        self.game = game_id
        self.mode = mode
        self.seed = int(seed)
        self.analog = bool(analog)
        # exact per-frame dt is required for deterministic reconstruction
        # (the sim is a pure function of seed + dt-stream + inputs); rounding
        # dt drifts the timeline and desyncs. Stored as full-precision floats.
        self.dts = []
        self.masks = []
        self.analog_data = []

    def on_frame(self, dt, inp):
        self.dts.append(float(dt))
        m = 0
        for name, bit in _BITS:
            if getattr(inp, name):
                m |= bit
        self.masks.append(m)
        if self.analog:
            self.analog_data.append([
                float(inp.aim_x), float(inp.aim_y), float(inp.strafe),
                float(inp.turn), float(inp.look_dx)])

    @property
    def frame_count(self):
        return len(self.dts)

    def build(self, score=0):
        return {
            "schema": SCHEMA, "game": self.game, "mode": self.mode,
            "seed": self.seed, "analog": self.analog, "score": int(score),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            # duration is cheap-to-read metadata for the replay browser so it
            # needn't sum every dt just to label a run's length
            "duration": round(sum(self.dts), 2),
            "dts": self.dts, "masks": self.masks,
            "analog_data": self.analog_data,
        }


class Replay:
    """Iterable playback of a recorded replay."""

    def __init__(self, data):
        self.game = data["game"]
        self.mode = data["mode"]
        self.seed = int(data["seed"])
        self.analog = bool(data.get("analog"))
        self.score = int(data.get("score", 0))
        self.dts = data["dts"]
        self.masks = data["masks"]
        self.analog_data = data.get("analog_data", [])

    @property
    def frame_count(self):
        return len(self.dts)

    @property
    def duration(self):
        return sum(self.dts)

    def frames(self):
        for i in range(len(self.dts)):
            dt = self.dts[i]
            m = self.masks[i]
            inp = InputState(
                left=bool(m & 1), right=bool(m & 2), up=bool(m & 4),
                down=bool(m & 8), focus=bool(m & 16), fire=bool(m & 32))
            if self.analog and i < len(self.analog_data):
                ax, ay, sx, tn, lk = self.analog_data[i]
                inp.aim_x, inp.aim_y = ax, ay
                inp.strafe, inp.turn, inp.look_dx = sx, tn, lk
            yield dt, inp


# ------------------------------------------------------------- persistence
def _atomic_write(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ---------------------------------------------------- CAB-13: tamper mark
# HMAC-SHA256 signing so a shared replay can be spot-checked for tampering
# before it's trusted (e.g. posted to a leaderboard, CAB-14). Stdlib only
# (hmac/hashlib/json) so this stays importable from the server/ package too,
# without dragging pygame/PyOpenGL into that image — the canonical encoding
# below is the wire format both sides must agree on if/when the server
# re-verifies (CAB-14): sorted-key, separator-compact JSON of every field
# except "sig" itself.
def _canonical_json(data):
    """Deterministic JSON encoding of a replay payload for HMAC purposes:
    sorted keys (so dict insertion order never matters), no incidental
    whitespace, and the "sig" field always excluded (so this is stable
    whether or not `data` already carries a signature)."""
    payload = {k: v for k, v in data.items() if k != "sig"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_replay(data, key):
    """HMAC-SHA256 tamper-mark for a replay payload, as a hex digest. Pure
    function: does not mutate `data`; callers store the result themselves as
    data["sig"]."""
    if isinstance(key, str):
        key = key.encode("utf-8")
    return hmac.new(key, _canonical_json(data), hashlib.sha256).hexdigest()


def verify_replay(data, key):
    """True if data["sig"] matches the HMAC of its other fields under `key`,
    via a constant-time compare. Returns False (never raises) when "sig" is
    missing/blank, so "unsigned" and "tampered" are both just "unverified"
    to callers."""
    sig = data.get("sig")
    if not sig:
        return False
    if isinstance(key, str):
        key = key.encode("utf-8")
    expected = hmac.new(key, _canonical_json(data), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _resolve_key():
    """Resolve the key used to sign/verify locally-saved replays:

    1. The cabinet's server API key — CABINET_MAN_API_KEY env var (or the
       legacy PIXEL_INVADERS_API_KEY), matching game/netclient.py's lookup;
       else a settings-stored equivalent (settings["server_key"]) — so a
       paired cabinet's replays can be re-verified server-side later (B2 /
       CAB-14).
    2. Otherwise, a per-profile random key generated once and cached in
       settings["replay_key"], so an unpaired cabinet's local replays are
       still self-consistently signed/verified.

    Local import to avoid importing the profile layer (and its disk I/O)
    for callers that only need sign_replay/verify_replay with an explicit
    key (e.g. tests, or a future server-side verifier)."""
    env_key = (os.environ.get("CABINET_MAN_API_KEY")
               or os.environ.get("PIXEL_INVADERS_API_KEY"))
    if env_key:
        return env_key.encode("utf-8")
    from meta import profile as profile_mod
    profile = profile_mod.load()
    settings = profile.setdefault("settings", {})
    server_key = settings.get("server_key")
    if server_key:
        return server_key.encode("utf-8")
    replay_key = settings.get("replay_key")
    if not replay_key:
        replay_key = secrets.token_hex(32)
        settings["replay_key"] = replay_key
        profile_mod.save(profile)
    return replay_key.encode("utf-8")


def _signed(data, key):
    """Return a copy of `data` carrying a fresh "sig" HMAC, using `key` if
    given else the auto-resolved cabinet/profile key. Never mutates the
    input dict (callers like main.py hold onto it, e.g. self.last_replay,
    and shouldn't see it change shape under them)."""
    if key is None:
        key = _resolve_key()
    out = dict(data)
    out["sig"] = sign_replay(out, key)
    return out


def load(path, key=None):
    """Load a replay file, returning the parsed dict with an added
    "verified" bool. Signing is a tamper *mark*, not a gate: unsigned or
    pre-HMAC replays load exactly as before (schema back-compat) — they're
    just reported unverified, never refused, so every existing local replay
    still plays in the Theater."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if key is None:
        key = _resolve_key()
    data["verified"] = verify_replay(data, key)
    return data


def last_path(game_id, mode):
    return os.path.join(REPLAY_DIR, f"last_{game_id}_{mode}.json")


def save_last(data, key=None):
    """Overwrite the 'last run' replay for this game+mode (always kept so a
    run can be exported after the fact). Tamper-marked with an HMAC using
    `key` if given, else the auto-resolved cabinet/profile key."""
    data = _signed(data, key)
    path = last_path(data["game"], data["mode"])
    _atomic_write(path, data)
    return path


def keep(data, key=None):
    """Save a timestamped keeper copy (a run the player wants to hold onto).
    Tamper-marked the same way as save_last."""
    data = _signed(data, key)
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"{data['game']}_{data['mode']}_{data.get('score', 0):07d}_{ts}.json"
    path = os.path.join(REPLAY_DIR, name)
    _atomic_write(path, data)
    return path


def _meta(path):
    """Lightweight metadata for one replay file (for the in-game browser)."""
    data = load(path)
    dts = data.get("dts") or []
    name = os.path.basename(path)
    return {
        "path": path,
        "file": name,
        "game": data.get("game"),
        "mode": data.get("mode"),
        "seed": int(data.get("seed", 0)),
        "score": int(data.get("score", 0)),
        "frames": len(dts),
        "duration": float(data.get("duration") or sum(dts)),
        "created": data.get("created", ""),
        # the always-overwritten "last run" copy vs. a player-kept keeper
        "kept": not name.startswith("last_"),
        "verified": bool(data.get("verified")),
        "mtime": os.path.getmtime(path),
    }


def list_for_game(game_id):
    """All saved replays for a game, newest first, as metadata dicts. Skips
    unreadable files so a single corrupt replay never breaks the browser."""
    out = []
    if not os.path.isdir(REPLAY_DIR):
        return out
    for name in os.listdir(REPLAY_DIR):
        if not name.endswith(".json"):
            continue
        try:
            meta = _meta(os.path.join(REPLAY_DIR, name))
        except (OSError, ValueError, KeyError):
            continue
        if meta["game"] == game_id and meta["frames"] > 0:
            out.append(meta)
    out.sort(key=lambda e: e["mtime"], reverse=True)
    return out
