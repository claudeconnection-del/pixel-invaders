"""The bullet-hell simulation. Pure logic — no pygame, no GL.

Owns all entities, runs collisions/graze/scoring/wave progression, and emits
events (game.events) that the shell, stats, achievements, audio, and particle
systems consume. Deterministic under a seeded rng for testing.
"""
import math
import random

from game import events as ev
from game.entities import (
    FIELD_WIDTH,
    FIELD_HEIGHT,
    Player,
    Bullet,
    Enemy,
    Boss,
    PowerUp,
    circles_hit,
    dist_sq,
)
from game.patterns import PatternContext
from game.waves import (
    ENEMY_STATS,
    BOSS_MAX_HP,
    PHASE_THRESHOLDS,
    build_waves,
    build_boss_phases,
)

MAX_ENEMY_BULLETS = 400
MULTIPLIER_CAP = 5.0

# world.state values
INTRO = "intro"              # brief pause before wave 1
WAVE = "wave"
INTERMISSION = "intermission"
BOSS_FIGHT = "boss"
CELEBRATING = "celebrating"  # boss died, brief fanfare before run end
WON = "won"
LOST = "lost"


class World:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.player = Player()
        self.player_bullets = []
        self.enemy_bullets = []
        self.enemies = []
        self.powerups = []
        self.boss = None
        self.boss_patterns = []
        self.events = []
        self.score = 0
        self.multiplier = 1.0
        self.time = 0.0
        self.state = INTRO
        self.state_timer = 1.6
        self.wave_index = -1
        self.waves = build_waves(self.rng)
        self.boss_phase_factories = build_boss_phases(self.rng)
        self.hit_this_wave = False
        self.stats = {
            "kills": 0, "shots": 0, "hits": 0, "grazes": 0, "powerups": 0,
            "deaths": 0, "max_multiplier": 1.0, "duration": 0.0,
            "wave_reached": 1,
        }

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

    # ------------------------------------------------------------ spawning
    def _spawn_enemy_bullet(self, x, y, angle, speed, sprite="bullet_enemy",
                            r=5.0, curve=0.0):
        if len(self.enemy_bullets) >= MAX_ENEMY_BULLETS:
            return
        self.enemy_bullets.append(Bullet(
            x=x, y=y,
            vx=math.cos(angle) * speed, vy=math.sin(angle) * speed,
            r=r, sprite=sprite, curve=curve,
        ))

    def _start_wave(self, index):
        self.wave_index = index
        self.state = WAVE
        self.hit_this_wave = False
        self.stats["wave_reached"] = max(self.stats["wave_reached"], index + 1)
        wave = self.waves[index]
        for spec in wave["enemies"]:
            hp, points, radius = ENEMY_STATS[spec["kind"]]
            e = Enemy(
                kind=spec["kind"],
                slot_x=spec["slot"][0], slot_y=spec["slot"][1],
                spawn_x=spec["spawn"][0], spawn_y=spec["spawn"][1],
                hp=hp, points=points, radius=radius,
                entry_delay=spec["entry_delay"],
                bob_phase=self.rng.uniform(0, math.tau),
                patterns=spec["patterns"](),
            )
            self.enemies.append(e)
        self.emit(ev.WAVE_START, index=index, name=wave["name"])

    def _start_boss(self):
        self.state = BOSS_FIGHT
        self.stats["wave_reached"] = len(self.waves) + 1
        self.hit_this_wave = False
        self.boss = Boss(hp=BOSS_MAX_HP, max_hp=BOSS_MAX_HP)
        self.boss_patterns = self.boss_phase_factories[1]()
        self.emit(ev.BOSS_SPAWN)

    # -------------------------------------------------------------- update
    def update(self, dt, inp):
        self.time += dt
        if not self.run_over:
            self.stats["duration"] = self.time

        if self.player.alive and not self.run_over:
            self.player.update(dt, inp)
            self._handle_player_fire(inp)

        self._update_state_machine(dt)
        self._update_enemies(dt)
        self._update_boss(dt)

        for b in self.player_bullets:
            b.update(dt)
        for b in self.enemy_bullets:
            b.update(dt)
        for p in self.powerups:
            p.update(dt)

        if not self.run_over:
            self._collide_player_bullets()
            self._collide_enemy_bullets()
            self._collide_powerups()

        self.player_bullets = [b for b in self.player_bullets if b.alive]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.alive]
        self.powerups = [p for p in self.powerups if p.alive]

        # multiplier decays gently toward 1.0
        if self.multiplier > 1.0:
            self.multiplier = max(1.0, self.multiplier - 0.05 * dt)

    def _update_state_machine(self, dt):
        if self.state == INTRO:
            self.state_timer -= dt
            if self.state_timer <= 0:
                self._start_wave(0)
        elif self.state == WAVE:
            if not self.enemies:
                wave = self.waves[self.wave_index]
                bonus = int(300 * (self.wave_index + 1) * self.multiplier)
                self.score += bonus
                self.emit(ev.WAVE_CLEAR, index=self.wave_index, name=wave["name"],
                          untouched=not self.hit_this_wave, bonus=bonus)
                self.state = INTERMISSION
                self.state_timer = 2.2
        elif self.state == INTERMISSION:
            self.state_timer -= dt
            if self.state_timer <= 0:
                if self.wave_index + 1 < len(self.waves):
                    self._start_wave(self.wave_index + 1)
                else:
                    self._start_boss()
        elif self.state == CELEBRATING:
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.state = WON
                self.emit(ev.RUN_END, win=True, summary=self.run_summary(True))

    def _handle_player_fire(self, inp):
        p = self.player
        if not inp.fire or p.fire_cooldown > 0:
            return
        p.fire_cooldown = p.fire_delay
        angles = [-math.pi / 2]
        if p.spread_timer > 0:
            angles = [-math.pi / 2 - 0.21, -math.pi / 2, -math.pi / 2 + 0.21]
        for a in angles:
            self.player_bullets.append(Bullet(
                x=p.x, y=p.y - 24,
                vx=math.cos(a) * 700, vy=math.sin(a) * 700,
                r=6.0, sprite="bullet_player", from_player=True,
            ))
        self.stats["shots"] += len(angles)
        self.emit(ev.SHOT_FIRED, count=len(angles))

    def _pattern_ctx(self):
        return PatternContext(
            spawn=self._spawn_enemy_bullet,
            player_x=self.player.x, player_y=self.player.y,
            bullet_budget=MAX_ENEMY_BULLETS - len(self.enemy_bullets),
        )

    def _update_enemies(self, dt):
        if not self.enemies:
            return
        formation_offset = math.sin(self.time * 0.45) * 26
        firing_allowed = self.state == WAVE and not self.run_over
        for e in self.enemies:
            in_formation = e.update(dt, formation_offset)
            if in_formation and firing_allowed and self.player.alive:
                ctx = self._pattern_ctx()
                for pat in e.patterns:
                    pat.update(dt, ctx, e.x, e.y)

    def _update_boss(self, dt):
        boss = self.boss
        if boss is None or not boss.alive:
            return
        boss.update(dt)
        if self.state == BOSS_FIGHT and self.player.alive:
            ctx = self._pattern_ctx()
            for pat in self.boss_patterns:
                pat.update(dt, ctx, boss.x, boss.y)

    # ---------------------------------------------------------- collisions
    def _collide_player_bullets(self):
        for b in self.player_bullets:
            if not b.alive:
                continue
            for e in self.enemies:
                if e.alive and circles_hit(b.x, b.y, b.r, e.x, e.y, e.radius):
                    b.alive = False
                    self.stats["hits"] += 1
                    e.hp -= 1
                    if e.hp <= 0:
                        e.alive = False
                        self._on_enemy_killed(e)
                    break
            if b.alive and self.boss is not None and self.boss.alive:
                if circles_hit(b.x, b.y, b.r, self.boss.x, self.boss.y, self.boss.radius):
                    b.alive = False
                    self.stats["hits"] += 1
                    self._damage_boss(1)
        self.enemies = [e for e in self.enemies if e.alive]

    def _on_enemy_killed(self, e):
        pts = int(e.points * self.multiplier)
        self.score += pts
        self.stats["kills"] += 1
        self.emit(ev.ENEMY_KILLED, kind=e.kind, x=e.x, y=e.y, points_awarded=pts)
        if self.rng.random() < 0.12:
            kind = self.rng.choices(
                ["spread", "rapid", "shield"], weights=[40, 40, 20])[0]
            self.powerups.append(PowerUp(kind=kind, x=e.x, y=e.y))
            self.emit(ev.POWERUP_SPAWN, kind=kind, x=e.x, y=e.y)

    def _damage_boss(self, amount):
        boss = self.boss
        boss.hp -= amount
        if boss.hp <= 0:
            boss.alive = False
            pts = int(5000 * self.multiplier)
            self.score += pts
            self.stats["kills"] += 1
            self.emit(ev.BOSS_KILLED, x=boss.x, y=boss.y)
            self.enemy_bullets.clear()
            self.state = CELEBRATING
            self.state_timer = 2.5
            return
        # phase transitions at fixed hp fractions
        frac = boss.hp_frac
        new_phase = 1 + sum(1 for t in PHASE_THRESHOLDS if frac <= t)
        if new_phase != boss.phase:
            boss.phase = new_phase
            self.boss_patterns = self.boss_phase_factories[new_phase]()
            self.enemy_bullets.clear()
            self.emit(ev.BOSS_PHASE, phase=new_phase, x=boss.x, y=boss.y)

    def _collide_enemy_bullets(self):
        p = self.player
        if not p.alive:
            return
        for b in self.enemy_bullets:
            if not b.alive:
                continue
            if circles_hit(b.x, b.y, b.r, p.x, p.y, p.hitbox_r):
                if p.invuln > 0:
                    continue
                b.alive = False
                self._on_player_hit()
                continue
            if not b.grazed:
                graze_range = p.graze_r + b.r
                if dist_sq(b.x, b.y, p.x, p.y) <= graze_range * graze_range:
                    b.grazed = True
                    self.stats["grazes"] += 1
                    self.multiplier = min(MULTIPLIER_CAP, self.multiplier + 0.1)
                    self.stats["max_multiplier"] = max(
                        self.stats["max_multiplier"], self.multiplier)
                    self.score += int(10 * self.multiplier)
                    self.emit(ev.GRAZE, x=b.x, y=b.y)

    def _on_player_hit(self):
        p = self.player
        self.hit_this_wave = True
        if p.shield:
            p.shield = False
            p.invuln = 1.0
            self.emit(ev.SHIELD_BREAK, x=p.x, y=p.y)
            return
        p.lives -= 1
        self.stats["deaths"] += 1
        self.multiplier = 1.0
        self.enemy_bullets.clear()  # mercy rule
        self.emit(ev.PLAYER_HIT, lives_left=p.lives, x=p.x, y=p.y)
        if p.lives <= 0:
            p.alive = False
            self.state = LOST
            self.emit(ev.PLAYER_DEATH)
            self.emit(ev.RUN_END, win=False, summary=self.run_summary(False))
        else:
            p.invuln = 2.0
            p.x, p.y = FIELD_WIDTH / 2, FIELD_HEIGHT - 70

    def _collide_powerups(self):
        p = self.player
        if not p.alive:
            return
        for pu in self.powerups:
            if pu.alive and circles_hit(pu.x, pu.y, pu.radius, p.x, p.y, 20):
                pu.alive = False
                self.stats["powerups"] += 1
                if pu.kind == "spread":
                    p.spread_timer = 10.0
                elif pu.kind == "rapid":
                    p.rapid_timer = 10.0
                elif pu.kind == "shield":
                    p.shield = True
                self.emit(ev.POWERUP_PICKUP, kind=pu.kind, x=pu.x, y=pu.y)

    # -------------------------------------------------------------- output
    def run_summary(self, win):
        s = dict(self.stats)
        s["win"] = win
        s["score"] = self.score
        s["accuracy"] = (s["hits"] / s["shots"]) if s["shots"] else 0.0
        return s
