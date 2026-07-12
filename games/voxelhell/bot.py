"""Demo bot for attract mode and headless tests."""
from game.entities import InputState


def demo_bot(world):
    """Dodge bullets predicted to hit within ~0.7s, otherwise line up under
    the nearest target. Always firing."""
    inp = InputState(fire=True)
    p = world.player
    danger = None
    for b in world.enemy_bullets:
        if b.vy <= 10:
            continue
        t_impact = (p.y - b.y) / b.vy
        if not (0 <= t_impact <= 0.7):
            continue
        x_at_impact = b.x + b.vx * t_impact
        if abs(x_at_impact - p.x) < 26:
            if danger is None or t_impact < danger[0]:
                danger = (t_impact, x_at_impact)
    if danger is not None:
        if danger[1] >= p.x:
            inp.left = True
        else:
            inp.right = True
        return inp
    targets = world.enemies or ([world.boss] if world.boss and world.boss.alive else [])
    targets = [t for t in targets if t.y > -20]
    if targets:
        tx = min(targets, key=lambda e: abs(e.x - p.x)).x
        if tx < p.x - 8:
            inp.left = True
        elif tx > p.x + 8:
            inp.right = True
    return inp
