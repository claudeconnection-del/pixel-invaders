"""Achievement definitions and the engine that unlocks them from events.

Each achievement's `check(etype, data, life, run)` is evaluated for every
event while locked. `progress(life, run)` (optional) returns (current, target)
for the menu's progress bars.
"""
from datetime import datetime, timezone

from game import events as ev


class Achievement:
    def __init__(self, aid, name, desc, check, progress=None):
        self.id = aid
        self.name = name
        self.desc = desc
        self.check = check
        self.progress = progress


def _summary(etype, data):
    return data["summary"] if etype == ev.RUN_END else None


ACHIEVEMENTS = [
    Achievement(
        "first_blood", "First Blood", "Destroy your first enemy",
        lambda e, d, life, run: e == ev.ENEMY_KILLED,
    ),
    Achievement(
        "warmed_up", "Warmed Up", "Clear Wave 1",
        lambda e, d, life, run: e == ev.WAVE_CLEAR and d["index"] == 0,
    ),
    Achievement(
        "halfway_there", "Halfway There", "Clear Wave 3",
        lambda e, d, life, run: e == ev.WAVE_CLEAR and d["index"] == 2,
    ),
    Achievement(
        "boss_slayer", "Boss Slayer", "Defeat the boss",
        lambda e, d, life, run: e == ev.BOSS_KILLED,
    ),
    Achievement(
        "one_credit_clear", "One Credit Clear", "Beat the campaign without losing a life",
        lambda e, d, life, run: (s := _summary(e, d)) is not None
        and s["win"] and s["deaths"] == 0,
    ),
    Achievement(
        "untouchable", "Untouchable", "Clear any wave without getting hit",
        lambda e, d, life, run: e == ev.WAVE_CLEAR and d["untouched"],
    ),
    Achievement(
        "graze_addict", "Graze Addict", "Graze 100 bullets in one run",
        lambda e, d, life, run: e == ev.GRAZE and run["grazes"] >= 100,
        progress=lambda life, run: (run["grazes"], 100),
    ),
    Achievement(
        "edge_lord", "Edge Lord", "Graze 1,000 bullets lifetime",
        lambda e, d, life, run: e == ev.GRAZE and life["grazes"] >= 1000,
        progress=lambda life, run: (life["grazes"], 1000),
    ),
    Achievement(
        "sharpshooter", "Sharpshooter", "Finish a run with 75%+ accuracy (min 50 shots)",
        lambda e, d, life, run: (s := _summary(e, d)) is not None
        and s["shots"] >= 50 and s["accuracy"] >= 0.75,
    ),
    Achievement(
        "hoarder", "Hoarder", "Collect 5 power-ups in one run",
        lambda e, d, life, run: e == ev.POWERUP_PICKUP and run["powerups"] >= 5,
        progress=lambda life, run: (run["powerups"], 5),
    ),
    Achievement(
        "exterminator", "Exterminator", "Destroy 1,000 enemies lifetime",
        lambda e, d, life, run: e in (ev.ENEMY_KILLED, ev.BOSS_KILLED)
        and life["kills"] >= 1000,
        progress=lambda life, run: (life["kills"], 1000),
    ),
    Achievement(
        "marathoner", "Marathoner", "Play for 1 hour total",
        lambda e, d, life, run: life["playtime"] >= 3600,
        progress=lambda life, run: (int(life["playtime"]), 3600),
    ),
]

BY_ID = {a.id: a for a in ACHIEVEMENTS}


class AchievementEngine:
    """Evaluates locked achievements against each event; unlocks write into
    the profile (including any skin tied to the achievement)."""

    def __init__(self, profile):
        self.profile = profile

    def is_unlocked(self, aid):
        return aid in self.profile["achievements"]

    def on_frame(self, frame_events, run_stats):
        """Returns list of newly unlocked Achievement objects (for toasts)."""
        from game.skins import skin_for_achievement
        life = self.profile["lifetime"]
        unlocked_now = []
        # marathoner has no triggering event; give every frame a chance via a
        # synthetic tick when events are empty is wasteful — instead check it
        # alongside any event AND on run end; plus a cheap direct check here.
        candidates = [a for a in ACHIEVEMENTS if not self.is_unlocked(a.id)]
        if not candidates:
            return unlocked_now
        for etype, data in frame_events:
            for a in candidates:
                if a.id in self.profile["achievements"]:
                    continue
                try:
                    hit = a.check(etype, data, life, run_stats)
                except (KeyError, TypeError):
                    hit = False
                if hit:
                    self._unlock(a, skin_for_achievement, unlocked_now)
        # time-based achievement: no event needed
        marathoner = BY_ID["marathoner"]
        if not self.is_unlocked("marathoner") and life["playtime"] >= 3600:
            self._unlock(marathoner, skin_for_achievement, unlocked_now)
        return unlocked_now

    def _unlock(self, achievement, skin_for_achievement, out):
        self.profile["achievements"][achievement.id] = {
            "unlocked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        skin = skin_for_achievement(achievement.id)
        if skin and skin not in self.profile["unlocked_skins"]:
            self.profile["unlocked_skins"].append(skin)
        out.append(achievement)
