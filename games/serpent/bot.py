"""Demo bot for attract mode and headless tests."""
from game.entities import InputState
from games.serpent.world import DIRS, OPPOSITE, COLS, ROWS


def demo_bot(world):
    """Greedy fruit chase with 1-step survival lookahead."""
    head = world.body[0]
    fruit = world.fruit
    deadly = set(world.body[:-1]) | world.obstacles

    def safe(direction):
        dx, dy = DIRS[direction]
        nxt = (head[0] + dx, head[1] + dy)
        return (0 <= nxt[0] < COLS and 0 <= nxt[1] < ROWS
                and nxt not in deadly)

    prefs = []
    if fruit:
        if fruit[0] > head[0]:
            prefs.append("right")
        elif fruit[0] < head[0]:
            prefs.append("left")
        if fruit[1] > head[1]:
            prefs.append("down")
        elif fruit[1] < head[1]:
            prefs.append("up")
    prefs += ["up", "left", "down", "right"]
    for d in prefs:
        if d != OPPOSITE[world.direction] and safe(d):
            return InputState(**{d: True})
    return InputState()
