"""Wave and boss choreography for the campaign.

Each wave is a list of enemy specs; the world instantiates them. Pattern
factories are lambdas so every enemy gets its own pattern state.
"""
from games.voxelhell.patterns import AimedBurst, RadialBurst, Spiral, WallVolley

ENEMY_STATS = {
    # kind: (hp, points, radius)
    "squid": (1, 30, 20.0),
    "crab": (1, 20, 22.0),
    "octo": (2, 10, 22.0),
    "elite": (3, 50, 20.0),
}


def _row(kind, count, y, patterns_factory, x_margin=70, entry_stagger=0.12,
         delay_base=0.0, spawn_side=0):
    """Lay `count` enemies of `kind` evenly across a row at height y."""
    from game.entities import FIELD_WIDTH
    specs = []
    span = FIELD_WIDTH - 2 * x_margin
    for i in range(count):
        x = x_margin + span * (i / (count - 1) if count > 1 else 0.5)
        spawn_x = x if spawn_side == 0 else (-60 if spawn_side < 0 else FIELD_WIDTH + 60)
        specs.append({
            "kind": kind,
            "slot": (x, y),
            "spawn": (spawn_x, -60),
            "entry_delay": delay_base + i * entry_stagger,
            "patterns": patterns_factory,
        })
    return specs


def build_waves(rng):
    """Returns the campaign waves. rng is used by patterns that need
    randomness (wall gaps) so runs are reproducible under a seeded rng."""
    waves = []

    # Wave 1 — First Contact: gentle aimed shots only
    waves.append({
        "name": "FIRST CONTACT",
        "enemies":
            _row("octo", 6, 110, lambda: [AimedBurst(interval=2.4, speed=150, start_delay=1.5)])
            + _row("octo", 6, 180, lambda: [AimedBurst(interval=2.8, speed=140, start_delay=2.5)],
                   delay_base=0.5),
    })

    # Wave 2 — Crossfire: aimed fans + first radial bursts
    waves.append({
        "name": "CROSSFIRE",
        "enemies":
            _row("crab", 8, 100, lambda: [AimedBurst(interval=2.2, count=3, spread_deg=14,
                                                     speed=165, start_delay=1.5)])
            + _row("octo", 8, 175, lambda: [RadialBurst(interval=3.4, count=10, speed=110,
                                                        start_delay=2.5)], delay_base=0.6),
    })

    # Wave 3 — Spiral Down: center elites spin spirals, squids snipe
    waves.append({
        "name": "SPIRAL DOWN",
        "enemies":
            _row("squid", 6, 95, lambda: [AimedBurst(interval=1.9, speed=195, start_delay=1.5)])
            + _row("elite", 2, 170, lambda: [Spiral(arms=2, rate=7, speed=115, omega_deg=80,
                                                    start_delay=2.0)],
                   x_margin=220, delay_base=0.8)
            + _row("crab", 6, 245, lambda: [AimedBurst(interval=2.6, count=2, spread_deg=24,
                                                       speed=150, start_delay=3.0)],
                   delay_base=1.0),
    })

    # Wave 4 — The Wall: falling curtains with gaps + radial pressure
    waves.append({
        "name": "THE WALL",
        "enemies":
            _row("elite", 4, 90, lambda: [WallVolley(interval=3.6, columns=13, speed=125,
                                                     gap_cols=3, start_delay=2.0, rng=rng)],
                 x_margin=110)
            + _row("squid", 8, 170, lambda: [AimedBurst(interval=2.1, speed=185, start_delay=1.5),
                                             RadialBurst(interval=4.4, count=8, speed=105,
                                                         start_delay=3.5)], delay_base=0.7),
    })

    # Wave 5 — Maelstrom: everything at once
    waves.append({
        "name": "MAELSTROM",
        "enemies":
            _row("elite", 3, 95, lambda: [Spiral(arms=2, rate=8, speed=125, omega_deg=110,
                                                 curve_deg=8, start_delay=2.0)],
                 x_margin=160)
            + _row("crab", 8, 170, lambda: [AimedBurst(interval=1.8, count=3, spread_deg=16,
                                                       speed=175, start_delay=1.5)],
                   delay_base=0.5, spawn_side=-1)
            + _row("squid", 7, 245, lambda: [RadialBurst(interval=3.0, count=12, speed=120,
                                                         rotate_deg=15, start_delay=3.0)],
                   delay_base=1.0, spawn_side=1),
    })

    return waves


BOSS_MAX_HP = 240

def build_boss_phases(rng):
    """Pattern sets per boss phase; world swaps them at hp thresholds."""
    return {
        1: lambda: [
            RadialBurst(interval=1.7, count=18, speed=135, rotate_deg=11, start_delay=1.0),
            AimedBurst(interval=1.0, count=3, spread_deg=12, speed=190, start_delay=1.6),
        ],
        2: lambda: [
            Spiral(arms=2, rate=9, speed=125, omega_deg=95, start_delay=0.5),
            WallVolley(interval=3.4, columns=15, speed=130, gap_cols=3, start_delay=2.0, rng=rng),
        ],
        3: lambda: [
            Spiral(arms=3, rate=10, speed=140, omega_deg=-130, curve_deg=6, start_delay=0.5),
            RadialBurst(interval=2.0, count=26, speed=150, rotate_deg=7, start_delay=1.2),
            AimedBurst(interval=0.85, count=1, speed=230, start_delay=0.8),
        ],
    }


PHASE_THRESHOLDS = (2 / 3, 1 / 3)  # hp fractions where phase 2 and 3 begin

ENDLESS_BOSS_EVERY = 5  # every Nth endless sector is a boss

ENDLESS_NAMES = ["SECTOR SWEEP", "AMBUSH", "GAUNTLET", "ONSLAUGHT",
                 "SWARM", "BLOCKADE", "INCURSION", "FLASHPOINT"]


def endless_difficulty(index):
    """Difficulty multiplier for endless sector `index` (0-based)."""
    return min(3.0, 1.0 + index * 0.09)


def build_endless_wave(rng, index):
    """Procedural endless sector: 2-3 rows sampled from templates, pattern
    parameters scaled by depth."""
    d = endless_difficulty(index)

    def aimed():
        return [AimedBurst(interval=rng.uniform(2.0, 2.8), count=rng.choice([1, 1, 3]),
                           spread_deg=14, speed=155, start_delay=rng.uniform(1.5, 2.5))]

    def radial():
        return [RadialBurst(interval=rng.uniform(3.0, 4.0), count=rng.choice([8, 10, 12]),
                            speed=115, start_delay=rng.uniform(2.0, 3.5))]

    def spiral():
        return [Spiral(arms=2, rate=6, speed=115, omega_deg=rng.choice([75, -85]),
                       start_delay=2.0)]

    def wall():
        return [WallVolley(interval=3.8, columns=13, speed=120, gap_cols=3,
                           start_delay=2.2, rng=rng)]

    # deeper sectors unlock nastier row archetypes
    archetypes = [("octo", aimed), ("crab", aimed), ("crab", radial)]
    if index >= 2:
        archetypes += [("squid", aimed), ("squid", radial)]
    if index >= 4:
        archetypes += [("elite", spiral)]
    if index >= 6:
        archetypes += [("elite", wall)]

    n_rows = 2 if index < 3 else 3
    rows = []
    for row_i in range(n_rows):
        kind, pattern_factory = rng.choice(archetypes)
        count = min(9, (4 if kind == "elite" else 6) + index // 3)
        if kind == "elite":
            count = min(count, 4)
        y = 95 + row_i * 78
        side = rng.choice([0, -1, 1])
        rows += _row(kind, count, y, pattern_factory,
                     delay_base=row_i * 0.5, spawn_side=side)

    return {
        "name": f"{rng.choice(ENDLESS_NAMES)} {index + 1}",
        "enemies": rows,
        "difficulty": d,
    }
