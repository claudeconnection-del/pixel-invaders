"""Voxel Crisis simulation: on-rails cover shooter.

The camera rides waypoints; enemies pop from cover, telegraph, and shoot.
Duck (focus) to avoid hits and reload your clip. Pure logic — the game
layer projects enemies to screen space for the mouse hitscan.
"""
import math
import random

from game import events as ev

CLIP_SIZE = 8
PLAYER_HP = 5
TRAVEL_TIME = 2.2

HIDDEN = "hidden"
RISING = "rising"
AIMING = "aiming"
SHOOTING = "shooting"

PLAYING_STATE = "playing"
TRAVELING = "traveling"
WON = "won"
LOST = "lost"

# stage layout: camera waypoints with enemy cover spots (world xz + facing)
STAGE = [
    {
        "cam": (0.0, 1.6, 10.0), "look": (0.0, 1.2, 0.0),
        "spots": [(-3.0, -2.0), (0.5, -3.0), (3.5, -1.5)],
    },
    {
        "cam": (6.0, 1.6, 6.0), "look": (10.0, 1.2, -2.0),
        "spots": [(8.0, -3.0), (11.0, -1.0), (13.0, -4.0), (9.5, -6.0)],
    },
    {
        "cam": (12.0, 1.6, 2.0), "look": (18.0, 1.4, -4.0),
        "spots": [(16.0, -6.0), (19.0, -8.0), (21.0, -5.0), (17.5, -10.0)],
    },
    {
        "cam": (18.0, 1.6, -6.0), "look": (24.0, 1.2, -12.0),
        "spots": [(22.0, -12.0), (25.0, -14.0), (27.0, -10.0),
                  (23.5, -16.0), (26.0, -17.0)],
    },
    {
        "cam": (26.0, 1.8, -14.0), "look": (32.0, 1.6, -20.0),
        "spots": [(30.0, -20.0), (33.0, -22.0), (35.0, -18.0),
                  (31.5, -24.0), (34.0, -25.0)],
    },
    {  # boss arena
        "cam": (32.0, 2.0, -22.0), "look": (38.0, 1.8, -28.0),
        "spots": [(38.0, -28.0), (35.5, -26.0), (40.5, -26.0)],
        "boss": True,
    },
]

QUICK_KILL_WINDOW = 0.8


class CoverEnemy:
    def __init__(self, x, z, rng, boss=False):
        self.x, self.z = x, z
        self.boss = boss
        self.hp = 25 if boss else 1
        self.max_hp = self.hp
        self.state = HIDDEN
        self.timer = rng.uniform(0.6, 2.2)
        self.telegraph = 0.0
        self.pop_frac = 0.0        # 0 hidden .. 1 fully up
        self.popped_at = None
        self.hurt_timer = 0.0
        self.alive = True
        # game layer caches projected screen position while popped:
        self.screen_x = None
        self.screen_y = None
        self.screen_r = 46.0

    @property
    def shootable(self):
        return self.alive and self.pop_frac > 0.35


class CrisisWorld:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.time = 0.0
        self.state = TRAVELING
        self.travel_t = 1.0  # arrive at stop 0 immediately-ish
        self.stop_index = -1
        self.enemies = []
        self.hp = PLAYER_HP
        self.clip = CLIP_SIZE
        self.ducking = False
        self.prev_fire = False
        self.score = 0
        self.won = False
        self.hurt_flash = 0.0
        self.events = []
        self.stats = {
            "kills": 0, "shots": 0, "hits": 0, "grazes": 0, "powerups": 0,
            "deaths": 0, "max_multiplier": 1.0, "duration": 0.0,
            "wave_reached": 0, "quick_kills": 0, "mode": "arcade",
        }
        self.cam = STAGE[0]["cam"]
        self.look = STAGE[0]["look"]
        self._travel_from = (self.cam, self.look)
        self._travel_to = (self.cam, self.look)

    # ------------------------------------------------------------- helpers
    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out = self.events
        self.events = []
        return out

    @property
    def run_over(self):
        return self.state in (WON, LOST)

    @property
    def stop(self):
        return STAGE[self.stop_index] if 0 <= self.stop_index < len(STAGE) else None

    # -------------------------------------------------------------- stops
    def _arrive(self, index):
        self.stop_index = index
        stop = STAGE[index]
        self.cam, self.look = stop["cam"], stop["look"]
        boss = stop.get("boss", False)
        self.enemies = []
        for i, (x, z) in enumerate(stop["spots"]):
            is_boss = boss and i == 0
            e = CoverEnemy(x, z, self.rng, boss=is_boss)
            self.enemies.append(e)
        self.state = PLAYING_STATE
        self.stats["wave_reached"] = index + 1
        name = "DREAD CAPTAIN" if boss else f"ZONE {index + 1}"
        self.emit(ev.WAVE_START, index=index, name=name, mode="arcade")
        if boss:
            self.emit(ev.BOSS_SPAWN)

    def _depart(self):
        nxt = self.stop_index + 1
        if nxt >= len(STAGE):
            self.won = True
            self.state = WON
            self.emit(ev.RUN_END, win=True, summary=self.run_summary(True))
            return
        self.state = TRAVELING
        self.travel_t = 0.0
        self._travel_from = (self.cam, self.look)
        self._travel_to = (STAGE[nxt]["cam"], STAGE[nxt]["look"])

    # -------------------------------------------------------------- update
    def update(self, dt, inp):
        if self.run_over:
            return
        self.time += dt
        self.stats["duration"] = self.time
        self.hurt_flash = max(0.0, self.hurt_flash - dt * 2.5)
        self.ducking = inp.focus

        if self.state == TRAVELING:
            self.travel_t += dt / TRAVEL_TIME
            k = min(1.0, self.travel_t)
            k = k * k * (3 - 2 * k)  # smoothstep
            fc, fl = self._travel_from
            tc, tl = self._travel_to
            self.cam = tuple(a + (b - a) * k for a, b in zip(fc, tc))
            self.look = tuple(a + (b - a) * k for a, b in zip(fl, tl))
            if self.travel_t >= 1.0:
                self._arrive(self.stop_index + 1)
            return

        # ducking reloads the clip
        if self.ducking and self.clip < CLIP_SIZE:
            self.clip = CLIP_SIZE
            self.emit("crisis_reload")

        clicked = inp.fire and not self.prev_fire
        self.prev_fire = inp.fire
        if clicked and not self.ducking:
            self._shoot(inp.aim_x, inp.aim_y)

        self._update_enemies(dt)

        if not self.enemies and self.state == PLAYING_STATE:
            bonus = 300 * (self.stop_index + 1)
            self.score += bonus
            self.emit(ev.WAVE_CLEAR, index=self.stop_index, name="",
                      untouched=False, bonus=bonus, mode="arcade")
            self._depart()

    def _shoot(self, aim_x, aim_y):
        if self.clip <= 0:
            self.emit("crisis_click")
            return
        self.clip -= 1
        self.stats["shots"] += 1
        self.emit(ev.SHOT_FIRED, count=1)
        for e in self.enemies:
            if not e.shootable or e.screen_x is None:
                continue
            dx, dy = aim_x - e.screen_x, aim_y - e.screen_y
            if dx * dx + dy * dy <= e.screen_r * e.screen_r:
                self._damage(e)
                return
        self.emit("crisis_miss", x=aim_x, y=aim_y)

    def _damage(self, e):
        self.stats["hits"] += 1
        e.hp -= 1
        e.hurt_timer = 0.15
        if e.hp > 0:
            self.emit("crisis_enemy_hurt", wx=e.x, wy=1.4, wz=e.z,
                      boss=e.boss)
            return
        e.alive = False
        self.enemies.remove(e)
        pts = 1000 if e.boss else 200
        quick = (e.popped_at is not None
                 and (self.time - e.popped_at) <= QUICK_KILL_WINDOW)
        if quick:
            pts += 100
            self.stats["quick_kills"] += 1
        self.score += pts
        self.stats["kills"] += 1
        self.emit(ev.ENEMY_KILLED, kind="boss" if e.boss else "trooper",
                  x=e.x, y=e.z, wx=e.x, wy=1.4, wz=e.z,
                  points_awarded=pts, quick=quick)
        if e.boss:
            self.emit(ev.BOSS_KILLED, x=e.x, y=e.z)

    def _update_enemies(self, dt):
        for e in self.enemies:
            e.hurt_timer = max(0.0, e.hurt_timer - dt)
            if e.state == HIDDEN:
                e.pop_frac = max(0.0, e.pop_frac - dt * 3)
                e.timer -= dt
                if e.timer <= 0:
                    e.state = RISING
            elif e.state == RISING:
                e.pop_frac = min(1.0, e.pop_frac + dt * 3.5)
                if e.pop_frac >= 1.0:
                    e.state = AIMING
                    e.popped_at = self.time
                    e.telegraph = 1.0 if e.boss else 1.5
            elif e.state == AIMING:
                e.telegraph -= dt
                if e.telegraph <= 0:
                    e.state = SHOOTING
                    self.emit("crisis_enemy_shot", wx=e.x, wy=1.6, wz=e.z)
                    if not self.ducking:
                        self._damage_player()
                    e.state = HIDDEN
                    e.timer = self.rng.uniform(0.9, 2.4)
            # SHOOTING resolves instantly above

    def _damage_player(self):
        self.hp -= 1
        self.hurt_flash = 1.0
        self.emit(ev.PLAYER_HIT, lives_left=max(0, self.hp),
                  x=self.cam[0], y=self.cam[2])
        if self.hp <= 0:
            self.stats["deaths"] += 1
            self.state = LOST
            self.emit(ev.PLAYER_DEATH)
            self.emit(ev.RUN_END, win=False, summary=self.run_summary(False))

    # -------------------------------------------------------------- output
    def run_summary(self, win):
        s = dict(self.stats)
        s["win"] = win
        s["score"] = self.score
        s["final_hp"] = max(0, self.hp)
        s["accuracy"] = (s["hits"] / s["shots"]) if s["shots"] else 0.0
        return s
