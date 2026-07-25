# Speedrun category — implementation plan

Spec: `docs/superpowers/specs/2026-07-25-speedrun-category-design.md`.
**Status: awaiting owner approval (CAB-17) — do not start Increment 1 until the spec's open
questions are answered.** Once approved: TDD; commit per increment; message trailer
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
Branch: `secret-local-multiplayer` (do not merge to main without asking).

**Goal:** a new SPEEDRUN cabinet category, proven first by one flagship game — **Riftrunner**, a
Mari0-style portal platformer — with a category engine (timer/splits/any%/replay-as-submission/PB
board) built game-agnostic from the start so the racer and top-down follow-ups (later epics) are
"write a model + view," not new plumbing.

## Global constraints
- Headless-testable core (timer/splits math, portal teleport math, level/physics sim) with no GL.
  Rendering/wiring is GL, verified live (`python main.py` / hidden-GL capture), same split as
  every other game on this cabinet.
- No new asset pipeline — levels are in-code ASCII grids (`LEVELS`), matching
  `games/breaker/world.py` / `games/voxeldoom/world.py`.
- Reuse, don't redesign: `meta/replay.py`, `meta/ghost.py`, `meta/leaderboard.py`,
  `meta/achievements.py`, the server's `/api/v1/scores` pair all get **additive** extensions at
  most (new optional fields/bits/columns), never a schema/behavior change for existing games.
- Follow existing patterns: `arcade.game_api` `GameInfo`/`GameRun`, `game.events` vocabulary
  (reuse `LEVEL_CLEAR`/`RUN_END`, no new event types in v1), `OverlayRenderer` drawing.

## Increment 1 — category engine (headless, TDD)
- New shared module (home TBD at pickup time — likely `games/speedrun/category.py` or
  `meta/speedrun.py`, following the `games/cards/` / `games/board/` shared-kit precedent): pure
  functions/small classes for `time_cs` accounting from a dt stream, split recording
  (`record_split(elapsed, index)`), the category registry (`{"any_pct": ...}`, structured so
  `low_pct` is a later additive entry), and the score-inversion helpers
  (`to_score(time_cs)` / `from_score(score)` around `TIME_CEILING`).
- `tools/test_speedrun.py`: dt-stream summation matches expected `time_cs`; splits recorded in
  order; score inversion round-trips; category registry rejects an unknown category id.
- Commit `feat(speedrun): category engine — timer, splits, any% (headless core)`.

## Increment 2 — Riftrunner headless core (portal platformer sim)
- `games/riftrunner/__init__.py`, `games/riftrunner/model.py`: grid world + gravity/move/jump
  physics, the `LEVELS` ASCII format (§4 of the spec: `#`/`.`/`P`/`X`/`=`/`^`), portal placement
  (one pair, axis-aligned, portal-able-tile check), the momentum-preserving teleport transform,
  hazard-tile reset-to-checkpoint, goal detection emitting `LEVEL_CLEAR`/`RUN_END` (`summary`
  carrying `time_cs`/`splits`/`category`).
- `tools/test_riftrunner.py`: deterministic sim (same seed+scripted inputs → identical end
  state/time), portal teleport math (velocity magnitude preserved, direction rotated correctly
  for each of the 4 axis-aligned orientations), hazard reset, goal/split events fire at the right
  frame, illegal portal placement (non-`#` tile) rejected. No GL.
- Commit `feat(riftrunner): portal platformer rules + physics (headless core)`.

## Increment 3 — Riftrunner view/input + SPEEDRUN category registration (GL, live)
- `games/riftrunner/game.py`: `INFO` (`GameInfo`, category SPEEDRUN, `modes=[("any_pct",
  "ANY%")]`), `RiftrunnerRun` (`GameRun`) — overlay rendering (`OverlayRenderer`, matching
  `games/breaker`'s approach), crosshair aim + portal-placement input, HUD timer/split display,
  win/finish screen.
- Register `("SPEEDRUN", ["riftrunner"])` in `games/__init__.py` `CATEGORIES`.
- `games/riftrunner/bot.py`: attract-mode demo driver (`games/breaker/bot.py` shape) — never
  touches stats/achievements/PB board, per the existing attract contract.
- Verify via hidden-GL capture + `tools/smoke_test.py` coverage; commit
  `feat(riftrunner): view, input, attract demo; register SPEEDRUN category`.

## Increment 4 — determinism wiring: replay + ghost
- Additive `meta/replay.py` change: extend `_BITS` with `("portal_a", 64), ("portal_b", 128)`
  (old replays unaffected — unset bits decode False); Riftrunner opts into `analog=True` to reuse
  `aim_x`/`aim_y` as the portal crosshair.
- Wire `ReplayRecorder`/`Replay` into Riftrunner's run loop the same way every other game does;
  regression test: recording a scripted run and replaying it reproduces identical `time_cs` and
  `splits`, bit-for-bit.
- `ghost_sample()` on `RiftrunnerRun` returning `(player_x, player_y)` — no changes needed to
  `meta/ghost.py` (already generic); verify the PB ghost races correctly for `riftrunner:any_pct`.
- `tools/test_riftrunner.py` (or a new `tools/test_speedrun.py` case) covers the replay-reproduces-
  identical-time property explicitly — this is the property the whole "replay is the submission"
  claim rests on.
- Commit `feat(speedrun): replay determinism + ghost integration for Riftrunner`.

## Increment 5 — local PB board + submission flow
- `meta/leaderboard.py` usage (unchanged): `submit(profile, "riftrunner", "any_pct", name,
  to_score(time_cs), extra={"time_cs", "splits", "category": "any_pct"})`.
- A PB-board UI screen (or a panel on the existing scores/leaderboard screen) showing the
  category's best time (re-derived via `from_score`), splits, and a "watch replay" hook into the
  existing Replay Theater.
- `meta.replay.keep()` called on finish (existing generic keeper-save, no new format).
- Commit `feat(riftrunner): local PB board + replay-as-submission flow`.

## Increment 6 — replay signing (depends on CAB-13)
- **Blocked/gated on CAB-13 landing its signing primitive** (see spec Open Question 1). If
  CAB-13 hasn't landed when this increment is picked up: stop here and flag it rather than
  building a placeholder signer — signing is the whole tamper-resistance point and shouldn't be
  half-implemented.
- Once available: call CAB-13's `sign(replay_dict)` on finish, attach `replay["sig"]`; PB-board
  and outbox entries carry `sig` in their `extra`/payload.
- Test: a hand-edited replay JSON fails `verify()`; an unmodified recorded replay passes.
- Commit `feat(riftrunner): sign replays via CAB-13's tamper-mark primitive`.

## Increment 7 — server category leaderboard (additive) + outbox
- `server/db.py`: additive nullable `meta TEXT` column on `scores` (guarded add-if-missing
  migration; `NULL` for all existing rows/games — no other column/index/behavior changes).
- `server/app.py`: `ScoreSubmission` gains one optional, length-capped field (`meta: str | None`,
  JSON blob holding `time_cs`/`splits`/`sig`); `insert_score`/`top_scores` pass it through
  unchanged otherwise. No new endpoints — `/api/v1/scores` GET/POST serve the SPEEDRUN category
  exactly like any other game's board.
- `meta/outbox.py`: additive optional payload alongside the existing game/mode/name/score/wave
  fields so a queued speedrun submission survives an offline retry with its `meta` blob intact.
- `server/test_server.py`: submit-with-meta round-trips; submit-without-meta (any other game)
  is unaffected; oversized `meta` is rejected (mirrors the existing match `state` size cap).
- Commit `feat(server): additive meta column for speedrun replay verification data`.

## Increment 8 — achievements + unlocks
- `games/riftrunner/achievements.py`: `first_finish`, `sub_target` (per-level time bar),
  `no_reset` (no hazard hit), `hundred_runs` grind — `meta.achievements.Achievement` pattern.
- Cosmetic unlock (portal-color/trail skin) via existing `has_skins`/`skin_resolver`.
- Note (not built this round — third game doesn't exist yet): the cross-game "PB in all three
  SPEEDRUN games" achievement follows the `meta.achievements.evaluate_ambient` pattern
  (cabinet-level evaluator reading multiple games' profile sections); stub the hook point in a
  comment, implement once Increment 10 (top-down) or its racer counterpart ships.
- Commit `feat(riftrunner): achievements + cosmetic unlocks`.

## Increment 9+ — racer and top-down (future epics, not detailed here)
Each follows Increments 1–8's shape against the *same* category engine from Increment 1
(untouched): headless physics/track-or-level core (TDD) → view/input + category registration
(GL, live) → replay/ghost wiring (mostly free — Increment 4's `_BITS`/ghost pattern, extended only
if the game needs a genuinely new discrete input) → PB board (free — Increment 5's code, new
`game_id`) → achievements. These get their own short design pass at pickup time (track/level
roster, physics feel) rather than being pre-specified now, per the spec's scope-ladder call.

## Self-review
Spec coverage: roster + recommendation (Increment 2's existence *is* the "platformer ships
first" call), category mechanics + any% + replay-as-submission + PB/server boards (I1, I5, I7),
determinism + ghost (I4), level format + portal v1 scope (I2), achievements/unlocks/attract (I3,
I8). CAB-13 dependency is called out as a hard gate on I6 rather than papered over. Headless core
(timer math, portal/physics sim) fully testable before any GL, matching this repo's TDD
convention; GL/wiring increments are each independently small and commit-sized like the
card/tabletop suite's plan.
