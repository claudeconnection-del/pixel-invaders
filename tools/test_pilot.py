"""Headless Cabinet Man pilot tests: the Solitaire reference pilot wins a
contrived solvable board, is deterministic from the run's seed, and the
score-integrity + handback plumbing behave; the Breaker "uncanny paddle"
pilot clears level 1 without losing a life and its interception solver is
verified against contrived trajectories; the Voxel Hell pilot never wastes a
shot over a modest wave horizon and its closed-form solvers are cross-checked
against brute-force stepping. No pygame display, no GL.

Run: python tools/test_pilot.py
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game import events as ev  # noqa: E402
from games.cards.deck import Card  # noqa: E402
import games.solitaire.game as solgame  # noqa: E402
from games.solitaire.pilot import create_pilot  # noqa: E402
import games.breaker.game as breakergame  # noqa: E402
from games.breaker.pilot import (  # noqa: E402
    create_pilot as breaker_create_pilot,
    solve_intercept, BreakerPilot, PADDLE_SPEED, _required_lead_time,
)
from games.breaker.world import PLAYING_STATE  # noqa: E402
import games.voxelhell.game as vhgame  # noqa: E402
from games.voxelhell.pilot import (  # noqa: E402
    create_pilot as voxelhell_create_pilot,
    solve_vertical_intercept, enemy_pos_at, _bullet_reach_tau,
)
from arcade.pilot import create_pilot_for, suppress_for_pilot  # noqa: E402
from game.entities import Bullet, InputState  # noqa: E402


def _solved_setup(run):
    """Mirror test_cards.test_autocomplete_and_double_click: a board with
    nothing face-down and one card left to place — always solvable."""
    run.model.foundations = {"S": [Card(r, "S") for r in range(1, 13)],  # up to Q
                             "H": [Card(r, "H") for r in range(1, 14)],
                             "D": [Card(r, "D") for r in range(1, 14)],
                             "C": [Card(r, "C") for r in range(1, 14)]}
    run.model.tableau = [{"down": [], "up": [Card(13, "S")]}] + \
                        [{"down": [], "up": []} for _ in range(6)]
    run.model.stock, run.model.waste = [], []
    run.won_flag = False


def test_pilot_wins_solvable_board():
    run = solgame.create_run("draw1", random.Random(1))
    _solved_setup(run)
    pilot = create_pilot(run)
    steps = 0
    while not run.model.won and steps < 200:
        assert pilot.step(run, 0.02) is None      # table game: acts directly
        steps += 1
    assert run.model.won and run.won_flag
    print(f"solitaire pilot wins a solvable board OK ({steps} steps)")


def test_pilot_determinism():
    def drive(seed):
        run = solgame.create_run("draw1", random.Random(seed))
        pilot = create_pilot(run)
        for _ in range(400):
            pilot.step(run, 0.03)
            if run.won_flag:
                break
        return (run.model.cards_home, run.model.moves, run.won_flag)

    a = drive(777)
    b = drive(777)
    assert a == b
    print(f"pilot determinism OK (same seed -> {a})")


def test_pilot_opt_in_and_creation():
    run = solgame.create_run("draw1", random.Random(2))
    pilot = create_pilot_for(solgame, run)
    assert pilot is not None and pilot.label == "Cabinet Man"

    class _NoOptIn:
        pass
    assert create_pilot_for(_NoOptIn, run) is None
    print("pilot opt-in (create_pilot_for) OK")


def test_pilot_touched_suppression():
    run = solgame.create_run("draw1", random.Random(3))
    run.pilot_touched = False
    assert not suppress_for_pilot(run)
    pilot = create_pilot(run)
    pilot.step(run, 0.02)
    run.pilot_touched = True          # set by the cabinet loop, as main.py does
    assert suppress_for_pilot(run)
    fresh = solgame.create_run("draw1", random.Random(4))
    assert not suppress_for_pilot(fresh)   # untouched runs are never suppressed
    print("pilot_touched flag + suppression helper OK")


def test_handback_state_machine():
    """The App-level handback: any real input clears the active pilot. Tests
    the pure detection + clearing logic directly (no pygame display needed)."""
    from main import App

    neutral = InputState()
    active = InputState(fire=True)
    assert App._pilot_real_input(active)
    assert not App._pilot_real_input(neutral)

    class _FakeApp:
        def __init__(self):
            self.pilot = object()
            self.wave_banner = None

        def post_banner(self, text, seconds):
            self.wave_banner = (text, seconds)

    fake = _FakeApp()
    App._handback_pilot(fake)
    assert fake.pilot is None and fake.wave_banner is not None
    # idempotent: handing back an already-inactive pilot is a no-op
    fake2 = _FakeApp()
    fake2.pilot = None
    App._handback_pilot(fake2)
    assert fake2.pilot is None and fake2.wave_banner is None
    print("handback state machine OK (real-input detection + flag clear)")


# -------------------------------------------------------- breaker: pilot
# Minimal stand-ins for BreakerWorld/BreakerRun so the interception + timing
# logic can be unit-tested against contrived trajectories directly, without
# running a full simulation.
class _StubBall:
    def __init__(self, x, y, vx, vy, r=8.0):
        self.x, self.y, self.vx, self.vy, self.r = x, y, vx, vy, r


class _StubWorld:
    def __init__(self, paddle_x, paddle_y, paddle_half, balls, bricks=()):
        self.state = PLAYING_STATE
        self.paddle_x = paddle_x
        self.paddle_y = paddle_y
        self.paddle_half = paddle_half
        self.balls = balls
        self.bricks = list(bricks)


class _StubRun:
    def __init__(self, world):
        self.world = world


def test_breaker_solve_intercept_straight_line():
    """A ball falling with no horizontal velocity arrives exactly under
    itself -- no wall bounce, trivial to hand-verify."""
    t, x = solve_intercept(ball_x=300, ball_y=100, vx=0, vy=200,
                           paddle_y=660, ball_r=8, field_width=640)
    assert abs(t - 2.71) < 1e-9
    assert abs(x - 300) < 1e-9
    print(f"solve_intercept straight-line OK (t={t:.3f}, x={x:.1f})")


def test_breaker_solve_intercept_wall_bounce():
    """A ball angled hard enough to clear the right wall before reaching
    paddle height reflects once and lands short of it. Cross-checked
    against a tiny brute-force stepper that replicates the sim's own
    left/right wall-bounce rule (no bricks, no top wall -- the ball is
    already descending) to independently confirm the analytic fold."""
    ball_x, ball_y, vx, vy = 300, 42, 191, 300
    paddle_y, ball_r, field_width = 660, 8.0, 640

    t, x = solve_intercept(ball_x, ball_y, vx, vy, paddle_y, ball_r, field_width)
    # Hand-derived: raw unfolded x = 300 + 191*2.0 = 682, 50px past the
    # right wall (632) -> single reflection lands at 2*632 - 682 = 582.
    assert abs(t - 2.0) < 1e-9
    assert abs(x - 582) < 1e-9

    def bruteforce(x, y, vx, vy, dt=0.0005):
        target_y = paddle_y - ball_r - 10
        lo, hi = ball_r, field_width - ball_r
        t = 0.0
        while y < target_y:
            x += vx * dt
            y += vy * dt
            t += dt
            if x < lo:
                x, vx = lo, abs(vx)
            elif x > hi:
                x, vx = hi, -abs(vx)
        return t, x

    bt, bx = bruteforce(ball_x, ball_y, vx, vy)
    assert abs(bt - t) < 0.01 and abs(bx - x) < 1.0, \
        f"analytic ({t:.3f},{x:.1f}) vs brute-force ({bt:.3f},{bx:.1f})"
    print(f"solve_intercept one-wall-bounce OK (t={t:.3f}, x={x:.1f}, "
          f"brute-force agrees)")


def test_breaker_pilot_reachability_edge_case():
    """The paddle must start moving exactly as early as reachability
    demands -- never a fixed "wait until N seconds left" guess. Construct a
    ball whose arrival leaves *just* enough time for a full-speed glide
    starting on the very first frame the pilot sees it (any later start
    would miss); a companion case with the same distance but generous time
    confirms the pilot still holds still when it doesn't need to move."""
    paddle_x0, target_x, paddle_y = 300.0, 600.0, 660.0
    distance = target_x - paddle_x0
    lead = _required_lead_time(distance, PADDLE_SPEED)
    assert abs(lead - distance / PADDLE_SPEED) < 1e-9

    ball_r = 8.0
    target_y = paddle_y - ball_r - 10
    vy = 300.0

    # Tight: only reachable if the glide starts this very frame. A naive
    # fixed threshold (e.g. "wait until 0.5s left") would fail this, since
    # t_remaining here (~0.715s) is well above any such constant.
    t_remaining_tight = lead + 0.001
    ball_y_tight = target_y - vy * t_remaining_tight
    world = _StubWorld(paddle_x0, paddle_y, 55.0,
                       [_StubBall(target_x, ball_y_tight, 0.0, vy)])
    pilot = BreakerPilot(_StubRun(world))
    inp = pilot.step(_StubRun(world), 1 / 60)
    assert inp.right and not inp.left, \
        "pilot failed to start moving on the first reachable-only-if-immediate frame"

    # Slack: same distance, but the ball is much further from paddle height
    # -- plenty of time, so the stillness quirk holds and it doesn't move.
    t_remaining_slack = lead + 2.0
    ball_y_slack = target_y - vy * t_remaining_slack
    world2 = _StubWorld(paddle_x0, paddle_y, 55.0,
                        [_StubBall(target_x, ball_y_slack, 0.0, vy)])
    pilot2 = BreakerPilot(_StubRun(world2))
    inp2 = pilot2.step(_StubRun(world2), 1 / 60)
    assert not inp2.left and not inp2.right, \
        "pilot moved early despite ample time -- stillness quirk broken"
    print("breaker pilot reachability edge case OK (moves exactly as late "
          "as necessary, stays still when it isn't)")


def test_breaker_pilot_clears_level_one():
    """Cabinet Man clears level 1 on three seeds without losing a single
    life -- zero deaths at *default* lives (not the lives=99 dodge from
    tools/test_games.py), since the point is to prove the interceptor
    itself never misses, not merely to survive long enough to see bricks."""
    DT = 1 / 60
    for seed in (1, 2, 3):
        run = breakergame.create_run("arcade", random.Random(seed))
        pilot = breaker_create_pilot(run)
        deaths = 0
        cleared = False
        frames = 0
        while frames < 60 * 60 * 30:
            inp = pilot.step(run, DT)
            run.update(DT, inp)
            for etype, data in run.drain_events():
                if etype == ev.PLAYER_HIT:
                    deaths += 1
                elif etype == ev.LEVEL_CLEAR and data["index"] == 0:
                    cleared = True
            frames += 1
            if cleared or run.run_over:
                break
        assert cleared, f"breaker pilot seed {seed}: never cleared level 1 ({frames} frames)"
        assert deaths == 0, f"breaker pilot seed {seed}: lost {deaths} lives clearing level 1"
        print(f"breaker pilot cleared level 1 seed={seed} in {frames} frames, 0 deaths")


def test_breaker_pilot_determinism():
    """Same seed -> identical run, frame for frame (no rng of its own, but
    proving it doesn't accidentally introduce nondeterminism e.g. via dict
    ordering or float drift some other way)."""
    def drive(seed):
        run = breakergame.create_run("arcade", random.Random(seed))
        pilot = breaker_create_pilot(run)
        DT = 1 / 60
        trace = []
        for _ in range(3000):
            inp = pilot.step(run, DT)
            run.update(DT, inp)
            run.drain_events()
            trace.append((round(run.world.paddle_x, 6), run.world.score,
                          len(run.world.bricks), len(run.world.balls)))
            if run.run_over:
                break
        return trace

    a, b = drive(555), drive(555)
    assert a == b
    print(f"breaker pilot determinism OK (same seed -> identical {len(a)}-frame trace)")


# -------------------------------------------------------- voxel hell: pilot
def test_voxelhell_solve_vertical_intercept():
    """The closed-form vertical-intercept solver converges to the same answer
    a brute-force stepper reaches, for a sinusoidally-bobbing target (mirrors
    Breaker's wall-bounce cross-check)."""
    class _Enemy:
        slot_x, slot_y, bob_phase, time_alive = 300.0, 120.0, 0.7, 3.4
        entry_t, entry_delay = 1.0, 0.0

    e = _Enemy()
    world_time = 5.0
    muzzle_y = 700.0 - 24.0
    speed = 700.0
    t, x = solve_vertical_intercept(
        lambda tau: enemy_pos_at(world_time, e, tau), muzzle_y, speed)

    # brute force: step a straight-up bullet from muzzle_y until it reaches
    # the enemy's live y, reading the enemy's exact position each step
    def bruteforce(dt=0.0002):
        y = muzzle_y
        tau = 0.0
        while True:
            ex, ey = enemy_pos_at(world_time, e, tau)
            if y <= ey:
                return tau, ex
            y -= speed * dt
            tau += dt

    bt, bx = bruteforce()
    assert abs(bt - t) < 0.01 and abs(bx - x) < 1.0, \
        f"analytic ({t:.4f},{x:.2f}) vs brute-force ({bt:.4f},{bx:.2f})"
    print(f"voxelhell solve_vertical_intercept OK (t={t:.4f}, x={x:.1f}, "
          f"brute-force agrees)")


def test_voxelhell_bullet_reach_tau():
    """`_bullet_reach_tau` finds a straight and a curved bullet's exact
    crossing of a target row, cross-checked by brute-force stepping."""
    # straight bullet
    b = Bullet(x=100.0, y=100.0, vx=40.0, vy=260.0)
    tau = _bullet_reach_tau(b, 640.0, 3.0)
    assert tau is not None and abs((b.y + b.vy * tau) - 640.0) < 1e-6

    # curved bullet: brute-force the same crossing with the sim's own update.
    # This one arcs up to ~y=440 then back down, so y=400 is crossed while
    # rising — the solver must find that first (earliest) crossing.
    row = 400.0
    bc = Bullet(x=300.0, y=120.0, vx=180.0, vy=200.0, curve=1.4)
    tau_c = _bullet_reach_tau(bc, row, 4.0)
    assert tau_c is not None
    sim = Bullet(x=300.0, y=120.0, vx=180.0, vy=200.0, curve=1.4)
    t = 0.0
    dt = 0.0002
    while sim.y < row and t < 4.0:
        sim.update(dt)
        t += dt
    assert abs(t - tau_c) < 0.02, f"curved reach {tau_c:.4f} vs brute {t:.4f}"
    print("voxelhell _bullet_reach_tau OK (straight + curved, brute agrees)")


def test_voxelhell_never_wastes_a_shot():
    """The headline invariant, measured precisely: every shot the pilot fires
    lands. A frame's `shots - hits` gap is only ever explained by bullets
    still in flight — never a *settled* miss (a fired bullet that arrived and
    connected with nothing). Asserted frame-by-frame across many seeds up to
    the wave-3 boundary, where it holds exactly; the pilot also fires
    substantially and reaches wave 3 every time.

    Scope note: the invariant is verified through the opening waves. In dense
    *late* waves an enemy still completing its fly-in (not yet a valid
    intercept target, so not yet a known column occupant) can very rarely
    drift into a shot's column mid-flight and eat it — a documented v1
    shadowing limitation in games/voxelhell/pilot.py; it costs a hit, not the
    pilot's life, and is empirically ~1 shot per several full games."""
    DT = 1 / 60
    for seed in range(1, 8):
        run = vhgame.create_run("campaign", random.Random(seed))
        pilot = voxelhell_create_pilot(run)
        frames = 0
        worst_settled = 0
        while frames < 60 * 90:
            inp = pilot.step(run, DT)
            run.update(DT, inp)
            run.drain_events()
            frames += 1
            s = run.world.stats
            settled = (s["shots"] - s["hits"]) - len(run.world.player_bullets)
            worst_settled = max(worst_settled, settled)
            if s["wave_reached"] >= 3 or run.run_over:
                break
        s = run.world.stats
        assert worst_settled <= 0, \
            (f"seed {seed}: settled miss (wasted shot) before wave 3 — "
             f"worst gap beyond in-flight bullets was {worst_settled}")
        assert s["shots"] >= 10, f"seed {seed}: pilot barely fired ({s['shots']})"
        assert s["wave_reached"] >= 3, \
            f"seed {seed}: only reached wave {s['wave_reached']}"
    print("voxelhell pilot never wastes a shot OK "
          "(no settled miss through wave 3, 7 seeds)")


def test_voxelhell_pilot_determinism():
    def drive(seed):
        run = vhgame.create_run("campaign", random.Random(seed))
        pilot = voxelhell_create_pilot(run)
        DT = 1 / 60
        trace = []
        for _ in range(1500):
            inp = pilot.step(run, DT)
            run.update(DT, inp)
            run.drain_events()
            trace.append((round(run.world.player.x, 6), run.world.score,
                          len(run.world.enemies), run.world.stats["shots"]))
            if run.run_over:
                break
        return trace

    a, b = drive(7), drive(7)
    assert a == b
    print(f"voxelhell pilot determinism OK (same seed -> identical "
          f"{len(a)}-frame trace)")


def main():
    test_pilot_wins_solvable_board()
    test_pilot_determinism()
    test_pilot_opt_in_and_creation()
    test_pilot_touched_suppression()
    test_handback_state_machine()
    test_breaker_solve_intercept_straight_line()
    test_breaker_solve_intercept_wall_bounce()
    test_breaker_pilot_reachability_edge_case()
    test_breaker_pilot_clears_level_one()
    test_breaker_pilot_determinism()
    test_voxelhell_solve_vertical_intercept()
    test_voxelhell_bullet_reach_tau()
    test_voxelhell_never_wastes_a_shot()
    test_voxelhell_pilot_determinism()
    print("ALL PILOT TESTS PASSED")


if __name__ == "__main__":
    main()
