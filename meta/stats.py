"""Lifetime stat accumulation from world events into a game's profile section."""
from game import events as ev


class StatsTracker:
    """Feed it each frame's events (+ dt); it keeps the game section's
    lifetime dict current. The caller decides when to persist the profile."""

    def __init__(self, game_section):
        self.section = game_section

    def on_frame(self, dt, frame_events):
        life = self.section["lifetime"]
        life["playtime"] += dt
        for etype, data in frame_events:
            if etype == ev.ENEMY_KILLED:
                life["kills"] += 1
            elif etype == ev.SHOT_FIRED:
                life["shots"] += data["count"]
            elif etype == ev.GRAZE:
                life["grazes"] += 1
            elif etype == ev.POWERUP_PICKUP:
                life["powerups"] += 1
            elif etype == ev.PLAYER_HIT:
                life["deaths"] += 1
            elif etype == ev.BOSS_KILLED:
                life["bosses"] += 1
                life["kills"] += 1
            elif etype == ev.RUN_END:
                summary = data["summary"]
                life["runs"] += 1
                if summary["win"]:
                    life["wins"] += 1
                life["hits"] += summary.get("hits", 0)
                life["best_score"] = max(life["best_score"], summary["score"])
                life["best_wave"] = max(life["best_wave"],
                                        summary.get("wave_reached", 0))
