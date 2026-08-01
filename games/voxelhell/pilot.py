"""Cabinet Man's Voxel Hell pilot: "never wastes a shot."

Personality: perfect shot economy is the whole trick. Cabinet Man only pulls
the trigger when the current shot's flight path is *already* guaranteed to
connect — it leads the target using the target's own (fully predictable)
motion, and it never double-books a target that's already going to die from
a bullet already in flight. Dodging is superhuman (it samples a handful of
candidate lanes and steers to whichever one stays clear of every live bullet
for the whole reaction window) but tuned to read as smooth rather than
twitchy: the ship's held movement direction only flips once the case for
flipping is unambiguous, never on a single noisy frame. The one bit of
showmanship: when the field is *provably* clear of danger (zero enemy
bullets in flight — not just "probably fine"), it occasionally drifts out to
a screen edge and idles there for a beat before getting back to work.

Why prediction can be near-exact: enemy/boss motion in this sim is a
closed-form function of elapsed time (formation bob, the boss's slow weave,
the entry fly-in's cubic ease) rather than something integrated step by
step, so the pilot can ask "where will this target be in tau seconds" by
plugging a future time into the same formulas `Enemy.update`/`Boss.update`
use themselves — no forward-stepping simulation, no accumulated error to
buffer against. The one deliberate approximation: enemy-bullet curvature
(`Spiral`'s slow homing turn, a few degrees *per second*) is ignored during
dodge prediction and treated as a straight line — over the ~1s dodge horizon
that curve amounts to a sub-pixel deviation, dwarfed by the danger-scoring
safety margin anyway.

Fire discipline: how long a shot takes to reach a given altitude depends
only on the ship's (fixed) firing height, not on which column it's fired
from, so the pilot solves "when does this shot's lane reach the target's
row" once per (lane, target) pair — a short fixed-point iteration against
the target's own slow y-bob — and then checks whether the ship's *current*
x already lines up with where the target will be at that instant. The
margin is a fraction of the combined bullet+target radius: comfortably
inside the real hit tolerance, not a hair's-width guess. In-flight shots are
tracked as "claims" against a target's remaining hp (keyed by an expected
resolve time) so a second shot is never spent finishing a kill the first one
already guarantees. When the SPREAD powerup is active, one trigger pull
fires three diverging lanes at once; the pilot re-runs the same intercept
solve independently for all three and only fires when *every* lane already
has its own guaranteed target — in practice that means holding fire on the
frames where only the center lane lines up, which is the correct call (a
lane with nothing downrange is a wasted shot, spread or not). The pilot also
gives spread pickups a mild wide berth during dodging (not a hard rule —
survival still comes first) specifically to keep that harder 3-lane case
rare.

Bosses (v1): the same fire-discipline logic applies unchanged — the boss's
weave is just another closed-form target, and its huge radius makes leading
it easy — but its denser attack patterns lean on the dodge system's safety
margin rather than any boss-specific pattern-reading. This pilot aims to
survive a boss fight and chip it down cleanly, not to bait or optimize
around specific phase attacks.
"""
import math

from game.entities import FIELD_WIDTH, FIELD_HEIGHT, InputState

_PLAYER_Y = FIELD_HEIGHT - 30           # bottom of the allowed range: max reaction time
_BULLET_SPEED = 700.0
_PLAYER_BULLET_R = 6.0
_FIRE_ANGLE = -math.pi / 2
_SPREAD_OFFSET = 0.21                   # matches world._handle_player_fire

_HORIZON = 1.0                          # seconds of bullet danger sampled ahead
_LANE_XS = tuple(40.0 + (FIELD_WIDTH - 80.0) * i / 8 for i in range(9))  # 9 candidate lanes
_DANGER_MARGIN = 6.0                    # extra px of buffer beyond hitbox+bullet radius
_FIRE_MARGIN_FRAC = 0.55                # fraction of combined radius allowed as aim error
_DEADZONE = 6.0                         # px: ignore desired-x jitter smaller than this
_COMMIT_TIME = 0.12                     # s: minimum time between movement-direction flips
_QUIRK_COOLDOWN = (2.5, 5.0)            # s range between edge-drift quirks
_QUIRK_PAUSE = (0.6, 1.4)               # s range spent idling at the edge


# --------------------------------------------------------------- prediction
def _formation_pos(e, world_time, time_alive):
    offset = math.sin(world_time * 0.45) * 26
    x = e.slot_x + offset + math.sin(time_alive * 1.7 + e.bob_phase) * 6
    y = e.slot_y + math.sin(time_alive * 2.3 + e.bob_phase * 2) * 4
    return x, y


def _enemy_pos_at(e, world_time, tau):
    """Predicted (x, y) of enemy `e`, `tau` seconds from now. Only ever
    called for enemies already settled into formation (see `_gather_targets`)
    — formation motion is small, slow, and purely periodic, so this closed
    form stays accurate for as far ahead as the fire logic ever looks."""
    return _formation_pos(e, world_time + tau, e.time_alive + tau)


def _boss_pos_at(boss, tau):
    t = boss.time_alive + tau
    return (FIELD_WIDTH / 2 + math.sin(t * 0.55) * 170,
            150 + math.sin(t * 1.1) * 24)


class _Target:
    __slots__ = ("id", "radius", "hp", "pos_fn")

    def __init__(self, id_, radius, hp, pos_fn):
        self.id = id_
        self.radius = radius
        self.hp = hp
        self.pos_fn = pos_fn


def _gather_targets(world):
    """Live, shootable targets: enemies already settled into formation, and
    the boss. Enemies mid entry-fly-in are deliberately excluded — v1
    limitation, see module docstring — their cubic ease-out can briefly
    move faster than the ship's own bullets close in, which makes "when
    does a shot reach this row" have more than one crossing (or none) right
    at the start of the ease; holding fire until an enemy is settled sidesteps
    that entirely rather than risk a shot that looked safe but wasn't."""
    targets = []
    for e in world.enemies:
        if e.alive and e.entry_t >= 1.0:
            targets.append(_Target(
                id(e), e.radius, e.hp,
                lambda tau, e=e, wt=world.time: _enemy_pos_at(e, wt, tau)))
    boss = world.boss
    if boss is not None and boss.alive:
        targets.append(_Target(id(boss), boss.radius, boss.hp,
                                lambda tau, b=boss: _boss_pos_at(b, tau)))
    return targets


# -------------------------------------------------------------- dodge math
def _closest_dist(dx0, dy0, rvx, rvy, tau_lo, tau_hi):
    """Minimum distance between two points starting `(dx0, dy0)` apart and
    closing at constant relative velocity `(rvx, rvy)`, over tau in
    [tau_lo, tau_hi]. Exact (vertex of the quadratic distance^2), not a
    sampled approximation. Returns (min_dist, tau_at_min) or (None, None) if
    the interval is empty."""
    if tau_hi <= tau_lo:
        return None, None
    a = rvx * rvx + rvy * rvy
    if a > 1e-9:
        t_star = -(dx0 * rvx + dy0 * rvy) / a
        t_star = min(max(t_star, tau_lo), tau_hi)
    else:
        t_star = tau_lo
    dx = dx0 + rvx * t_star
    dy = dy0 + rvy * t_star
    return math.hypot(dx, dy), t_star


def _hazard_min_gap(p, hx, hy, hvx, hvy, x_c, direction, speed, t_arrive):
    """Closest approach of a straight-line hazard (bullet or falling
    powerup) to the ship's assumed two-phase path over the horizon: phase 1
    slides from p.x toward x_c at full speed (ending at t_arrive), phase 2
    holds at x_c for the remainder. Curvature is ignored (see module
    docstring) — negligible over this horizon for this sim's bullets."""
    best_gap, best_tau = None, None
    dx0, dy0 = hx - p.x, hy - p.y
    if t_arrive > 0.0:
        rvx1, rvy1 = hvx - direction * speed, hvy
        gap, tau = _closest_dist(dx0, dy0, rvx1, rvy1, 0.0, t_arrive)
        if gap is not None:
            best_gap, best_tau = gap, tau
    if t_arrive < _HORIZON:
        hx_at, hy_at = hx + hvx * t_arrive, hy + hvy * t_arrive
        gap, tau = _closest_dist(hx_at - x_c, hy_at - p.y, hvx, hvy,
                                  0.0, _HORIZON - t_arrive)
        if gap is not None and (best_gap is None or gap < best_gap):
            best_gap, best_tau = gap, t_arrive + tau
    return best_gap, best_tau


# ------------------------------------------------------------- fire lanes
def _fire_lanes(spread_active):
    deltas = (-_SPREAD_OFFSET, 0.0, _SPREAD_OFFSET) if spread_active else (0.0,)
    return [(math.cos(_FIRE_ANGLE + d) * _BULLET_SPEED,
              math.sin(_FIRE_ANGLE + d) * _BULLET_SPEED) for d in deltas]


def _lane_tau(target, vy, launch_y, iters=4):
    """Time for a lane with vertical speed `vy` (negative: upward) launched
    from `launch_y` to reach `target`'s row, iterating against the target's
    own (slow) y motion — formation bob and the boss's weave both change y
    far slower than any bullet closes in, so this converges in a couple of
    iterations. None if the target is behind us or the row is never reached
    within our lookahead. The `ty < -35` guard is a defensive backstop (not
    load-bearing for formation/boss targets, which never go there) against
    ever aiming at a y the bullet's own out-of-bounds check (-40) would make
    unreachable."""
    _, ty = target.pos_fn(0.0)
    tau = (launch_y - ty) / -vy
    if tau < 0:
        return None
    for _ in range(iters):
        _, ty = target.pos_fn(tau)
        tau = (launch_y - ty) / -vy
        if tau < 0:
            return None
    if ty < -35.0:
        return None
    return tau


def _lane_requirement(target, vx, vy, launch_y):
    """(tau, required_player_x, margin) for this lane to hit `target` if
    fired right now, or None if it can't connect at all."""
    tau = _lane_tau(target, vy, launch_y)
    if tau is None or tau <= 0.01 or tau > 1.4:
        return None
    tx, _ = target.pos_fn(tau)
    required_x = tx - vx * tau
    if not (20.0 <= required_x <= FIELD_WIDTH - 20.0):
        return None
    margin = (target.radius + _PLAYER_BULLET_R) * _FIRE_MARGIN_FRAC
    return tau, required_x, margin


def _lane_candidates(targets, vx, vy, launch_y, player_x):
    """Every target this lane (fired from the *current* `player_x`, not a
    solved-for one) would pass within margin of, as (tau, target) pairs
    sorted so the chronologically first one — whichever the bullet actually
    reaches first — comes first. This sim's bullets stop at the first thing
    they touch, and rows in this game often share a column (two enemies at
    the same x, different y), so a shot "aimed at" a far target can really
    connect with a nearer, unintended one instead. Solving per-target
    requirements independently (as `_lane_requirement` does, for steering)
    misses that; verifying an actual firing decision must not."""
    hits = []
    for t in targets:
        tau = _lane_tau(t, vy, launch_y)
        if tau is None or tau <= 0.01 or tau > 1.4:
            continue
        tx, _ = t.pos_fn(tau)
        bx = player_x + vx * tau
        margin = (t.radius + _PLAYER_BULLET_R) * _FIRE_MARGIN_FRAC
        if abs(bx - tx) <= margin:
            hits.append((tau, t))
    hits.sort(key=lambda pair: pair[0])
    return hits


# -------------------------------------------------------------- the pilot
class VoxelHellPilot:
    label = "Cabinet Man"

    def __init__(self, run):
        self.rng = run.world.rng
        self.pending = []           # in-flight claims: [{"id", "resolve"}]
        self._move_dir = 0
        self._commit_timer = 0.0
        self._quirk_state = "idle"  # idle -> moving -> pausing
        self._quirk_ready_at = self.rng.uniform(*_QUIRK_COOLDOWN)
        self._quirk_edge_x = None
        self._quirk_pause_until = 0.0

    # ------------------------------------------------------------ claims
    def _prune_claims(self, world_time):
        self.pending = [c for c in self.pending if c["resolve"] > world_time]

    def _claimed(self, target_id):
        return sum(1 for c in self.pending if c["id"] == target_id)

    # -------------------------------------------------------------- step
    def step(self, run, dt):
        world = run.world
        p = world.player
        if not p.alive or world.run_over:
            return InputState()

        self._prune_claims(world.time)
        targets = _gather_targets(world)

        move_dir = self._decide_move(world, p, targets, dt)
        down = p.y < _PLAYER_Y - 1.0

        # The shot's actual launch x is p.x *after* this frame's movement
        # (Player.update runs, then _handle_player_fire, inside world.update)
        # — mirror that same movement math here so the fire check validates
        # the position the bullet will really spawn from, not the position
        # from before this frame's step. Skipping this let a moving ship
        # occasionally drift just outside a shot's margin between deciding
        # to fire and the bullet actually spawning.
        dx = 1.0 if move_dir > 0 else (-1.0 if move_dir < 0 else 0.0)
        dy = 1.0 if down else 0.0
        if dx and dy:
            dx *= 1 / math.sqrt(2)
        predicted_x = max(20.0, min(FIELD_WIDTH - 20.0, p.x + dx * p.speed * dt))

        fire, assigned = self._decide_fire(world, p, targets, predicted_x)

        for target_id, tau in assigned:
            self.pending.append({"id": target_id, "resolve": world.time + tau + 0.05})

        return InputState(
            left=move_dir < 0, right=move_dir > 0,
            down=down, up=False,
            fire=fire,
        )

    # -------------------------------------------------------------- fire
    def _decide_fire(self, world, p, targets, player_x):
        if p.fire_cooldown > 0 or not targets:
            return False, []
        lanes = _fire_lanes(p.spread_timer > 0)
        launch_y = p.y - 24.0
        assigned = []
        used = {}
        for vx, vy in lanes:
            candidates = _lane_candidates(targets, vx, vy, launch_y, player_x)
            picked = None
            for tau, t in candidates:
                # The bullet physically reaches these in tau order, so the
                # first one still owed a hit (not already fully claimed by
                # shots already in flight) is the one this shot must be
                # booked against — a nearer, fully-claimed target is assumed
                # dead by the time this bullet would reach it (trusting our
                # own claim timing) and the shot passes through to whatever
                # is next in line.
                remaining = t.hp - self._claimed(t.id) - used.get(t.id, 0)
                if remaining > 0:
                    picked = (t.id, tau)
                    break
            if picked is None:
                return False, []    # any lane left unfilled: hold fire, entirely
            used[picked[0]] = used.get(picked[0], 0) + 1
            assigned.append(picked)
        return True, assigned

    # ------------------------------------------------------------- aiming
    def _best_alignment_x(self, p, targets):
        """The single required-x closest to our current position, among
        targets we could still usefully shoot (center lane only — spread's
        3-lane case is too rare to steer toward, it's just opportunistic)."""
        launch_y = p.y - 24.0
        best = None
        for t in targets:
            if t.hp - self._claimed(t.id) <= 0:
                continue
            req = _lane_requirement(t, 0.0, -_BULLET_SPEED, launch_y)
            if req is None:
                continue
            _, required_x, _ = req
            if best is None or abs(required_x - p.x) < abs(best - p.x):
                best = required_x
        return best

    # ------------------------------------------------------------ dodging
    def _danger(self, world, p, x_c):
        """How dangerous candidate lane `x_c` is: the ship is modeled as
        moving straight toward x_c at full speed and parking there (exactly
        what `_commit` actually drives), and each hazard's closest approach
        to that whole two-phase path over the horizon is found in closed
        form (exact quadratic minimum, not a sampled guess) — so a hazard
        that would clip the ship *between* candidate frames isn't missed."""
        speed = p.speed
        dist_needed = abs(x_c - p.x)
        direction = 0.0 if dist_needed == 0 else (1.0 if x_c > p.x else -1.0)
        t_arrive = min(dist_needed / speed, _HORIZON) if speed > 0 else 0.0
        score = 0.0
        for b in world.enemy_bullets:
            thresh = p.hitbox_r + b.r + _DANGER_MARGIN
            gap, tau = _hazard_min_gap(p, b.x, b.y, b.vx, b.vy, x_c, direction,
                                        speed, t_arrive)
            if gap is not None and gap < thresh:
                urgency = 1.0 - min(max(tau, 0.0), _HORIZON) / _HORIZON
                score += (thresh - gap) / thresh + urgency
        for pu in world.powerups:
            if pu.kind != "spread":
                continue
            thresh = 20.0 + pu.radius
            gap, tau = _hazard_min_gap(p, pu.x, pu.y, 0.0, pu.vy, x_c, direction,
                                        speed, t_arrive)
            if gap is not None and gap < thresh:
                score += 0.3 * (1.0 - min(max(tau, 0.0), _HORIZON) / _HORIZON)
        return score

    def _update_quirk(self, world, p):
        """Only ever engages when the field is *provably* safe (zero enemy
        bullets in flight, not merely low-risk); aborts back to normal play
        the instant that stops being true."""
        safe_now = not world.enemy_bullets
        if self._quirk_state == "idle":
            if safe_now and world.time >= self._quirk_ready_at:
                self._quirk_edge_x = (FIELD_WIDTH - 40.0 if self.rng.random() < 0.5
                                       else 40.0)
                self._quirk_state = "moving"
                return self._quirk_edge_x
            return None
        if not safe_now:
            self._quirk_state = "idle"
            self._quirk_ready_at = world.time + self.rng.uniform(*_QUIRK_COOLDOWN)
            return None
        if self._quirk_state == "moving":
            if abs(p.x - self._quirk_edge_x) <= _DEADZONE:
                self._quirk_state = "pausing"
                self._quirk_pause_until = world.time + self.rng.uniform(*_QUIRK_PAUSE)
            return self._quirk_edge_x
        if world.time >= self._quirk_pause_until:
            self._quirk_state = "idle"
            self._quirk_ready_at = world.time + self.rng.uniform(*_QUIRK_COOLDOWN)
            return None
        return self._quirk_edge_x

    def _decide_move(self, world, p, targets, dt):
        candidates = set(_LANE_XS)
        candidates.add(p.x)
        dangers = {x: self._danger(world, p, x) for x in candidates}
        min_danger = min(dangers.values())
        safe = [x for x, d in dangers.items() if d <= min_danger + 1e-9]

        quirk_x = self._update_quirk(world, p)
        if quirk_x is not None:
            desired = quirk_x
        else:
            align = self._best_alignment_x(p, targets) if p.spread_timer <= 0 else None
            if align is None:
                desired = min(safe, key=lambda x: abs(x - p.x))
            else:
                desired = min(safe, key=lambda x: abs(x - align))
        return self._commit(p, desired, dt)

    def _commit(self, p, desired_x, dt):
        """Direction hysteresis: holds a movement direction for a minimum
        stretch of time so the flight path reads as smooth glides, not a
        jittery flicker every frame."""
        self._commit_timer = max(0.0, self._commit_timer - dt)
        delta = desired_x - p.x
        new_dir = 0 if abs(delta) <= _DEADZONE else (1 if delta > 0 else -1)
        reversal = self._move_dir != 0 and new_dir != 0 and new_dir != self._move_dir
        if reversal and self._commit_timer > 0.0:
            new_dir = self._move_dir
        if new_dir != self._move_dir:
            self._commit_timer = _COMMIT_TIME
        self._move_dir = new_dir
        return new_dir


def create_pilot(run):
    return VoxelHellPilot(run)
