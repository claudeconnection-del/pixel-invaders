"""Ambient-mode presets: pure data + registry (unlock gating), idle routing,
and the mood-themed achievement rules. No pygame/GL — safe to import headless.

A preset is a calm generative scene plus how it's tuned. Built-ins live in
DEFAULTS; users tweak + save custom presets into their profile. Premium presets
are hidden until a flagship (non-multiplayer) achievement unlocks them.
"""
from dataclasses import asdict, dataclass

from game import theme


def _rgb(c):
    """Drop alpha: a theme RGBA token -> a JSON-friendly [r, g, b]."""
    return [c[0], c[1], c[2]]


@dataclass
class AmbientPreset:
    id: str
    name: str
    scene: str                     # scene renderer id (see ambient/scenes.py)
    palette: list                  # list of [r, g, b]
    speed: float = 1.0             # motion multiplier
    density: str = "medium"        # low | medium | high
    sound: str = "silence"         # "silence" | "music:<pool>" | "bed:<id>"
    dim: float = 0.0               # 0..1 extra darkening of the scene
    premium: str = None            # unlock achievement id, or None (free)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"], name=d["name"], scene=d["scene"],
            palette=[list(c) for c in d["palette"]],
            speed=d.get("speed", 1.0), density=d.get("density", "medium"),
            sound=d.get("sound", "silence"), dim=d.get("dim", 0.0),
            premium=d.get("premium"))


DEFAULTS = [
    AmbientPreset("embers", "Embers", "embers",
                  [_rgb(theme.EMBER), _rgb(theme.COPPER), _rgb(theme.HONEY)],
                  speed=1.0, density="medium", dim=0.15),
    AmbientPreset("starfield", "Starfield", "starfield",
                  [_rgb(theme.FROST), _rgb(theme.COBALT), _rgb(theme.CREAM)],
                  speed=0.6, density="high", dim=0.25),
    AmbientPreset("aurora", "Aurora", "aurora",
                  [_rgb(theme.SAGE), _rgb(theme.LAGOON), _rgb(theme.IRIS)],
                  speed=0.5, density="medium", dim=0.2),
    AmbientPreset("rain", "Rain", "rain",
                  [_rgb(theme.STEEL), _rgb(theme.FROST), _rgb(theme.COBALT)],
                  speed=1.3, density="high", dim=0.2),
    AmbientPreset("nebula", "Nebula", "nebula",
                  [_rgb(theme.IRIS), _rgb(theme.BLOOM), _rgb(theme.COBALT)],
                  speed=0.4, density="medium", dim=0.2),
    AmbientPreset("fireplace", "Fireplace", "fireplace",
                  [_rgb(theme.EMBER), _rgb(theme.RUST), _rgb(theme.HONEY)],
                  speed=1.1, density="medium", dim=0.1, sound="bed:ambient"),
    AmbientPreset("lattice", "Lattice", "lattice",
                  [_rgb(theme.SAGE), _rgb(theme.FROST), _rgb(theme.LAGOON)],
                  speed=0.6, density="medium", dim=0.18),
    # Premium — hidden until a flagship (non-multiplayer) achievement unlocks
    # it. Unlock ids are the real achievement ids from each game's ACHIEVEMENTS.
    AmbientPreset("supernova", "Supernova", "nebula",
                  [_rgb(theme.BLOOM), _rgb(theme.EMBER), _rgb(theme.IRIS)],
                  speed=0.7, density="high", dim=0.1,
                  premium="boss_slayer"),        # Voxel Hell: beat the Dreadnought
    AmbientPreset("ember_hellscape", "Ember Hellscape", "embers",
                  [_rgb(theme.GARNET), _rgb(theme.RUST), _rgb(theme.EMBER)],
                  speed=1.4, density="high", dim=0.05,
                  premium="rock_bottom"),        # Voxel Doom: escape all floors
    AmbientPreset("equalizer", "Equalizer", "equalizer",
                  [_rgb(theme.BLOOM), _rgb(theme.FROST), _rgb(theme.IRIS)],
                  speed=1.0, density="high", dim=0.08,
                  premium="resident_composer"),  # Voxel Studio: export a soundtrack
]


def all_presets():
    return list(DEFAULTS)


def available_presets(unlocked):
    """Built-in presets whose premium unlock (if any) is in `unlocked` — a set
    of earned achievement ids. Free presets always appear."""
    unlocked = unlocked or set()
    return [p for p in DEFAULTS if p.premium is None or p.premium in unlocked]


def custom_presets(ambient_profile):
    """The user's saved custom presets from profile['ambient']."""
    return [AmbientPreset.from_dict(d)
            for d in (ambient_profile or {}).get("custom", [])]


def idle_target(idle_screen):
    """What the MENU idle timer should fade to: 'attract' | 'ambient' | None.
    Unknown/missing values fall back to 'attract' (the historical behavior)."""
    return {"attract": "attract", "ambient": "ambient", "off": None}.get(
        idle_screen, "attract")


# --------------------------- mood-themed cabinet achievements ---------------
# Predicates over a context dict: session_seconds (continuous time in ambient),
# idle_entries (lifetime auto-entries), since_run_end_s (secs since a run
# ended), hour (local hour 0-23). Each rewards a mood / take-a-break play
# style, not skill. (id, name, description, predicate)
AMBIENT_ACHIEVEMENTS = [
    ("deep_breath", "Deep Breath",
     "Drift in ambient for ten unbroken minutes.",
     lambda c: c.get("session_seconds", 0) >= 600),
    ("drifted_off", "Drifted Off",
     "Let the cabinet idle into ambient 25 times.",
     lambda c: c.get("idle_entries", 0) >= 25),
    ("take_a_break", "Take a Break",
     "Slip into ambient within a minute of finishing a game.",
     lambda c: 0 <= c.get("since_run_end_s", 1e9) <= 60),
    ("night_owl", "Night Owl",
     "Find the calm after midnight.",
     lambda c: c.get("hour", 12) < 6),
]
