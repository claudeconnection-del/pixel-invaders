# Speedrun category — design

**Proposed direction (2026-07-25) — CAB-17. Not yet approved: this doc + its plan are a STOP
for the owner's sign-off before any implementation lands** (see Open questions below). Once
approved, work follows the usual pattern: headless-core-first increments, TDD, commit per
increment, this branch (`secret-local-multiplayer`).

Turns the roadmap's "Later" SPEEDRUN idea into a scoped v1: one flagship game (a Mari0-style
portal platformer) shipping a new **SPEEDRUN** cabinet category, a run-timer/splits/category
mechanic shared by every game in that category, and a submission model where **the replay itself
is the leaderboard entry** — reusing `meta/replay.py`, `meta/ghost.py`, and
`meta/leaderboard.py` as they exist today rather than inventing parallel machinery.

## Why / feel

Every game in this cabinet is already a pure seeded simulation driven by a recorded
seed+input-stream (`meta/replay.py`) — that determinism is exactly what real speedrunning
needs: a submission that *is* the proof, not a claim. The category's job is thin: start a
clock when the run starts, stop it (and snapshot split times) at defined checkpoints, and hand
the finished run's replay to the existing recording/leaderboard/ghost plumbing with almost no
new concepts. The flashy part — Mari0-style portals — earns its place because portal-route
speedrunning (sequence breaks, momentum tricks, portal skips) is a genre with real audience
pull, and it gives the cabinet something no other game here has: a movement mechanic players
will want to master and share clips of.

## 1. Game roster + scope ladder

Roadmap names three: a Mari0-style portal platformer, a racer, a top-down. **Recommendation:
ship the portal platformer first, as the SPEEDRUN flagship; racer and top-down follow later,
reusing the category engine unchanged.**

| # | Game (working title) | Genre | Ships |
|---|---|---|---|
| 1 | **Riftrunner** (`riftrunner`) | 2D portal platformer | v1 — flagship |
| 2 | **Scorch Circuit** (`scorch`) | top-down racer | follow-up |
| 3 | **Voxel Dash** (`voxeldash`) | top-down action-platformer | follow-up |

Working titles only — naming is the owner's call (open question below).

**Why the platformer first:**
- Portals are the one mechanic on this roster with genuine speedrunning cachet (Portal/Mari0
  communities live on sequence breaks and momentum preservation) — it's the natural flagship
  for a *speedrun* category, not just "another game with a clock on it."
- Cleanest fit for the category's core primitives: a level naturally segments into rooms/gates,
  so **splits** fall out of level geometry for free (reuse the existing `LEVEL_CLEAR` event —
  see §3) instead of needing bespoke checkpoint design like a racer's track sectors would.
  and doesn't add a second team-vs-team layer, keeping the first slice small.
- Lowest implementation risk: it's a 2D grid-and-physics sim rendered through the
  `OverlayRenderer`, exactly like `games/breaker` and `games/serpent` — no new GL/voxel-scene
  work, no networking. Level data is an in-code ASCII grid, mirroring `games/breaker/world.py`
  `LEVELS` and `games/voxeldoom/world.py` `MAPS` almost verbatim (see §4).
- A racer needs track/lap-boundary design and different physics (steering + drift); a top-down
  needs its own feel. Both are real work, not free — they're follow-ups, not throw-ins.

**Scope ladder:** the category engine (timer, splits, category rules, replay-as-submission, PB
board, ghost hookup — all of §2/§3) is built once against Riftrunner and is **game-agnostic by
construction** — the follow-up games are "write a model.py + game.py that emits the right
events," not new category plumbing. Racer and top-down are each their own headless-core-first
increment pair, sequenced but not detailed line-by-line in this round's plan (see the plan doc's
final section) — they get their own spec-level pass (roster of track/level data, physics) when
picked up, same as this doc does for the platformer.

All three are seeded deterministic sims, same as every other game here: `create_run(mode, rng)`,
`GameRun` duck-type, no networking, no per-run randomness beyond the seed.

## 2. SPEEDRUN category mechanics

New cabinet category `("SPEEDRUN", ["riftrunner"])` in `games/__init__.py` `CATEGORIES`
(racer/top-down append to the list later — additive, one line each).

### Run timer + splits
- The timer is **simulation time**, not wall clock: the sum of recorded per-frame `dt` since
  the run started (exactly the quantity `meta/replay.py`'s `Replay.duration` already computes
  from `dts`). Displayed/stored in **centiseconds** (`time_cs = round(elapsed * 100)`) — the
  common speedrunning unit and coarse enough to be a clean sortable int.
- **Splits** are just timestamps recorded when the sim emits a checkpoint event. Riftrunner
  already needs level/room transitions, so splits reuse the existing generic
  `game.events.LEVEL_CLEAR` event (`{index, bonus}` today; the run's `on_frame`/`run_summary`
  layer — not the shared event schema — is what records `time_cs` at each occurrence into a
  `splits: [int]` list). No new event type required for v1.
- A run's finish is the existing `RUN_END` event (`{win, summary}`); `summary` is already an
  arbitrary dict per `run_summary()`, so it carries `{time_cs, splits, category}` with zero
  changes to the shared event vocabulary.

### Category rules
- **v1 ships exactly one category: any%** — reach the level's goal tile by any means the sim
  allows (portal skips, sequence breaks, whatever a legal input stream can produce); fastest
  `time_cs` wins. This is deliberately the whole ruleset for v1: it needs no extra bookkeeping
  beyond "did you touch the goal," which keeps the category engine trivial to get right first.
- **Low% is explicitly deferred, not designed here.** Low% needs a well-defined "counted
  action" to abstain from (e.g. collectibles/upgrades used), and Riftrunner v1 has no
  collectibles (see §4 non-goals) — so low% isn't even meaningful until a later content pass
  adds something to withhold. The category registry is a small `{id: validator}` mapping
  precisely so adding `low_pct` later is additive, not a redesign.
- Category maps to `GameInfo.modes` exactly like every other game's mode list (e.g. Solitaire's
  draw-1/draw-3): `modes=[("any_pct", "ANY%")]`.

### Replay IS the submission
- On finish, the run's `meta/replay.py` `ReplayRecorder` (already wired into every game's run
  loop the same way) has the complete seed + per-frame dt/input stream. That recording — not a
  client-asserted "my time was X" — is the artifact submitted.
- Per CAB-13's HMAC tamper-mark work, the finished replay is **signed** before it's offered to
  the local PB board or the server (see Open questions — this spec takes CAB-13's signing
  primitive as a black box: something like `sign(replay_dict) -> sig` / `verify(replay_dict,
  sig) -> bool`, attached as `replay["sig"]`). The displayed/submitted `time_cs` and `splits`
  are *derived from the recording itself* (the same numbers the recorder already tracked while
  driving the run), not from a separately-trusted live timer value — so a tampered time and a
  tampered replay are the same tamper, and CAB-13's signature covers both. Full server-side
  re-simulation-to-verify is **out of scope for v1** (noted as a natural v2 hardening step once
  CAB-13's primitive exists) — v1's guarantee is only "this replay came from a real cabinet
  build and hasn't been hand-edited since," not "the server independently reproduced this time."
- Kept: the run's replay is saved via the existing `meta.replay.keep()` (a timestamped keeper,
  same as any other game's "save this run") — no new persistence format.

### Local PB board + server category leaderboards
- **Local PB board** reuses `meta/leaderboard.py` unchanged, keyed by `board_key(game_id,
  category)` exactly like every other game's board. The one wrinkle: that board sorts
  `score DESC` (higher-is-better), but a speedrun's "best" is the *lowest* time. Rather than
  redesign the leaderboard (descending-sort local board, or the server's `ORDER BY score DESC`),
  **encode the stored `score` as an inverted time**: `score = TIME_CEILING - time_cs` where
  `TIME_CEILING` is a fixed large constant (e.g. `99_999_999` cs ≈ 11.5 days of run time — comically
  generous headroom). Lower real time → higher stored score → sorts to the top with the
  existing DESC ordering, zero changes to `meta/leaderboard.py`, `server/db.py`'s
  `top_scores`/index, or the sort semantics anywhere else in the cabinet. The UI re-derives the
  human time as `TIME_CEILING - score` for display. `extra={"time_cs", "splits", "category",
  "sig"}` rides in `meta.leaderboard.submit`'s existing `extra` param unchanged.
- **Server category leaderboards are additive, not a redesign.** `game=<riftrunner>`,
  `mode=<any_pct>` against the *existing* `/api/v1/scores` POST/GET pair — the server already
  has no opinion on what "score" means per game, so the inverted-time encoding above is
  invisible to it. The only server change is carrying the extra verification/detail payload
  (`time_cs`, `splits`, `sig`) alongside the score: one new **optional, nullable** field on
  `ScoreSubmission` (e.g. `meta: str | None`, a small JSON blob, length-capped like `state` is
  on the match endpoints) and one new **nullable** `meta TEXT` column on the `scores` table
  (guarded `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`-style migration, `NULL` for every existing
  row/game — nothing else changes shape). `top_scores`/`get_scores` pass it through if present.
  No new endpoints, no schema redesign, no change to how any other game submits scores.
- The offline `meta/outbox.py` queue is reused for away-from-home submission retry; it needs the
  same small additive change (an optional payload blob alongside its existing
  game/mode/name/score/wave fields) to carry the `meta` blob through to the eventual POST.

## 3. Determinism requirements

- **Fixed dt is already the whole point of `meta/replay.py`**: it stores exact per-frame `dt`
  (not rounded), because the sim is a pure function of `seed, dt-stream, inputs`. The speedrun
  timer piggybacks on exactly this — `time_cs` is derived by summing the *same* recorded dts,
  so a re-played replay reproduces the identical finish time and identical split timestamps
  bit-for-bit. This is the property that makes "the replay is the submission" true, not just
  a slogan: anyone (a future verifier, or just the player) can re-run the recording headlessly
  and get the same number back.
- **New discrete inputs for portals.** `meta/replay.py`'s `_BITS` currently packs six named
  booleans (`left/right/up/down/focus/fire`) into one mask byte; Riftrunner needs at least two
  more discrete actions (place portal A / place portal B) that don't exist yet. The compatible
  move is **additive**: append new named bits to `_BITS` (e.g. `("portal_a", 64), ("portal_b",
  128)`, still fits in one int) rather than repurposing existing ones. Old replays without those
  bits decode fine (the bits are simply unset → both False) — no schema bump, no `SCHEMA`
  version change needed. Portal aim reuses the existing `aim_x`/`aim_y` analog fields (already
  present for the FPS games) as the crosshair; Riftrunner opts into `analog=True` recording like
  the FPS games do, rather than adding yet another new field.
- **Ghost integration needs zero changes to `meta/ghost.py`.** It's already fully generic: any
  `GameRun` that implements `ghost_sample()` gets recorded (uniform 20 Hz, capped/downsampled,
  linear-interpolated on playback) and the cabinet already race-ghosts personal bests with it.
  Riftrunner's `ghost_sample()` returns `(player_x, player_y)`; `board_key(game_id, mode)` with
  `mode = category` slots in exactly like every other game's ghost — the PB ghost for `any_pct`
  is stored and raced automatically. Splits/HMAC are a leaderboard-and-replay concern; the ghost
  is a separate, already-generic rendering aid and doesn't need to know about either.

## 4. Level format (Riftrunner) + portal mechanics v1 scope

### Level format: in-code, no assets
Mirrors `games/breaker/world.py`'s `LEVELS` / `games/voxeldoom/world.py`'s `MAPS` almost
exactly — a Python list of `(name, rows)` where `rows` is a list of equal-length strings, one
char per grid cell. No tilemap files, no image assets, no external editor — consistent with
this repo's "everything generated from code" identity.

```python
LEVELS = [
    ("FIRST GAP", [
        "########################",
        "#P.....................#",
        "#.....##########........#",
        "#.....#........#........#",
        "#.....#........#.......X#",
        "########################",
    ]),
    ...
]
```

Proposed v1 symbol set (small, on purpose):
- `#` solid wall — **portal-able** surface by default.
- `.` open floor/air.
- `P` player spawn. `X` goal (level clear / split fires here).
- `=` solid wall that is **not** portal-able (keeps some surfaces "safe," a common
  portal-platformer texture — also gives level design a lever without new mechanics).
- `^` a hazard tile (instant reset-to-last-checkpoint, not a "lose the run" — speedrunners
  restart fast; no lives/HP system needed for v1).

That's the entire tile vocabulary for v1. No moving platforms, no buttons/doors, no collectible
items (see non-goals) — enough to build real portal puzzles/gaps without any content pipeline
beyond writing more `LEVELS` entries.

### Portal mechanics v1 scope (kept deliberately small)
- Exactly **one portal pair**, blue + orange, shared/global (placing a new blue portal replaces
  the old one). No more than two portals ever exist.
- Placed by aiming (mouse/`aim_x,aim_y`, or a keyboard/pad reticle fallback like the FPS games'
  aim) at a portal-able (`#`) tile and pressing the new `portal_a`/`portal_b` input; the portal
  attaches to that tile's surface, axis-aligned (up/down/left/right faces only — **no angled
  surfaces** in v1, since axis-aligned collision is what the existing grid sim already gives us
  for free).
- Walking or falling into one portal exits the other; **momentum/speed is preserved through the
  transform** (this is the one non-negotiable "feels like Portal" mechanic — velocity magnitude
  carries through, direction is rotated to the exit portal's facing). This is the single most
  load-bearing mechanic to get right; everything else in v1 is scaffolding around it.
- **Explicit v1 non-goals** (kept out to keep the increment small and clearly bounded): no
  co-op/multiplayer portals, no portal gels/light bridges/turrets/companion-cube-style props, no
  portal-through-a-portal chaining beyond the one active pair, no collectible items/upgrades
  (hence low% isn't meaningful yet — see §2), no angled or moving portal surfaces, no in-run
  portal-gun "pickup" progression — the gun is available from the start of every level.

## 5. Achievements + unlock hooks, attract-mode fit, implementation sizing

### Achievements + unlocks
- Per-game `games/riftrunner/achievements.py` follows the existing `meta.achievements.Achievement`
  pattern (id/name/desc/check/progress) exactly like every other game: e.g. `first_finish` (any
  completed any% run), `sub_target` (finish under a level-specific time bar), `no_reset` (finish
  without hitting a hazard tile), and a grind achievement in the same spirit as Solitaire's
  `century`/`millennium` (e.g. `hundred_runs`).
- One **cross-game, category-level** achievement is worth calling out separately since it spans
  games that don't all exist yet: e.g. "set a PB in all three SPEEDRUN games." That can't live in
  a single game's `achievements.py` (no single game's profile section sees the other two), so it
  follows the existing `meta.achievements.evaluate_ambient`-style pattern — a small
  cabinet-level evaluator reading across `profile["riftrunner"]`/`profile["scorch"]`/
  `profile["voxeldash"]` PB records, exactly mirroring how ambient's mood achievements are
  evaluated outside any single game's event stream. Deferred until the third game ships (can't
  unlock a "all three" achievement with one game); the hook point is designed now so it isn't a
  later refactor.
- Cosmetic unlock (e.g. portal-color/trail skins) via the existing `has_skins` /
  `skin_resolver` mechanism already used by other games — no new unlock plumbing.

### Attract-mode fit
`GameInfo.attract=True`, `demo_bot` module following the exact `games/breaker/bot.py` shape — a
small heuristic driver (aim at the goal, place portals when blocked, don't chase optimal
splits). Per the existing attract contract (`main.py`: "attract demos never touch stats or
achievements"), attract runs never touch the PB board, leaderboard, or achievements — they're
demo footage only, same as every other game's attract loop.

### Implementation sizing
See the companion plan doc for the increment-by-increment breakdown. Sized like the
card/tabletop suite's plan: headless-core-first (category engine, then Riftrunner's model),
TDD, one commit per increment, small enough that a future session can pick up any single
increment without re-deriving this doc.

## Non-goals (this round)

- Racer and top-down implementations (roster follow-ups — engine is built to take them, not to
  ship them now).
- Low% (or any category beyond any%) — no collectibles exist yet to make it meaningful.
- Server-side re-simulation verification of submitted replays (v1 trusts CAB-13's signature,
  not an independent re-run).
- Online/co-op anything for Riftrunner (solo speedrunning, like every non-Battleship/non-BOARD
  game here).
- A level editor or external level-authoring tool (in-code `LEVELS` only, matching this repo's
  existing convention).
- Global/worldwide leaderboards UI polish beyond reusing the existing scoreboard/board rendering
  (`server/scoreboard.py`, the in-cabinet leaderboard screen) as-is.

## Open questions (owner sign-off needed before implementation starts)

1. **CAB-13 dependency/sequencing.** This spec assumes CAB-13 lands a reusable
   `sign(replay)`/`verify(replay, sig)` primitive and a key-provisioning story (baked-in cabinet
   secret? server-issued per-cabinet key on first contact?). CAB-13 doesn't appear to exist in
   this codebase yet (no `hmac`/tamper code found). Is CAB-13 landing before or in parallel with
   this work? If Riftrunner ships before CAB-13, the PB board/local flow works unsigned in the
   interim and the signature is bolted on later (Increment 6 in the plan) — confirm that's
   acceptable, or that CAB-13 must land first.
2. **Working titles.** `riftrunner` / `scorch` / `voxeldash` are placeholders picked for this
   doc — the owner may want different names (or to fold this into the existing "Emberlight"
   voxel branding more explicitly).
3. **Rendering style.** This spec recommends 2D `OverlayRenderer` rendering (like
   `breaker`/`serpent`) for the flagship rather than the voxel/GL scene pipeline the FPS games
   use, to keep the increment small. Confirm that's the right call rather than a voxel-rendered
   platformer (bigger scope, more "Emberlight" visual continuity with the FPS games).
4. **Score-inversion encoding** (`TIME_CEILING - time_cs`) is a pragmatic reuse of the existing
   descending-sort leaderboard rather than adding ascending-sort support. Confirm this reads
   clearly enough in the UI (always re-derived to a real time for display) rather than warranting
   a small ascending-sort option on `meta/leaderboard.py` instead.
5. **How aggressive should any% be allowed to get?** Sequence breaks and portal-assisted skips
   are explicitly *allowed* (that's the point of "any% ... any means the sim allows"), but level
   design has to accept that some levels may be trivially skippable once portals interact with
   walls in unintended ways. Confirm that's a feature, not a bug, for v1 — or whether specific
   skip patterns should be walled off level-by-level.
