"""Demo bot for attract mode and headless tests: drifts the crosshair
toward the nearest projected target and clicks when close. Keeps its aim
state on the world object between calls."""
from game.entities import InputState


def demo_bot(world):
    aim_x, aim_y = getattr(world, "_bot_aim", (640.0, 430.0))
    targets = [t for t in world.targets if t.screen_x is not None]
    inp = InputState(aim_x=aim_x, aim_y=aim_y)
    if not targets:
        return inp
    target = min(targets, key=lambda t: (t.screen_x - aim_x) ** 2
                 + (t.screen_y - aim_y) ** 2)
    dx = target.screen_x - aim_x
    dy = target.screen_y - aim_y
    inp.aim_x = aim_x + dx * 0.3
    inp.aim_y = aim_y + dy * 0.3
    world._bot_aim = (inp.aim_x, inp.aim_y)
    if dx * dx + dy * dy < (target.screen_r * 0.8) ** 2:
        inp.fire = not world.prev_fire  # click edges, not holds
    return inp
