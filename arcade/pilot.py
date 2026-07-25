"""Cabinet Man: the cabinet's summonable house player. Any game can opt in by
exporting `create_pilot(run)` from its `games/<id>/game.py` module — absent
means no Cabinet Man for that game. A pilot is a duck-typed object with:

    label            - short display name for the HUD badge
    step(run, dt) -> InputState | None
        Called once per frame while Cabinet Man has the controls, BEFORE the
        run's own update(). Sim games (Voxel Hell, Serpent, Breaker, ...)
        return a synthesized InputState for the cabinet to feed into
        run.update() instead of the human's; table games (Solitaire, Rummy,
        ...) act directly on the run/model's own PUBLIC methods and return
        None (the cabinet already drives those games with update(dt, inp)
        where inp is unused, same as the smoke test does).

Pilots should be deterministic given the run's own rng where feasible — no
wall-clock randomness — so a pilot run is exactly reproducible from the run's
seed, same as everything else in this cabinet.
"""


def create_pilot_for(module, run):
    """`module.create_pilot(run)` if the game opts in, else None."""
    create = getattr(module, "create_pilot", None)
    return create(run) if create is not None else None


def suppress_for_pilot(run):
    """True once Cabinet Man has driven any part of `run` — score
    submission, replay-share, and achievement unlocks all check this so a
    pilot-driven run can't boost the player's own stats. Cabinet Man is a
    showman, not a booster."""
    return getattr(run, "pilot_touched", False)
