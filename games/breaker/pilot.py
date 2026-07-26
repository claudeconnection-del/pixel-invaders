"""Cabinet Man's reference pilot for Voxel Breaker: "the uncanny paddle."

The house doesn't rally. It doesn't dive. It stands dead still while the
ball is anywhere but imminent, then makes exactly one clean move -- timed to
the frame -- straight to the interception point, and it's already decided
which edge of the paddle it wants to meet the ball with before it gets
there.

How it works, each frame:

  1. `solve_intercept` projects the soonest-arriving descending ball's
     current position/velocity forward at constant speed to the paddle's
     contact line, folding in any left/right wall bounces along the way
     (a triangle-wave reflection of the unfolded x, same idea as unfolding
     a light ray in a hall of mirrors). Brick collisions aren't modeled --
     re-solving fresh from the ball's live state every single frame means a
     bounce off a brick that changes the ball's course is absorbed
     automatically on the very next frame, no explicit brick sim required.
  2. `_aim_paddle_x` decides *where on the paddle* to meet the ball: it
     always aims for whichever surviving brick cluster's outer edge is
     nearer the ball's natural landing spot, and asks for a firm
     edge-of-paddle offset (not a soft nudge) toward it -- the paddle
     carves the field from the outsides in, one clean column at a time.
     The requested offset is clamped to whatever the field's walls
     physically allow, so the aim never costs a catch: if the ball is
     already tucked against a wall, "sending it further that way" just
     isn't on the table, and the pilot settles for what's reachable.
  3. The paddle only moves once the exact time required to glide there at
     its top speed (`_required_lead_time`) has caught up with the ball's
     time of arrival -- computed fresh every frame from the *live*
     distance and the *live* time-to-impact, never a fixed "wait until
     0.3s left" guess. For an ordinary shot that means long stillness then
     one smooth glide that lands right as the ball does. For a ball moving
     fast enough that the full-speed glide needs the whole remaining
     window, that threshold is already satisfied on the very first frame
     the pilot sees it -- so it starts immediately, exactly as early as
     reachability demands and not a frame earlier.

Powerups aren't chased: the paddle's path is set entirely by the
interception + aim logic above, and if that path happens to pass through a
falling capsule the catch is free (the world's own collision check does it
automatically). Nothing here spends a frame of positioning on a powerup.

No randomness is used anywhere -- the whole thing is a geometric function of
the world's live state, so it's deterministic for free from the run's own
seed (which only ever influences things indirectly, via the ball's launch
angle and brick/powerup layout).
"""
from game.entities import InputState, FIELD_WIDTH
from games.breaker.world import PLAYING_STATE

# Mirrors BreakerWorld._move_paddle's base speed (px/s). inp.focus halves it
# in the real sim but the pilot never sets focus, so full speed always
# applies. Not exported as a constant in world.py -- keep in sync by hand if
# that literal ever changes.
PADDLE_SPEED = 420.0

# Small forward safety margin (seconds) on the "must start moving now"
# deadline -- makes the glide begin a hair before the mathematically latest
# possible instant instead of shaving it exactly to the frame. Doesn't
# change the underlying reachability math, just how comfortable it looks.
_LEAD_BUFFER = 0.05

# Paddle-contact "english": how far off-center (as a fraction of
# paddle_half) the pilot aims its returns when it wants the ball to go left
# or right. Capped well short of 1.0 (the true edge, where a hit can graze
# and miss) so aiming never risks the catch.
_AIM_OFFSET = 0.8

# Treat sub-pixel gaps as "already there" / "already aligned" so the pilot
# doesn't jitter the direction bit back and forth at the destination.
_EPS = 1.0


def solve_intercept(ball_x, ball_y, vx, vy, paddle_y, ball_r=8.0,
                     field_width=FIELD_WIDTH):
    """Project a ball moving in a straight line at constant velocity forward
    to the paddle's contact line (`paddle_y - ball_r - 10`, matching the
    position the sim itself snaps a ball to on a paddle bounce), folding in
    any number of left/right wall bounces along the way.

    Returns `(t, x)` -- seconds until arrival and the x it will arrive at --
    or `None` if the ball isn't currently descending (`vy <= 0`): a
    constant-velocity projection of a rising ball can't say when it will
    turn around, since that depends on brick collisions this solver doesn't
    model.
    """
    if vy <= 0:
        return None
    target_y = paddle_y - ball_r - 10
    t = max(0.0, (target_y - ball_y) / vy)
    raw_x = ball_x + vx * t

    lo, hi = ball_r, field_width - ball_r
    span = hi - lo
    if span <= 0:
        return t, lo
    period = 2 * span
    m = (raw_x - lo) % period
    if m > span:
        m = period - m
    return t, lo + m


def _required_lead_time(distance, speed=PADDLE_SPEED):
    """Seconds of continuous full-speed travel needed to cover `distance`."""
    return abs(distance) / speed if speed > 0 else float("inf")


def _edge_targets(bricks):
    """The two "cluster edges" -- leftmost and rightmost surviving brick x --
    the aim heuristic carves toward next. None once the field is clear."""
    if not bricks:
        return None
    xs = [b.x for b in bricks]
    return min(xs), max(xs)


class BreakerPilot:
    """Cabinet Man at the paddle: see module docstring."""

    label = "Cabinet Man"

    def __init__(self, run):
        pass  # purely geometric -- no rng, no per-run state to seed

    def step(self, run, dt):
        world = run.world
        # Fire is a no-op without an active laser powerup and free once one
        # lands (auto-fires on cooldown) -- always worth holding.
        inp = InputState(fire=True)

        if world.state != PLAYING_STATE or not world.balls:
            return inp   # nothing airborne to react to: stay put

        target = self._choose_target(world)
        if target is None:
            # Every ball is currently rising or working through the brick
            # field -- no arrival clock to race yet, so there's no
            # "stillness deadline" to compute. Rather than freeze wherever
            # the last return happened to leave it (which, after a hard
            # edge-aimed return, is often jammed against a wall), drift
            # back to the field's center: that minimises the worst-case
            # distance to *either* wall, so whichever side the ball
            # eventually comes down on, the next real interception glide
            # is never a full-field sprint against the clock. One settling
            # glide back to a neutral stance, then true stillness again --
            # not a second reaction to the same ball.
            return self._drift_to_rest(world, inp)

        t_remaining, ball_x_at_paddle = target
        aim_x = self._aim_paddle_x(world, ball_x_at_paddle)
        distance = aim_x - world.paddle_x
        if abs(distance) < _EPS:
            return inp   # already exactly where it needs to be

        lead = _required_lead_time(distance)
        if lead + _LEAD_BUFFER < t_remaining:
            return inp   # plenty of time left: the stillness quirk

        inp.left = distance < 0
        inp.right = distance > 0
        return inp

    # ------------------------------------------------------------- helpers
    def _drift_to_rest(self, world, inp):
        distance = FIELD_WIDTH / 2 - world.paddle_x
        if abs(distance) >= _EPS:
            inp.left = distance < 0
            inp.right = distance > 0
        return inp

    def _choose_target(self, world):
        """The soonest-to-arrive descending ball's (t, x), or None."""
        best = None
        for ball in world.balls:
            solved = solve_intercept(ball.x, ball.y, ball.vx, ball.vy,
                                      world.paddle_y, ball.r)
            if solved is not None and (best is None or solved[0] < best[0]):
                best = solved
        return best

    def _aim_paddle_x(self, world, ball_x_at_paddle):
        """Where to park the paddle center so the ball lands with the
        english needed to send it toward the nearer surviving edge cluster,
        clamped to whatever the field walls make reachable."""
        half = world.paddle_half
        lo, hi = half, FIELD_WIDTH - half

        edges = _edge_targets(world.bricks)
        if edges is None:
            return min(max(ball_x_at_paddle, lo), hi)

        left_edge, right_edge = edges
        nearer = (left_edge
                  if abs(ball_x_at_paddle - left_edge) <= abs(ball_x_at_paddle - right_edge)
                  else right_edge)

        if abs(nearer - ball_x_at_paddle) < _EPS:
            desired_offset = 0.0
        else:
            desired_offset = _AIM_OFFSET if nearer > ball_x_at_paddle else -_AIM_OFFSET

        # offset = (ball_x - paddle_x) / half; paddle_x in [lo, hi] bounds
        # the achievable offset range -- clamp the request into it so aim
        # never comes at the cost of a miss.
        achievable_lo = (ball_x_at_paddle - hi) / half
        achievable_hi = (ball_x_at_paddle - lo) / half
        desired_offset = min(max(desired_offset, achievable_lo), achievable_hi)

        paddle_x = ball_x_at_paddle - desired_offset * half
        return min(max(paddle_x, lo), hi)


def create_pilot(run):
    return BreakerPilot(run)
