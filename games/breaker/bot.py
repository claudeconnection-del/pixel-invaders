"""Demo bot for attract mode and headless tests."""
from game.entities import InputState


def demo_bot(world):
    """Follow the most-dangerous descending ball; hold fire for lasers."""
    inp = InputState(fire=True)
    falling = [b for b in world.balls if b.vy > 0]
    target = None
    if falling:
        target = min(falling, key=lambda b: (world.paddle_y - b.y))
    elif world.balls:
        target = world.balls[0]
    tx = target.x if target else 320
    if tx < world.paddle_x - 8:
        inp.left = True
    elif tx > world.paddle_x + 8:
        inp.right = True
    return inp
