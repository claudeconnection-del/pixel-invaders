"""Demo bot for attract mode and headless tests: BFS-pathfinds to the
nearest enemy (then the exit), turns/moves toward the next path cell, and
fires when an enemy is lined up."""
import math
from collections import deque

from game.entities import InputState
from games.voxeldoom.world import CELL


def _bfs_step(world, start, goal):
    """First cell on the shortest path start->goal, or None."""
    if start == goal:
        return goal
    frontier = deque([start])
    came = {start: None}
    while frontier:
        cell = frontier.popleft()
        if cell == goal:
            break
        cx, cy = cell
        for nxt in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if nxt not in came and not world.is_wall(*nxt):
                came[nxt] = cell
                frontier.append(nxt)
    if goal not in came:
        return None
    cell = goal
    while came[cell] != start:
        cell = came[cell]
        if cell is None:
            return None
    return cell


def demo_bot(world):
    inp = InputState()
    my_cell = (int(round(world.px / CELL)), int(round(world.pz / CELL)))

    # pick an objective: nearest enemy, else the exit
    target_pos = None
    want_fire = False
    if world.enemies:
        enemy = min(world.enemies,
                    key=lambda e: (e.x - world.px) ** 2 + (e.z - world.pz) ** 2)
        target_pos = (enemy.x, enemy.z)
        want_fire = True
        # if we can already see it, aim straight at it instead of pathing
        if world.line_of_sight(world.px, world.pz, enemy.x, enemy.z):
            steer_x, steer_z = enemy.x, enemy.z
        else:
            goal = (int(round(enemy.x / CELL)), int(round(enemy.z / CELL)))
            step = _bfs_step(world, my_cell, goal)
            if step is None:
                steer_x, steer_z = enemy.x, enemy.z
            else:
                steer_x, steer_z = step[0] * CELL, step[1] * CELL
    elif world.exit_cell is not None:
        goal = world.exit_cell
        step = _bfs_step(world, my_cell, goal) or goal
        steer_x, steer_z = step[0] * CELL, step[1] * CELL
        target_pos = (goal[0] * CELL, goal[1] * CELL)
    else:
        return inp

    bearing = math.atan2(steer_z - world.pz, steer_x - world.px)
    diff = (bearing - world.angle + math.pi) % math.tau - math.pi
    if diff > 0.1:
        inp.turn = 1.0
    elif diff < -0.1:
        inp.turn = -1.0
    dist_to_obj = math.hypot(target_pos[0] - world.px,
                             target_pos[1] - world.pz)
    melee = want_fire and world.ammo <= 0
    stop_at = 1.0 if melee else 1.3
    if abs(diff) < 0.8 and not (want_fire and dist_to_obj < stop_at):
        inp.up = True

    if want_fire:
        ex, ez = target_pos
        aim = math.atan2(ez - world.pz, ex - world.px)
        aim_diff = (aim - world.angle + math.pi) % math.tau - math.pi
        in_reach = dist_to_obj < 1.7 if melee else True
        if abs(aim_diff) < 0.15 and in_reach and \
                world.line_of_sight(world.px, world.pz, ex, ez):
            inp.fire = not world.prev_fire
    return inp
