"""Voxel Doom simulation: grid dungeons, imps and gunners, hitscan pistol.

Pure logic — the game layer renders it in first person. World coords: one
map cell = 2.0 units on the xz plane; y is up. Controls map from
InputState: up/down move along facing, left/right turn (strafe with focus).
"""
import math
import random

from game import events as ev

CELL = 2.0
PLAYER_RADIUS = 0.45
MOVE_SPEED = 4.6
TURN_SPEED = 2.7
FIRE_DELAY = 0.28
GUN_RANGE = 26.0
GUN_DAMAGE = 1

PLAYING_STATE = "playing"
WON = "won"
LOST = "lost"

MAPS = [
    ("THE YARD", [
        "################",
        "#P.....#.......#",
        "#......#...I...#",
        "#..I...#.......#",
        "#......##..##..#",
        "#..............#",
        "####..#....#...#",
        "#.....#..G.#...#",
        "#..M..#....#.A.#",
        "#.....######...#",
        "#..I.......#...#",
        "#......G...#..X#",
        "################",
    ]),
    ("CROSSFIRE HALLS", [
        "##################",
        "#P....#......#...#",
        "#.....#..I...#.G.#",
        "#..#..#......#...#",
        "#..#..###..###...#",
        "#..#.........#...#",
        "#..##..I..G..##..#",
        "#...#........#...#",
        "#.M.#..####..#.A.#",
        "#...#..#..#......#",
        "#.G....#..#..I...#",
        "#......#..#......#",
        "#..A...#..#..M..X#",
        "##################",
    ]),
    ("THE PIT", [
        "####################",
        "#P.....G...........#",
        "#..##..####..##..I.#",
        "#..#............#..#",
        "#..#..I..G...M..#..#",
        "#..#............#..#",
        "#..######..######..#",
        "#.....#......#.....#",
        "#..A..#..GG..#..M..#",
        "#.....#......#..I..#",
        "#..I..#......#.....#",
        "#.....###..###..#..#",
        "#..G............#..#",
        "#......A....I...#.X#",
        "####################",
    ]),
]

ENEMY_STATS = {
    "imp": {"hp": 2, "points": 100, "speed": 2.6, "melee_dmg": 12},
    "gunner": {"hp": 3, "points": 150, "speed": 1.6, "shot_dmg": 10},
}


class Enemy:
    def __init__(self, kind, x, z, rng):
        stats = ENEMY_STATS[kind]
        self.kind = kind
        self.x, self.z = x, z
        self.hp = stats["hp"]
        self.alerted = False
        self.attack_timer = rng.uniform(0.8, 1.8)
        self.hurt_timer = 0.0
        self.wander_angle = rng.uniform(0, math.tau)
        self.alive = True


class Projectile:
    def __init__(self, x, z, angle, speed=7.5):
        self.x, self.z = x, z
        self.vx = math.cos(angle) * speed
        self.vz = math.sin(angle) * speed
        self.alive = True


class Pickup:
    def __init__(self, kind, x, z):
        self.kind = kind  # medkit | ammo
        self.x, self.z = x, z
        self.alive = True


class DoomWorld:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.level_index = -1
        self.state = PLAYING_STATE
        self.won = False
        self.time = 0.0
        self.score = 0
        self.hp = 100
        self.ammo = 48
        self.fire_cooldown = 0.0
        self.prev_fire = False
        self.hurt_flash = 0.0
        self.events = []
        self.stats = {
            "kills": 0, "shots": 0, "hits": 0, "grazes": 0, "powerups": 0,
            "deaths": 0, "max_multiplier": 1.0, "duration": 0.0,
            "wave_reached": 0, "mode": "campaign",
        }
        self._load_level(0)

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
    def level_name(self):
        return MAPS[self.level_index][0]

    # -------------------------------------------------------------- levels
    def _load_level(self, index):
        self.level_index = index
        name, layout = MAPS[index]
        self.grid = [list(row) for row in layout]
        self.rows = len(self.grid)
        self.cols = len(self.grid[0])
        self.enemies = []
        self.projectiles = []
        self.pickups = []
        self.exit_cell = None
        for cy, row in enumerate(self.grid):
            for cx, ch in enumerate(row):
                wx, wz = cx * CELL, cy * CELL
                if ch == "P":
                    self.px, self.pz = wx, wz
                    self.angle = 0.0
                elif ch == "I":
                    self.enemies.append(Enemy("imp", wx, wz, self.rng))
                elif ch == "G":
                    self.enemies.append(Enemy("gunner", wx, wz, self.rng))
                elif ch == "M":
                    self.pickups.append(Pickup("medkit", wx, wz))
                elif ch == "A":
                    self.pickups.append(Pickup("ammo", wx, wz))
                elif ch == "X":
                    self.exit_cell = (cx, cy)
                if ch not in "#":
                    self.grid[cy][cx] = "."
        self.stats["wave_reached"] = index + 1
        self.emit(ev.WAVE_START, index=index, name=name, mode="campaign")

    # ----------------------------------------------------------- geometry
    def is_wall(self, cx, cy):
        if not (0 <= cx < self.cols and 0 <= cy < self.rows):
            return True
        return self.grid[cy][cx] == "#"

    def blocked(self, x, z, r=PLAYER_RADIUS):
        for ox in (-r, r):
            for oz in (-r, r):
                if self.is_wall(int(round((x + ox) / CELL)),
                                int(round((z + oz) / CELL))):
                    return True
        return False

    def line_of_sight(self, x0, z0, x1, z1):
        """Sampled ray across the grid — good enough at cell scale."""
        dist = math.hypot(x1 - x0, z1 - z0)
        steps = max(1, int(dist / 0.4))
        for i in range(1, steps):
            t = i / steps
            x = x0 + (x1 - x0) * t
            z = z0 + (z1 - z0) * t
            if self.is_wall(int(round(x / CELL)), int(round(z / CELL))):
                return False
        return True

    def _try_move(self, x, z, dx, dz):
        """Move with axis-separated sliding collision."""
        nx = x + dx
        if not self.blocked(nx, z):
            x = nx
        nz = z + dz
        if not self.blocked(x, nz):
            z = nz
        return x, z

    # -------------------------------------------------------------- update
    def update(self, dt, inp):
        if self.run_over:
            return
        self.time += dt
        self.stats["duration"] = self.time
        self.hurt_flash = max(0.0, self.hurt_flash - dt * 2.5)
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt

        self._update_player(dt, inp)
        self._update_enemies(dt)
        self._update_projectiles(dt)
        self._check_pickups()
        self._check_exit()

    def _update_player(self, dt, inp):
        turn = (1 if inp.right else 0) - (1 if inp.left else 0)
        if inp.focus:  # strafe instead of turn
            side = self.angle + math.pi / 2
            dx = math.cos(side) * turn * MOVE_SPEED * dt
            dz = math.sin(side) * turn * MOVE_SPEED * dt
            self.px, self.pz = self._try_move(self.px, self.pz, dx, dz)
        else:
            self.angle += turn * TURN_SPEED * dt

        forward = (1 if inp.up else 0) - (1 if inp.down else 0)
        if forward:
            dx = math.cos(self.angle) * forward * MOVE_SPEED * dt
            dz = math.sin(self.angle) * forward * MOVE_SPEED * dt
            self.px, self.pz = self._try_move(self.px, self.pz, dx, dz)

        clicked = inp.fire and not self.prev_fire
        self.prev_fire = inp.fire
        if clicked and self.fire_cooldown <= 0:
            self._fire()

    def _fire(self):
        if self.ammo <= 0:
            self._melee()
            return
        self.ammo -= 1
        self.fire_cooldown = FIRE_DELAY
        self.stats["shots"] += 1
        self.emit(ev.SHOT_FIRED, count=1)

        # hitscan: nearest live enemy within a narrow cone and LOS
        best = None
        for e in self.enemies:
            dx, dz = e.x - self.px, e.z - self.pz
            dist = math.hypot(dx, dz)
            if dist > GUN_RANGE or dist < 0.01:
                continue
            bearing = math.atan2(dz, dx)
            diff = (bearing - self.angle + math.pi) % math.tau - math.pi
            if abs(diff) > math.atan2(0.55, dist):
                continue
            if not self.line_of_sight(self.px, self.pz, e.x, e.z):
                continue
            if best is None or dist < best[0]:
                best = (dist, e)
        if best is None:
            return
        _, enemy = best
        self.stats["hits"] += 1
        enemy.hp -= GUN_DAMAGE
        enemy.hurt_timer = 0.15
        enemy.alerted = True
        if enemy.hp <= 0:
            enemy.alive = False
            self.enemies.remove(enemy)
            pts = ENEMY_STATS[enemy.kind]["points"]
            self.score += pts
            self.stats["kills"] += 1
            self.emit(ev.ENEMY_KILLED, kind=enemy.kind, x=enemy.x, y=enemy.z,
                      wx=enemy.x, wy=1.0, wz=enemy.z, points_awarded=pts)
        else:
            self.emit("doom_enemy_hurt", wx=enemy.x, wy=1.0, wz=enemy.z)

    def _melee(self):
        """Out of ammo: fists. Short range, never leaves you softlocked."""
        self.fire_cooldown = 0.5
        self.emit("doom_melee")
        for e in self.enemies:
            dx, dz = e.x - self.px, e.z - self.pz
            dist = math.hypot(dx, dz)
            if dist > 1.8:
                continue
            bearing = math.atan2(dz, dx)
            diff = (bearing - self.angle + math.pi) % math.tau - math.pi
            if abs(diff) > 0.9:
                continue
            e.hp -= 1
            e.hurt_timer = 0.15
            e.alerted = True
            if e.hp <= 0:
                e.alive = False
                self.enemies.remove(e)
                pts = ENEMY_STATS[e.kind]["points"]
                self.score += pts
                self.stats["kills"] += 1
                self.emit(ev.ENEMY_KILLED, kind=e.kind, x=e.x, y=e.z,
                          wx=e.x, wy=1.0, wz=e.z, points_awarded=pts)
            else:
                self.emit("doom_enemy_hurt", wx=e.x, wy=1.0, wz=e.z)
            return

    def _update_enemies(self, dt):
        for e in self.enemies:
            e.hurt_timer = max(0.0, e.hurt_timer - dt)
            dx, dz = self.px - e.x, self.pz - e.z
            dist = math.hypot(dx, dz)
            sees = dist < 14.0 and self.line_of_sight(e.x, e.z, self.px, self.pz)
            if sees:
                e.alerted = True
            if not e.alerted:
                continue

            stats = ENEMY_STATS[e.kind]
            if e.kind == "imp":
                if dist > 1.1:
                    step = stats["speed"] * dt
                    e.x, e.z = self._try_move(
                        e.x, e.z, dx / dist * step, dz / dist * step)
                e.attack_timer -= dt
                if dist < 1.4 and e.attack_timer <= 0:
                    e.attack_timer = 0.9
                    self._damage_player(stats["melee_dmg"], "imp")
            else:  # gunner: hold range, strafe a little, shoot on sight
                if sees:
                    if dist < 5.0:
                        step = -stats["speed"] * dt
                    elif dist > 11.0:
                        step = stats["speed"] * dt
                    else:
                        step = 0.0
                    if step:
                        e.x, e.z = self._try_move(
                            e.x, e.z, dx / dist * step, dz / dist * step)
                    e.wander_angle += dt * 1.7
                    strafe = math.sin(e.wander_angle) * stats["speed"] * 0.5 * dt
                    side = math.atan2(dz, dx) + math.pi / 2
                    e.x, e.z = self._try_move(
                        e.x, e.z, math.cos(side) * strafe, math.sin(side) * strafe)
                    e.attack_timer -= dt
                    if e.attack_timer <= 0:
                        e.attack_timer = self.rng.uniform(1.5, 2.4)
                        aim = math.atan2(dz, dx) + self.rng.uniform(-0.06, 0.06)
                        self.projectiles.append(Projectile(e.x, e.z, aim))
                        self.emit("doom_enemy_shot", wx=e.x, wy=1.0, wz=e.z)

    def _update_projectiles(self, dt):
        for p in self.projectiles:
            p.x += p.vx * dt
            p.z += p.vz * dt
            if self.is_wall(int(round(p.x / CELL)), int(round(p.z / CELL))):
                p.alive = False
                continue
            if math.hypot(p.x - self.px, p.z - self.pz) < 0.5:
                p.alive = False
                self._damage_player(ENEMY_STATS["gunner"]["shot_dmg"], "gunner")
        self.projectiles = [p for p in self.projectiles if p.alive]

    def _damage_player(self, amount, source):
        self.hp -= amount
        self.hurt_flash = 1.0
        self.emit(ev.PLAYER_HIT, lives_left=max(0, self.hp), x=self.px, y=self.pz)
        if self.hp <= 0:
            self.stats["deaths"] += 1
            self.state = LOST
            self.emit(ev.PLAYER_DEATH)
            self.emit(ev.RUN_END, win=False, summary=self.run_summary(False))

    def _check_pickups(self):
        for pk in self.pickups:
            if pk.alive and math.hypot(pk.x - self.px, pk.z - self.pz) < 0.9:
                pk.alive = False
                self.stats["powerups"] += 1
                if pk.kind == "medkit":
                    self.hp = min(100, self.hp + 35)
                else:
                    self.ammo += 24
                self.emit(ev.POWERUP_PICKUP, kind=pk.kind, x=pk.x, y=pk.z,
                          wx=pk.x, wy=0.6, wz=pk.z)
        self.pickups = [p for p in self.pickups if p.alive]

    def _check_exit(self):
        if self.exit_cell is None:
            return
        ex, ey = self.exit_cell
        if int(round(self.px / CELL)) == ex and int(round(self.pz / CELL)) == ey:
            bonus = 500 + min(self.hp, 100) * 5
            self.score += bonus
            self.emit(ev.LEVEL_CLEAR, index=self.level_index, bonus=bonus,
                      perfect=False)
            if self.level_index + 1 < len(MAPS):
                self._load_level(self.level_index + 1)
            else:
                self.won = True
                self.state = WON
                self.emit(ev.RUN_END, win=True, summary=self.run_summary(True))

    # -------------------------------------------------------------- output
    def run_summary(self, win):
        s = dict(self.stats)
        s["win"] = win
        s["score"] = self.score
        s["level_reached"] = self.level_index + 1
        s["final_hp"] = max(0, self.hp)
        s["accuracy"] = (s["hits"] / s["shots"]) if s["shots"] else 0.0
        return s
