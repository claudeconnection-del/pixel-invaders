"""Generic achievement machinery. Definitions live with each game
(games/<id>/achievements.py); the engine operates on that game's profile
section so every game has its own unlock/lifetime space.
"""
from datetime import datetime, timezone


class Achievement:
    def __init__(self, aid, name, desc, check, progress=None):
        self.id = aid
        self.name = name
        self.desc = desc
        self.check = check          # (etype, data, life, run) -> bool
        self.progress = progress    # (life, run) -> (current, target) | None


class AchievementEngine:
    """Evaluates one game's locked achievements against each event; unlocks
    write into that game's profile section (including any tied skin)."""

    def __init__(self, game_section, achievements, skin_resolver=None):
        self.section = game_section
        self.achievements = achievements
        self.by_id = {a.id: a for a in achievements}
        self.skin_resolver = skin_resolver or (lambda aid: None)

    def is_unlocked(self, aid):
        return aid in self.section["achievements"]

    def on_frame(self, frame_events, run_stats):
        """Returns list of newly unlocked Achievement objects (for toasts)."""
        life = self.section["lifetime"]
        unlocked_now = []
        candidates = [a for a in self.achievements if not self.is_unlocked(a.id)]
        if not candidates:
            return unlocked_now
        for etype, data in frame_events:
            for a in candidates:
                if a.id in self.section["achievements"]:
                    continue
                try:
                    hit = a.check(etype, data, life, run_stats)
                except (KeyError, TypeError):
                    hit = False
                if hit:
                    self._unlock(a, unlocked_now)
        # time-based achievements (no triggering event): cheap direct check
        for a in candidates:
            if a.id not in self.section["achievements"] and a.progress is not None:
                try:
                    if a.check(None, None, life, run_stats):
                        self._unlock(a, unlocked_now)
                except (KeyError, TypeError):
                    pass
        return unlocked_now

    def _unlock(self, achievement, out):
        self.section["achievements"][achievement.id] = {
            "unlocked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        skin = self.skin_resolver(achievement.id)
        if skin and skin not in self.section["unlocked_skins"]:
            self.section["unlocked_skins"].append(skin)
        out.append(achievement)


# ------------------------------------------- cabinet-level ambient (mood)
# Ambient isn't a game, so its "mood" achievements are evaluated at the cabinet
# level against profile["ambient"] counters + a live context, not game events.
def evaluate_ambient(profile, context):
    """Check the ambient mood achievements against `context` (a dict:
    session_seconds / idle_entries / since_run_end_s / hour) and record any new
    unlocks in profile['ambient']['achievements']. Returns newly-unlocked
    Achievement objects (for toasts). Pure/headless — no GL."""
    from ambient.preset import AMBIENT_ACHIEVEMENTS
    amb = profile.setdefault("ambient", {})
    unlocked = amb.setdefault("achievements", {})
    out = []
    for aid, name, desc, predicate in AMBIENT_ACHIEVEMENTS:
        if aid in unlocked:
            continue
        try:
            hit = predicate(context)
        except (KeyError, TypeError):
            hit = False
        if hit:
            unlocked[aid] = {
                "unlocked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            out.append(Achievement(aid, name, desc, lambda *a: False))
    return out
