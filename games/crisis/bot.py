"""Demo bot for attract mode and headless tests: shoots popped enemies,
ducks when a telegraph is about to fire or the clip runs dry."""
from game.entities import InputState
from games.crisis.world import AIMING


def demo_bot(world):
    aim_x, aim_y = getattr(world, "_bot_aim", (640.0, 430.0))
    inp = InputState(aim_x=aim_x, aim_y=aim_y)

    # incoming fire? duck. empty clip? duck to reload.
    danger = any(e.state == AIMING and e.telegraph < 0.35
                 for e in world.enemies)
    if danger or world.clip == 0:
        inp.focus = True
        return inp

    targets = [e for e in world.enemies
               if e.shootable and e.screen_x is not None]
    if not targets:
        return inp
    # prioritize the closest-to-firing enemy
    target = min(targets, key=lambda e: e.telegraph if e.state == AIMING else 9)
    dx = target.screen_x - aim_x
    dy = target.screen_y - aim_y
    inp.aim_x = aim_x + dx * 0.4
    inp.aim_y = aim_y + dy * 0.4
    world._bot_aim = (inp.aim_x, inp.aim_y)
    if dx * dx + dy * dy < (target.screen_r * 0.7) ** 2:
        inp.fire = not world.prev_fire
    return inp
