"""Cabinet Man's reference pilot for Voxel Hell: "never wastes a shot."

The house doesn't spray. Every bullet it fires is already solved, before the
trigger is pulled, to land on something -- the pilot only ever squeezes off
a shot once its own muzzle is standing exactly where an enemy or the boss
provably will be when a straight-up shot fired *right now* gets there.

How the shot economy works, each frame:

  1. `enemy_pos_at` / `boss_pos_at` are the exact closed-form position
     functions transcribed straight from `Enemy.update`/`Boss.update` --
     once an enemy has finished its fly-in (`entry_t >= 1.0`), its motion
     and the boss's motion are both pure deterministic sums of sines, not a
     physics simulation, so a future position is a formula, not something
     that has to be stepped toward frame by frame.
  2. `solve_vertical_intercept` asks: "if I fired a vx=0 bullet straight up
     right now, when would it cross this target's height, and where would
     the target be at that instant?" The player's bullet arrives at a fixed
     height only after time `t = (muzzle_y - target_y) / bullet_speed`, but
     `target_y` itself is oscillating a few pixels with time -- so this
     solves for `t` and `target_y(t)` together by fixed-point iteration
     exactly like Breaker's `solve_intercept` folds in wall bounces: the
     oscillation amplitude here (4px for enemies, 24px for the boss) is
     tiny next to how far a 700px/s bullet travels per correction, so 2-3
     passes converge to sub-pixel accuracy (verified against a brute-force
     stepper in `tools/test_pilot.py`, same as Breaker's wall-bounce check).
  3. The pilot only requests fire once its own x is within a few pixels of
     that solved intercept x -- not "close enough for the target's hit
     radius to cover the rest", the actual muzzle alignment, so the shot is
     never counting on generosity from `circles_hit`'s radius sum to save a
     sloppy aim.
  4. Multi-hit targets (octo/elite) can legitimately take more than one
     landed shot, and Voxel Hell keeps several bullets in flight at once
     (the fire cooldown is much shorter than a bullet's ~0.3-0.9s flight
     time) -- so before ever pulling the trigger again at the *same*
     target, the pilot checks a `_claims` ledger: how many already-fired,
     not-yet-landed bullets are already committed to it (tracked by
     `id(target)` with an expiry a hair past each one's own predicted
     arrival), and only fires again if `hp - active_claims > 0`. This is
     the whole trick that keeps `shots_fired == hits` true even under
     rapid-fire: the sim processes every bullet still in `player_bullets`
     every frame regardless of when it was fired, and once a target's `hp`
     reaches 0 mid-frame its `alive` flag flips immediately -- a bullet
     that arrives to find its target already dead just sails through
     without ever registering a hit. Never over-committing more claims
     than the target has hp left is what prevents that.

Powerup safety (spread): a fire input while `player.spread_timer > 0`
detonates into *three* simultaneous bullets at diverging angles, entirely
outside the pilot's control -- and none of the trajectory math above
applies to the two angled ones. Rather than re-derive three independent
intercept solves every frame just to justify firing during a 10-second
buff the ship doesn't need, the pilot treats `spread_timer > 0` as a
standing "hold fire" state: it keeps dodging and tracking normally, just
never sets `fire=True` until the buff itself expires, then resumes
single-shot discipline exactly as before. Holding fire costs nothing
against the `shots_fired == hits` invariant (no bullet, no risk), so this
holds unconditionally -- even if a spread orb is ever picked up (nothing
stops the world's own automatic pickup-on-overlap). As a courtesy (not a
safety requirement) the same hazard-avoidance machinery used for dodging
also treats a falling "spread" orb as a hazard to steer clear of, so the
ship mostly declines the buff in the first place and the 10s of forced
downtime is rare rather than routine.

Dodging: the ship never moves vertically (same simplification Voxel Hell's
existing attract-mode `demo_bot` makes), so "danger" is entirely about
which x a hazard will occupy at the moment it reaches the ship's current
y-row. Enemy bullets travel in straight lines unless `curve != 0`, in which
case they trace an exact circular arc (constant speed, constant turn
rate); either way, `_bullet_reach_tau` solves *exactly* when a bullet
crosses that row (straight bullets: direct algebra; curved ones: bracket the
earliest sign change of the closed-form `y(tau)` in a handful of coarse
steps, then bisect) rather than sampling its position at a handful of
future instants -- sampling a fast bullet's position can alias straight
past a narrow hit radius between two samples, but solving for the
crossing itself can't miss it. Every frame this gives a short list of
"this x, at this radius, is claimed" hazards; a full-field grid scan picks
the x with the largest worst-case clearance. Whether to chase the
fire-alignment spot or retreat to open field is a hysteresis band (enter
fire-alignment mode only once genuinely clear by a margin, leave it the
instant that margin erodes, and danger at the ship's *actual current*
position always overrides immediately, no hold, no exception) so the ship
doesn't flap between the two several times a second; once it's picked a
dodge spot on the open-field side it holds that choice for a minimum
duration too, for the same reason -- unless the spot it's already
standing on or already heading to stops being safe, which always breaks
the hold immediately.

Personality quirk: when there's truly nothing to shoot at and no hazard
anywhere in the sampled window (checked, not assumed), the ship
occasionally drifts to a screen edge and idles there for a beat before
resuming, seeded from the run's own rng -- deterministic, never a wall-
clock roll, and it can never fire while parked there (nothing to aim at is
exactly why it's parked).

Bosses (v1 simplification, documented honestly): the boss gets the exact
same intercept-and-claim treatment as any other target -- it just never
runs out of hp fast enough for the claim ledger to matter in practice. Its
own bullet *patterns* are not specifically countered (no boss-pattern
solver); the pilot leans on the same generic hazard-sampling dodge that
protects it against regular waves. That's an acceptable v1 per the ticket:
chip away at the boss and keep the shot economy, don't attempt a bespoke
per-phase dodge.

Known v1 shadowing limitation (documented honestly): `_visible` rules out a
target "shadowed" by a nearer *in-formation* enemy sharing its column, so
the pilot only ever fires at what a straight-up shot will truly hit first.
But an enemy still completing its fly-in (`entry_t < 1.0`) isn't an
intercept candidate yet, so it isn't a known column occupant -- and in a
dense wave one can drift into a fired shot's column while that shot is still
travelling and eat it, leaving the target the pilot *claimed* un-hit. The
shot still lands on the fly-in enemy (so it's not lost damage, and the ship
is never endangered), but it silently falsifies one claim, which in rare
cases leaves a later shot chasing something already dead from an unrelated
hit. Empirically this is ~1 shot per several full games and only in late,
crowded waves; the shot-economy invariant holds exactly through the opening
waves (see tools/test_pilot.py). Fully closing it would mean predicting
fly-in enemies' future positions too -- deferred.
"""
import math

from game.entities import InputState, FIELD_WIDTH

BULLET_SPEED = 700.0     # Bullet speed for a straight (non-spread) shot.
BULLET_RADIUS = 6.0      # Player bullet r, from World._handle_player_fire.
MUZZLE_DY = 24.0         # Bullets spawn at (player.x, player.y - 24).
PLAYER_HALF_X = 20.0     # Player.update clamps x to [20, FIELD_WIDTH - 20].

# Extra margin (px) added on top of the raw bullet+target radius sum when
# deciding one live target "shadows" another sharing a similar column --
# see `_visible`'s docstring on why this matters at all.
_SHADOW_PAD = 3.0

# How tight the muzzle has to sit on the solved intercept x before the
# pilot actually pulls the trigger. Comfortably inside the smallest real
# hit radius (squid/elite enemy radius 20 + bullet r 6 = 26px) so aim error
# is never what's saving the shot.
_FIRE_ALIGN_EPS = 3.0

# Below this, treat "haven't quite arrived" as arrived -- stops the
# left/right bits from flipping every frame once within a pixel or two of
# the goal (same idea as Breaker's `_EPS`).
_MOVE_EPS = 2.0

# A claim's tracked expiry gets this much slack added past its own solved
# arrival time before the ledger considers it resolved. Erring late here
# is always safe (just briefly conservative about capacity); erring early
# is what would let a second bullet get over-committed to hp that's
# already spoken for.
_CLAIM_BUFFER = 0.12

# Only switch the "current focus" target away from what it already was
# aiming at if a candidate is at least this much closer to aim at --
# otherwise keep tracking the same target so the muzzle doesn't hunt
# between two similarly-placed enemies.
_REFOCUS_MARGIN = 50.0

# Hysteresis band (px of clearance) for entering/leaving fire-alignment
# mode -- enter only once clearly safe, leave as soon as it's not, so the
# ship doesn't flap between chasing a shot and bailing to open field.
_SAFE_ENTER = 10.0
_SAFE_EXIT = 0.0

# How far ahead (seconds) the hazard scan solves for enemy bullets /
# falling spread orbs crossing the ship's y-row. Deliberately short: a
# hazard that won't cross for several seconds isn't a constraint on *this*
# frame's decision (the ship will simply reassess long before it becomes
# one), and treating every bullet still airborne anywhere on the field as
# an immediate claim on real estate -- regardless of when it actually
# arrives -- starves the field of safe spots that are only "occupied" on
# paper. Long enough to give a full-speed dodge real travel budget
# (`_DODGE_LOOKAHEAD * PLAYER_SPEED` px) before a threat solved exactly
# (no sampling, so no window to alias through) actually arrives.
_DODGE_LOOKAHEAD = 1.1
PLAYER_SPEED = 300.0     # Player.speed -- the pilot never sets focus (which
                          # would halve it), so full speed always applies.

# Extra pixels of margin added on top of the raw radius sum when deciding
# a spot is "close enough to a hazard to avoid" -- a little slack beyond
# the bare minimum so the ship isn't grazing things by design.
_HAZARD_PAD = 8.0

# Once the ship commits to a specific open-field dodge spot, hold it this
# long before reconsidering (unless that very spot turns dangerous sooner)
# -- "hold a chosen direction for a minimum duration" per the brief.
_DODGE_HOLD = 0.2

# Spacing (px) of the open-field candidate grid scanned for the safest x.
_GRID_STEP = 20.0

# Personality quirk cadence: per-second chance of triggering an idle edge
# drift (only ever considered when there's nothing to shoot at and the
# hazard scan is provably clean), and how long it lingers there.
_IDLE_CHANCE_PER_SEC = 0.12
_IDLE_MIN_DURATION = 0.6
_IDLE_MAX_DURATION = 1.5
_IDLE_MARGIN = 40.0  # how close to the wall counts as "at the edge"


def enemy_pos_at(world_time, e, tau):
    """Exact position an in-formation enemy will occupy `tau` seconds from
    now -- transcribed from `Enemy.update`'s in-formation branch (not a
    simulation step)."""
    formation_offset_x = math.sin((world_time + tau) * 0.45) * 26
    t = e.time_alive + tau
    x = e.slot_x + formation_offset_x + math.sin(t * 1.7 + e.bob_phase) * 6
    y = e.slot_y + math.sin(t * 2.3 + e.bob_phase * 2) * 4
    return x, y


def boss_pos_at(boss, tau):
    """Exact position the boss will occupy `tau` seconds from now --
    transcribed from `Boss.update`."""
    t = boss.time_alive + tau
    x = FIELD_WIDTH / 2 + math.sin(t * 0.55) * 170
    y = 150 + math.sin(t * 1.1) * 24
    return x, y


def solve_vertical_intercept(pos_at_fn, muzzle_y, bullet_speed=BULLET_SPEED,
                              iters=4):
    """Given a target's `pos_at(tau) -> (x, y)`, solve for the arrival time
    `t` of a bullet fired *right now* straight up from some x (unknown yet
    -- only the muzzle height matters) at `bullet_speed`, and the x the
    target will be at when it gets there.

    Fixed-point on `t`: start from the target's *current* y, then
    repeatedly re-solve `t = (muzzle_y - target_y(t)) / bullet_speed` using
    the target's y at the previous estimate. The target's own y-oscillation
    amplitude here (a handful of pixels) is tiny next to how far a
    700px/s bullet travels per correction, so this converges to sub-pixel
    accuracy in a couple of passes (see `tools/test_pilot.py` for a
    brute-force cross-check).

    Returns `(t, x)`, or `None` if the target is at/behind the muzzle
    already (t would come out <= 0 -- nothing to solve, not reachable this
    way)."""
    _, y0 = pos_at_fn(0.0)
    t = (muzzle_y - y0) / bullet_speed
    if t <= 0:
        return None
    for _ in range(iters):
        _, y = pos_at_fn(t)
        t = (muzzle_y - y) / bullet_speed
        if t <= 0:
            return None
    x, _ = pos_at_fn(t)
    return t, x


def _bullet_pos_at(b, tau):
    """Exact future position of an enemy bullet -- a straight line, or (if
    `curve != 0`) the exact circular arc traced by a constant-speed,
    constant-turn-rate velocity vector (`Bullet.update` rotates the
    velocity direction at `curve` rad/s every frame; integrating that
    continuously gives a closed-form arc, not a per-frame Euler step)."""
    if b.curve == 0:
        return b.x + b.vx * tau, b.y + b.vy * tau
    speed = math.hypot(b.vx, b.vy)
    heading0 = math.atan2(b.vy, b.vx)
    heading = heading0 + b.curve * tau
    x = b.x + (speed / b.curve) * (math.sin(heading) - math.sin(heading0))
    y = b.y - (speed / b.curve) * (math.cos(heading) - math.cos(heading0))
    return x, y


def _powerup_pos_at(pu, tau):
    """Exact future position of a falling powerup -- `PowerUp.update` adds
    a constant fall speed plus a `sin(time_alive * 2.2) * 20` per-second
    horizontal drift; integrating that drift term in closed form gives the
    same `(cos(a) - cos(b)) / rate` shape as the curved-bullet arc above."""
    x = pu.x + (20 / 2.2) * (math.cos(2.2 * pu.time_alive)
                              - math.cos(2.2 * (pu.time_alive + tau)))
    y = pu.y + pu.vy * tau
    return x, y


def _in_formation(e):
    return e.time_alive >= e.entry_delay and e.entry_t >= 1.0


# A mover whose exact crossing of the ship's y-row solves to a hair
# *before* now (it crossed a fraction of a frame ago) is still very much a
# live threat -- the row-crossing instant is only the center of its hit
# radius's vertical span, not the whole span, so something moving at a
# realistic pattern speed can still be well within that radius a moment
# after the geometric crossing. Widening the accepted window to include a
# short window just behind "now" catches that without having to special-
# case "already basically touching" separately.
_PAST_SLOP = 0.2


def _linear_reach(y0, vy, target_y, cap):
    """When (if ever) a constant-vy mover crosses `target_y` within
    `[-_PAST_SLOP, cap]` seconds -- trivial algebra, exact."""
    if vy == 0:
        return None
    tau = (target_y - y0) / vy
    if -_PAST_SLOP <= tau <= cap:
        return tau
    return None


def _bullet_reach_tau(b, target_y, cap):
    """When a bullet crosses `target_y`, exactly. Straight bullets solve
    directly; curved ones trace a sinusoidal `y(tau)`, so this brackets the
    *earliest* sign change in a handful of coarse steps across the window
    and bisects inside it -- exact to well under a pixel, and, unlike
    sampling the bullet's *position* at a handful of instants (which can
    alias straight past a fast bullet crossing a narrow hit radius between
    two samples), this only ever needs the crossing itself, so there's no
    window to slip through."""
    if b.curve == 0:
        return _linear_reach(b.y, b.vy, target_y, cap)
    speed = math.hypot(b.vx, b.vy)
    heading0 = math.atan2(b.vy, b.vx)
    w = b.curve

    def y_at(tau):
        return b.y - (speed / w) * (math.cos(heading0 + w * tau) - math.cos(heading0))

    steps = 16
    window = cap + _PAST_SLOP
    prev_tau, prev_f = -_PAST_SLOP, y_at(-_PAST_SLOP) - target_y
    if prev_f == 0.0:
        return prev_tau
    for i in range(1, steps + 1):
        tau = -_PAST_SLOP + window * i / steps
        f = y_at(tau) - target_y
        if f == 0.0:
            return tau
        if prev_f * f < 0.0:
            lo, hi, flo = prev_tau, tau, prev_f
            for _ in range(24):
                mid = (lo + hi) / 2
                fm = y_at(mid) - target_y
                if flo * fm <= 0.0:
                    hi = mid
                else:
                    lo, flo = mid, fm
            return (lo + hi) / 2
        prev_tau, prev_f = tau, f
    return None


class VoxelHellPilot:
    """Cabinet Man at the stick: see module docstring."""

    label = "Cabinet Man"

    def __init__(self, run):
        self.rng = run.world.rng
        self._claims = {}          # id(target) -> [expiry world-times]
        self._focus_id = None
        self._mode = "dodge"       # "align" | "dodge"
        self._dodge_x = None
        self._dodge_hold = 0.0
        self._idle_timer = 0.0
        self._idle_x = None

    # --------------------------------------------------------------- step
    def step(self, run, dt):
        world = run.world
        p = world.player
        inp = InputState()
        if not p.alive:
            return inp

        self._prune_claims(world)
        hazards = self._collect_hazards(world)
        focus = self._pick_focus(world)

        self._update_mode(focus, hazards, p)

        want_fire = False
        if self._mode == "align" and focus is not None:
            target, t_arr, x_req = focus
            goal_x = x_req
            if abs(p.x - x_req) <= _FIRE_ALIGN_EPS:
                want_fire = True
        else:
            goal_x = self._pick_dodge_x(world, hazards, dt)
            idle_x = self._maybe_idle(world, focus, hazards, dt)
            if idle_x is not None:
                goal_x = idle_x

        dx = goal_x - p.x
        if abs(dx) > _MOVE_EPS:
            inp.left = dx < 0
            inp.right = dx > 0

        if want_fire:
            inp.fire = True
            target, t_arr, _ = focus
            self._claims.setdefault(id(target), []).append(
                world.time + t_arr + _CLAIM_BUFFER)

        return inp

    # ----------------------------------------------------------- targeting
    def _prune_claims(self, world):
        """Drop claims whose target has died (nothing left to reserve hp
        for -- also sidesteps any risk of a later object reusing the same
        `id()`) and claims whose predicted arrival has already passed."""
        alive_ids = {id(e) for e in world.enemies}
        if world.boss is not None and world.boss.alive:
            alive_ids.add(id(world.boss))
        for key in list(self._claims):
            if key not in alive_ids:
                del self._claims[key]
                continue
            kept = [t for t in self._claims[key] if t > world.time]
            if kept:
                self._claims[key] = kept
            else:
                del self._claims[key]

    def _capacity(self, target):
        """How many more bullets may still be committed to `target` right
        now without out-running its remaining hp."""
        return target.hp - len(self._claims.get(id(target), ()))

    def _pick_focus(self, world):
        """The best currently-reachable, spare-capacity target as
        `(target, t_arrival, x_required)`, or `None`. Sticky: keeps the
        previous focus unless it's no longer valid or a candidate is
        clearly closer (`_REFOCUS_MARGIN`), so the muzzle doesn't hunt
        between similarly-placed targets."""
        p = world.player
        muzzle_y = p.y - MUZZLE_DY
        solved = []  # every alive, in-formation target's own intercept solve

        boss = world.boss
        if boss is not None and boss.alive:
            sol = solve_vertical_intercept(lambda tau: boss_pos_at(boss, tau),
                                            muzzle_y)
            if sol is not None:
                t, x = sol
                solved.append((boss, t, x))

        for e in world.enemies:
            if not e.alive or not _in_formation(e):
                continue
            sol = solve_vertical_intercept(
                lambda tau, e=e: enemy_pos_at(world.time, e, tau), muzzle_y)
            if sol is None:
                continue
            t, x = sol
            solved.append((e, t, x))

        candidates = self._visible(solved, p.x)
        if not candidates:
            self._focus_id = None
            return None

        candidates.sort(key=lambda c: c[3])
        best = candidates[0]
        if self._focus_id is not None:
            for c in candidates:
                if id(c[0]) == self._focus_id and c[3] <= best[3] + _REFOCUS_MARGIN:
                    best = c
                    break

        self._focus_id = id(best[0])
        return best[0], best[1], best[2]

    def _visible(self, solved, player_x):
        """Filter `solved` (every live target's own straight-up intercept)
        down to targets a bullet fired at their `x` would actually reach --
        and, of those, only ones with spare hp capacity.

        Every enemy row in this game tends to reuse the same evenly-spaced
        slot-x grid regardless of kind (`waves.py`'s `_row` helper divides
        the field width the same way for a 6-wide squid row as a 6-wide
        crab row), and every enemy's x carries the *same* shared
        `formation_offset_x` term -- so a bullet aimed at a far row's
        enemy will, far more often than not, also line up with a nearer
        row's enemy at (almost) the same x. A straight-up bullet always
        hits whatever's nearest to the muzzle along its column first, so
        a farther target "shadowed" by a nearer live one at a similar x is
        never actually reachable right now no matter how precisely it's
        aimed at -- firing there just spends the shot on the shadowing
        target instead (still a hit, so it doesn't break the shot-economy
        invariant by itself, but it silently falsifies this pilot's own
        claim bookkeeping for the target it *thought* it was shooting,
        which is what let a later shot end up chasing something already
        dead from an unrelated stray hit and connect with nothing). Ruling
        out shadowed targets up front means every claim this pilot makes
        is against whatever will truly be hit."""
        by_t = sorted(solved, key=lambda c: c[1])
        kept = []
        for target, t, x in by_t:
            blocked = False
            for shadow, _, shadow_x in kept:
                threshold = shadow.radius + BULLET_RADIUS + _SHADOW_PAD
                if abs(x - shadow_x) < threshold:
                    blocked = True
                    break
            if not blocked:
                kept.append((target, t, x))
        return [(target, t, x, abs(x - player_x)) for target, t, x in kept
                if self._capacity(target) > 0]

    # ------------------------------------------------------------- hazards
    def _collect_hazards(self, world):
        """`[(x_at_crossing, avoid_radius), ...]` for every enemy bullet
        and falling "spread" powerup that will cross the ship's *current*
        y-row within the lookahead window -- resolved exactly (see
        `_bullet_reach_tau`/`_linear_reach`), so nothing in a narrow, fast
        crossing can slip between sample points. The ship never moves
        vertically, so "the ship's y-row" is just `player.y` all the way
        down this frame's decision."""
        p = world.player
        target_y = p.y
        hazards = []
        for b in world.enemy_bullets:
            tau = _bullet_reach_tau(b, target_y, _DODGE_LOOKAHEAD)
            if tau is None:
                continue
            hx, _ = _bullet_pos_at(b, tau)
            hazards.append((hx, b.r + p.hitbox_r + _HAZARD_PAD))
        for pu in world.powerups:
            if pu.kind != "spread":
                continue
            tau = _linear_reach(pu.y, pu.vy, target_y, _DODGE_LOOKAHEAD)
            if tau is None:
                continue
            hx, _ = _powerup_pos_at(pu, tau)
            hazards.append((hx, pu.radius + 20.0 + _HAZARD_PAD))
        return hazards

    def _clearance(self, x, hazards):
        """Signed distance from `x` (on the ship's y-row) to the nearest
        hazard's hit surface -- negative means a hazard is projected to
        reach this exact x at the moment it crosses this row. `+inf` when
        there's nothing to avoid."""
        if not hazards:
            return float("inf")
        return min(abs(x - hx) - radius for hx, radius in hazards)

    def _safest_x(self, world, hazards):
        p = world.player
        lo, hi = PLAYER_HALF_X, FIELD_WIDTH - PLAYER_HALF_X
        best_x = p.x
        best_clear = self._clearance(p.x, hazards)
        x = lo
        while x <= hi:
            c = self._clearance(x, hazards)
            if c > best_clear:
                best_clear, best_x = c, x
            x += _GRID_STEP
        return best_x, best_clear

    # ---------------------------------------------------------- mode/goal
    def _update_mode(self, focus, hazards, p):
        """Hysteresis between "chase the fire-alignment spot" and "retreat
        to open field": entering align mode requires a healthy clearance
        margin, leaving it happens the instant that margin erodes -- so a
        genuine threat is reacted to immediately, but marginal, noisy
        clearance readings right at the boundary don't cause the ship to
        flap between the two behaviors every frame."""
        can_align = focus is not None and p.spread_timer <= 0
        clearance = (self._clearance(focus[2], hazards)
                     if can_align else float("-inf"))
        # Wherever the ship physically is right now takes priority over
        # the alignment goal's own assessment: mid-transit toward a shot
        # it can still be standing somewhere dangerous, and that has to
        # override instantly, no hold, no exception.
        if self._clearance(p.x, hazards) < _SAFE_EXIT:
            self._mode = "dodge"
            return
        if self._mode == "align":
            if not can_align or clearance < _SAFE_EXIT:
                self._mode = "dodge"
        else:
            if can_align and clearance >= _SAFE_ENTER:
                self._mode = "align"

    def _pick_dodge_x(self, world, hazards, dt):
        """The open-field x to head for while not chasing a shot.

        Recomputed fresh every frame -- with a full-field grid this is
        cheap, and the safest spot only drifts smoothly as hazards do, so
        this doesn't flap on its own. The only thing held for
        `_DODGE_HOLD` seconds is *switching away* from the current pick to
        some other comparably-safe spot (a genuine improvement in
        clearance, or the current pick actually going unsafe, both bypass
        the hold immediately) -- that's what stops the ship from
        oscillating between two similarly-safe candidates once it's
        already committed to one."""
        p = world.player
        self._dodge_hold = max(0.0, self._dodge_hold - dt)
        best_x, best_clear = self._safest_x(world, hazards)
        if self._dodge_x is None:
            self._dodge_x = best_x
            self._dodge_hold = _DODGE_HOLD
            return self._dodge_x
        # Danger at the *actual current spot* (not just the held
        # destination) always forces an immediate reconsideration --
        # covers the case where a fresh hazard threatens where the ship
        # already is while it's still mid-transit toward the held pick.
        current_clear = min(self._clearance(self._dodge_x, hazards),
                             self._clearance(p.x, hazards))
        if current_clear < 0.0 or self._dodge_hold <= 0:
            if current_clear < 0.0 or best_clear > current_clear + _MOVE_EPS:
                self._dodge_x = best_x
            self._dodge_hold = _DODGE_HOLD
        return self._dodge_x

    # --------------------------------------------------------- personality
    def _maybe_idle(self, world, focus, hazards, dt):
        """Nice-to-have quirk: when there's nothing to shoot at and the
        hazard scan is provably clean (no bullet or spread orb anywhere in
        the sampled window), occasionally drift to a screen edge and idle
        there for a beat. Deterministic from the run's own rng, never a
        wall-clock roll; never overrides an active target or a real
        hazard, so it can't cost a shot or a life."""
        if focus is not None or hazards:
            self._idle_timer = 0.0
            return None
        if self._idle_timer > 0:
            self._idle_timer -= dt
            return self._idle_x
        if self.rng.random() < _IDLE_CHANCE_PER_SEC * dt:
            self._idle_x = (_IDLE_MARGIN if self.rng.random() < 0.5
                             else FIELD_WIDTH - _IDLE_MARGIN)
            self._idle_timer = self.rng.uniform(_IDLE_MIN_DURATION,
                                                 _IDLE_MAX_DURATION)
            return self._idle_x
        return None


def create_pilot(run):
    return VoxelHellPilot(run)
