"""Event types emitted by the world simulation each frame.

Consumers (stats, achievements, sfx, particles, toasts) read the frame's event
list; the simulation never knows they exist.
"""

ENEMY_KILLED = "enemy_killed"      # {kind, x, y, points_awarded}
PLAYER_HIT = "player_hit"          # {lives_left, x, y}
PLAYER_DEATH = "player_death"      # {} (final life lost)
SHIELD_BREAK = "shield_break"      # {x, y}
GRAZE = "graze"                    # {x, y}
SHOT_FIRED = "shot_fired"          # {count}
WAVE_START = "wave_start"          # {index, name}
WAVE_CLEAR = "wave_clear"          # {index, name, untouched, bonus}
POWERUP_SPAWN = "powerup_spawn"    # {kind, x, y}
POWERUP_PICKUP = "powerup_pickup"  # {kind, x, y}
BOSS_SPAWN = "boss_spawn"          # {}
BOSS_PHASE = "boss_phase"          # {phase, x, y}
BOSS_KILLED = "boss_killed"        # {x, y}
RUN_END = "run_end"                # {win, summary}
