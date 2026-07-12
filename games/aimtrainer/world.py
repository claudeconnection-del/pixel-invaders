"""Voxel Aim simulation: gridshot-style target popping, 60-second score
attack. Pure logic; the game layer injects per-frame screen positions for
the targets (projected by the renderer), so hit-testing stays headless.
"""
import random

from game import events as ev

RUN_SECONDS = 60.0
ACTIVE_TARGETS = 3
TARGET_RADIUS = 0.55        # world units
SPAWN_DELAY = 0.12

# target wall bounds (world coords; camera looks down -z)
WALL_Z = -6.0
X_RANGE = (-5.4, 5.4)
Y_RANGE = (0.8, 5.2)

PLAYING_STATE = "playing"
DONE = "done"


class Target:
    def __init__(self, rng, now):
        self.x = rng.uniform(*X_RANGE)
        self.y = rng.uniform(*Y_RANGE)
        self.z = WALL_Z
        self.born = now
        self.alive = True
        # game layer fills these after projecting each frame:
        self.screen_x = None
        self.screen_y = None
        self.screen_r = 40.0


class AimWorld:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.time = 0.0
        self.state = PLAYING_STATE
        self.targets = []
        self.respawn_queue = []  # [spawn_at_time, ...]
        self.score = 0
        self.multiplier = 1.0
        self.events = []
        self.prev_fire = False
        self.won = False
        self.stats = {
            "kills": 0, "shots": 0, "hits": 0, "grazes": 0, "powerups": 0,
            "deaths": 0, "max_multiplier": 1.0, "duration": 0.0,
            "wave_reached": 0, "best_reaction": None, "reaction_sum": 0.0,
            "mode": "gridshot",
        }
        for _ in range(ACTIVE_TARGETS):
            self.targets.append(Target(self.rng, 0.0))

    # ------------------------------------------------------------- helpers
    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out = self.events
        self.events = []
        return out

    @property
    def run_over(self):
        return self.state == DONE

    @property
    def time_left(self):
        return max(0.0, RUN_SECONDS - self.time)

    # -------------------------------------------------------------- update
    def update(self, dt, inp):
        if self.run_over:
            return
        self.time += dt
        self.stats["duration"] = self.time

        if self.time >= RUN_SECONDS:
            self._finish()
            return

        # respawns
        due = [t for t in self.respawn_queue if t <= self.time]
        for t in due:
            self.respawn_queue.remove(t)
            self.targets.append(Target(self.rng, self.time))

        # rising-edge fire
        clicked = inp.fire and not self.prev_fire
        self.prev_fire = inp.fire
        if clicked:
            self._shoot(inp.aim_x, inp.aim_y)

    def _shoot(self, aim_x, aim_y):
        self.stats["shots"] += 1
        self.emit(ev.SHOT_FIRED, count=1)
        hit = None
        for target in self.targets:
            if target.screen_x is None:
                continue
            dx = aim_x - target.screen_x
            dy = aim_y - target.screen_y
            if dx * dx + dy * dy <= target.screen_r * target.screen_r:
                hit = target
                break
        if hit is None:
            self.multiplier = 1.0
            self.emit("aim_miss", x=aim_x, y=aim_y)
            return

        self.targets.remove(hit)
        self.respawn_queue.append(self.time + SPAWN_DELAY)
        reaction = self.time - hit.born
        self.stats["hits"] += 1
        self.stats["kills"] += 1
        self.stats["reaction_sum"] += reaction
        best = self.stats["best_reaction"]
        if best is None or reaction < best:
            self.stats["best_reaction"] = reaction
        pts = int(100 * self.multiplier)
        self.score += pts
        self.multiplier = min(3.0, self.multiplier + 0.25)
        self.stats["max_multiplier"] = max(self.stats["max_multiplier"],
                                           self.multiplier)
        self.emit(ev.ENEMY_KILLED, kind="target", x=hit.x, y=hit.y,
                  wx=hit.x, wy=hit.y, wz=hit.z, points_awarded=pts,
                  reaction=reaction)

    def _finish(self):
        self.state = DONE
        self.won = True  # completing the timer is a "win" for score attack
        self.emit(ev.RUN_END, win=True, summary=self.run_summary(True))

    # -------------------------------------------------------------- output
    def run_summary(self, win):
        s = dict(self.stats)
        s["win"] = win
        s["score"] = self.score
        s["accuracy"] = (s["hits"] / s["shots"]) if s["shots"] else 0.0
        s["avg_reaction"] = (s["reaction_sum"] / s["hits"]) if s["hits"] else 0.0
        s.pop("reaction_sum", None)
        return s
