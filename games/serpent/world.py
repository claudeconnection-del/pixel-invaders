"""Voxel Serpent simulation. Pure logic — no pygame, no GL.

Grid snake on the shared field: eat fruit, grow, speed up. Obstacle walls
appear as you feed. Death by wall, obstacle, or self. Score scales with
length; gold fruit is rare and worth a detour.
"""
import random

from game import events as ev

COLS = 15
ROWS = 16
CELL = 40
X0 = (640 - COLS * CELL) // 2
Y0 = 70

PLAYING_STATE = "playing"
LOST = "lost"

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


def field_pos(cell):
    cx, cy = cell
    return X0 + cx * CELL + CELL / 2, Y0 + cy * CELL + CELL / 2


class SerpentWorld:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        mid = (COLS // 2, ROWS // 2)
        self.body = [(mid[0] - i, mid[1]) for i in range(3)]  # head first
        self.direction = "right"
        self.pending_direction = "right"
        self.grow = 0
        self.obstacles = set()
        self.fruit = None
        self.fruit_kind = "apple"
        self.events = []
        self.score = 0
        self.time = 0.0
        self.move_timer = 0.0
        self.fruits_eaten = 0
        self.golds_eaten = 0
        self.state = PLAYING_STATE
        self.won = False
        self.stats = {
            "kills": 0, "shots": 0, "hits": 0, "grazes": 0, "powerups": 0,
            "deaths": 0, "max_multiplier": 1.0, "duration": 0.0,
            "wave_reached": 0, "length": 3, "golds": 0, "mode": "arcade",
        }
        self._spawn_fruit()

    # ------------------------------------------------------------- helpers
    def emit(self, etype, **data):
        self.events.append((etype, data))

    def drain_events(self):
        out = self.events
        self.events = []
        return out

    @property
    def run_over(self):
        return self.state == LOST

    @property
    def length(self):
        return len(self.body)

    def _step_interval(self):
        return max(0.07, 0.16 - 0.0035 * (self.length - 3))

    def _free_cells(self):
        occupied = set(self.body) | self.obstacles
        if self.fruit:
            occupied.add(self.fruit)
        return [(x, y) for x in range(COLS) for y in range(ROWS)
                if (x, y) not in occupied]

    def _spawn_fruit(self):
        free = self._free_cells()
        if not free:
            return
        self.fruit = self.rng.choice(free)
        self.fruit_kind = "gold" if self.rng.random() < 0.1 else "apple"

    def _spawn_obstacle(self):
        """A short wall, never adjacent to the head's next few cells."""
        head = self.body[0]
        hx, hy = head
        danger = {(hx + dx, hy + dy) for dx in range(-3, 4) for dy in range(-3, 4)}
        candidates = [c for c in self._free_cells() if c not in danger]
        if not candidates:
            return
        start = self.rng.choice(candidates)
        horizontal = self.rng.random() < 0.5
        length = self.rng.randint(2, 3)
        for i in range(length):
            cell = (start[0] + (i if horizontal else 0),
                    start[1] + (0 if horizontal else i))
            if 0 <= cell[0] < COLS and 0 <= cell[1] < ROWS \
                    and cell not in danger and cell != self.fruit \
                    and cell not in self.body:
                self.obstacles.add(cell)

    # -------------------------------------------------------------- update
    def apply_input(self, inp):
        wanted = None
        if inp.up:
            wanted = "up"
        elif inp.down:
            wanted = "down"
        elif inp.left:
            wanted = "left"
        elif inp.right:
            wanted = "right"
        if wanted and wanted != OPPOSITE[self.direction]:
            self.pending_direction = wanted

    def update(self, dt, inp):
        if self.run_over:
            return
        self.time += dt
        self.stats["duration"] = self.time
        self.apply_input(inp)
        self.move_timer += dt
        if self.move_timer >= self._step_interval():
            self.move_timer = 0.0
            self._step()

    def _step(self):
        self.direction = self.pending_direction
        dx, dy = DIRS[self.direction]
        hx, hy = self.body[0]
        new_head = (hx + dx, hy + dy)

        out = not (0 <= new_head[0] < COLS and 0 <= new_head[1] < ROWS)
        tail_moving = self.grow == 0
        body_check = self.body[:-1] if tail_moving else self.body
        if out or new_head in self.obstacles or new_head in body_check:
            self._die(new_head)
            return

        self.body.insert(0, new_head)
        if self.grow > 0:
            self.grow -= 1
        else:
            self.body.pop()

        if new_head == self.fruit:
            self._eat()

        self.stats["length"] = max(self.stats["length"], self.length)

    def _eat(self):
        kind = self.fruit_kind
        fx, fy = field_pos(self.fruit)
        self.fruits_eaten += 1
        if kind == "gold":
            self.golds_eaten += 1
            self.stats["golds"] = self.golds_eaten
            self.grow += 3
            pts = 50 + self.length * 2
        else:
            self.grow += 1
            pts = 10 + self.length
        self.score += pts
        self.stats["powerups"] += 1  # lifetime pickups counter
        self.emit(ev.FRUIT_EATEN, kind=kind, x=fx, y=fy, length=self.length)
        self.emit(ev.POWERUP_PICKUP, kind=kind, x=fx, y=fy)
        if self.fruits_eaten % 5 == 0:
            self._spawn_obstacle()
        self._spawn_fruit()

    def _die(self, at_cell):
        fx, fy = field_pos(self.body[0])
        self.state = LOST
        self.stats["deaths"] += 1
        self.emit(ev.PLAYER_HIT, lives_left=0, x=fx, y=fy)
        self.emit(ev.PLAYER_DEATH)
        self.emit(ev.RUN_END, win=False, summary=self.run_summary(False))

    # -------------------------------------------------------------- output
    def run_summary(self, win):
        s = dict(self.stats)
        s["win"] = win
        s["score"] = self.score
        s["length"] = self.length
        return s
