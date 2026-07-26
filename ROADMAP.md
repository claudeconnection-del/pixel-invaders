# Cabinet Man — Roadmap & Handoff

Living cross-session status for **Cabinet Man** — an Emberlight-themed voxel **arcade cabinet**
(Python 3.14, `pygame-ce` + `PyOpenGL`; one `main.py` hosts many games + a shared engine).

**This file is the shared handoff for any seat/session (local or cloud).** Keep it updated,
committed, and **pushed** whenever a plan or increment lands, so another session can pick up
exactly where the last left off. (Per-seat scratch notes live in the *gitignored* `CLAUDE.md`;
architecture in `README.md`; deploy in `DEPLOY.md`.)

## Where the work lives
- **Active branch: `secret-local-multiplayer`** — all current work is here, **not merged to
  `main`** (do not merge without the owner's OK). Push this branch after each increment.
- Specs + plans: `docs/superpowers/specs/` and `docs/superpowers/plans/` (dated). Read the latest
  before starting related work.

## Run & test (Windows; mac/linux use `.venv/bin/python`)
```bash
.venv/Scripts/python.exe main.py                  # run the cabinet
.venv/Scripts/python.exe tools/smoke_test.py      # boots the app, drives every screen + game
.venv/Scripts/python.exe tools/test_cards.py      # tabletop: deck / skins / Solitaire rules
.venv/Scripts/python.exe tools/test_rummy.py      # tabletop: Gin Rummy rules + achievements
.venv/Scripts/python.exe tools/test_ambient.py    # ambient presets / idle / mood rules
.venv/Scripts/python.exe tools/test_battleship.py tools/test_companion.py
.venv/Scripts/python.exe tools/test_meta.py tools/test_games.py tools/test_world.py tools/test_render.py
```

## Status — 2026-07-25

### ✅ Done (on this branch)
- **Rename** Pixel Invaders → **Cabinet Man** (Emberlight stays the *look*). Client env vars
  `CABINET_MAN_SERVER` / `CABINET_MAN_API_KEY` (old `PIXEL_INVADERS_*` still honored).
- **Battleship — truly-secret local multiplayer** (companion phones as private controllers, the
  cabinet is the shared TV). `games/battleship/`, `games/board/companion/`, per-perspective replay.
- **Ambient mode** (I1–I6) — calm idle/manual screen. `ambient/` package: idle-screen setting +
  `F2` manual entry; 6 scenes + premium Equalizer; `TAB` live customization + custom save slots;
  silence / music-pool / generated-bed sound; flagship-tied premium unlocks + 4 mood achievements.
  *Feature-complete; pending the owner's live QA.*
- **Card/tabletop suite — Solitaire slice COMPLETE.** Shared `games/cards/` kit (deck model +
  deck/felt skin registries + overlay card render), new **TABLETOP** category, `games/solitaire/`
  (Klondike rules + table + click-to-pick/drop play, **double-click → foundation** from anywhere,
  **auto-complete** prompt that pops in once no tableau card is face-down and cascades the finish,
  `TAB` deck/felt skin picker, grind achievements century/millennium=1000-games/founder +
  cosmetic unlocks). Cosmetics store: `settings["tabletop"]`. **Rich skin library**: 22 decks
  (geometric backs — grid/checker/dots/brick/diamond/cross/pinstripe/frames/emblem — via
  `cards.render` BACK_PATTERNS + `back_bg`; high-contrast light/dark faces) and 25 felts
  (solids incl. high-contrast, gradients, `pattern:` geometric washes carbon/grid/checker/dots,
  and dynamic `scene:` felts). The geometric `lattice` scene is shared with ambient mode (a new
  free "Lattice" preset — 7 free / 3 premium ambient scenes now). This is the solid base for the
  remaining card games.
- **Rummy (Gin) — achievements + grind counters + premium cosmetics (CAB-5).** ✅ 7 achievements
  (`first_hand/first_gin/undercut/game_win/hot_streak/hand_century/shark`) in
  `games/rummy/achievements.py`; lifetime counters `rm_hands/rm_hand_wins/rm_gins/rm_undercuts/
  rm_game_wins/rm_streak/rm_best_streak` wired in `games/rummy/game.py` (seeded on deal, updated
  in `_announce`, redeal paths counted). New premium cosmetics: deck `juniper` (unlocks on
  `first_gin`) + felt `speakeasy` (unlocks on `game_win`). Extracted the shared cosmetic-unlock
  sync out of Solitaire into `games/cards/table.py:sync_unlocks(section, settings, save_cb)`,
  called per-frame by both Solitaire and Rummy (Solitaire's behavior unchanged).
- **Cabinet Man framework + Solitaire reference pilot (CAB-32, Epic E1).** ✅ `arcade/pilot.py`
  (`create_pilot_for(module, run)`, `suppress_for_pilot(run)`); games opt in by exporting
  `create_pilot(run)` from `games/<id>/game.py`. `games/solitaire/pilot.py`: an unorthodox
  speed-solver — always wins a solvable board via the same auto-complete route as `SPACE`,
  makes visible progress otherwise (alternates which end of the tableau it scans, occasional
  legal-but-pointless tableau shuffle for personality), ~90ms cadence seeded from the run's own
  rng (deterministic, no wall-clock randomness); gives up gracefully if truly stuck (v1
  limitation, documented). Cabinet wiring in `main.py`: `F1` summons/hands back while PLAYING
  (banner + pulsing top-right HUD badge); the pilot steps before `run.update()` each frame,
  overriding the human `InputState` when it returns one; **any** real input (key, click, pad,
  or movement) instantly hands back with an "…all yours" toast. Score integrity:
  `run.pilot_touched` flags any run Cabinet Man drove any part of — high-score submission is
  skipped, the local replay is still recorded but marked `"pilot": true`, and achievement
  unlocks are suppressed for that run. Tests in `tools/test_pilot.py`; `tools/smoke_test.py`
  drives a live summon → pilot moves → handback on Solitaire.
- **Cabinet Man pilots — Breaker (CAB-35), Voxel Hell (CAB-33).** ✅ `games/breaker/pilot.py`
  the "uncanny paddle": stands still while the ball is far, computes the exact latest frame it
  can start a single full-speed glide and still intercept (`solve_intercept` folds wall bounces
  via triangle-wave reflection), aims returns with edge-of-paddle english toward the nearer
  surviving brick cluster; clears level 1 with zero deaths on 3 seeds. ✅ `games/voxelhell/pilot.py`
  "never wastes a shot": every target's future position is a closed-form sum-of-sines
  (`enemy_pos_at`/`boss_pos_at` transcribed from the sim), `solve_vertical_intercept` fixed-points
  the straight-up bullet's arrival, and a per-target claim ledger (keyed by `id`, expiring past
  each bullet's predicted arrival) never over-commits more bullets than a target has hp — so
  `shots == hits` holds exactly through the opening waves (verified frame-by-frame, 7 seeds, in
  `tools/test_pilot.py` via the no-settled-miss invariant). Holds fire entirely during the
  spread buff (3 uncontrolled angled bullets would break the invariant); dodges by solving each
  hazard's exact row-crossing (no position sampling) and scanning the field for max clearance
  with hysteresis so it doesn't flap. Known v1 limitation (documented in the module + honestly
  in Jira): a still-flying-in enemy can very rarely drift into a shot's column in dense late
  waves and eat it (~1 shot per several full games) — closing it needs fly-in prediction,
  deferred. Both pilots' closed-form solvers are cross-checked against brute-force steppers.
  Smoke drives a live summon→fire→handback on Voxel Hell (the sim-game pilot path).
- **Cabinet Man pilot — Serpent (CAB-34): "draws odd symbols, never in danger."** ✅
  `games/serpent/pilot.py`. Safety is a hard guarantee via *tail reachability* (the check the
  earlier draft's pure flood-fill was too weak for): after any candidate move it BFS-floods from
  the new head and only allows the move if the head can still reach its own tail through free
  cells — the tail always vacates, so a path to it means the snake can follow its own tail
  forever and never self-trap. Every move (food OR glyph) is gated by this. Priorities: (1)
  **glyph mode** while comfortable — trace a deterministic direction-sequence glyph from a small
  library (box/zig-zag/staircase/comb), each step safety-gated, abandoned the instant it'd be
  unsafe or the board crowds; glyph choice seeded off the run's rng; (2) **food pathing** — BFS
  shortest safe path to the fruit, first step re-validated by the tail check; (3) **stall/endgame**
  — follow the tail (guaranteed-empty next cell), which both survives crowded boards and yields a
  space-filling serpentine, then largest-reachable-area fallback; a genuinely sealed board ends
  the run (on-brand). Tests in `tools/test_pilot.py`: the near-trap safety case (a naively-free
  dead-end that a flood-fill count would accept is rejected), survival to length ≥25 with zero
  deaths before it + glyphs provably interleaved across 5 seeds, determinism. Smoke drives a live
  serpent summon→grow→handback (528 glyph moves in ~20s).
- **Cabinet Man attract star + persona + achievements (CAB-36, Epic E5) — Epic E COMPLETE 🎉.**
  ✅ `arcade/cabinet_man.py` (pure/headless): `attract_star_is_pilot(setting, pilot_gids, cycle)`
  resolves who headlines an idle attract cycle — `replays` (canned demo bot, historical),
  `cabinet_man` (always a live pilot), or `mixed` (alternate, default once ≥2 pilots exist), all
  degrading to canned when no games have opted in; `pick_pilot_gid` rotates through the opted-in
  pilots. Wired into `main.py` `start_attract`/`update_attract`: a starred cycle creates a real
  pilot and drives the throwaway attract run with it (no profile writes — smoke asserts profile
  equality before/after), with a GOLD persona caption ("CABINET MAN is playing — press any
  button"). Persona: deterministic takeover-banner rotation (`takeover_banner(n)` — 4 variants,
  restraint over cringe). Cabinet-level achievements in a new `profile["cabinet_man"]` space
  (mirrors the ambient mood set): `ghost_in_the_machine` (watch a summoned pilot 60+ unbroken
  seconds — tracked via `pilot_watch`) and `tag_team` (take back the controls and then beat your
  *session best* — `session_best` records only your own clean runs, so it's always your doing;
  respects E1's no-pilot-scoring rule). New SETTINGS rows: "Cabinet Man" master on/off (default
  on; F1 + attract-star both honor it) and "Attract star". Tests: attract-star selection +
  banner rotation + achievement predicates + pilot discovery in `tools/test_pilot.py`; smoke
  fields a live `cabinet_man`-starred attract cycle and asserts zero profile writes.
  **Epic E (Cabinet Man Mode) is done end to end: framework + Solitaire/Breaker/Voxel Hell/Serpent
  pilots + attract integration + persona + achievements.**

### 🔧 Next — finish the card/tabletop suite (reuse the `games/cards/` kit)
1. ✅ **Rummy lay-offs onto the knocker's melds (CAB-6).** `apply_layoffs(defender_cards,
   knocker_melds)` in `games/rummy/model.py` — greedy-to-fixpoint: run melds extend at
   either end (chained, e.g. laying off 9H onto 6-7-8H then 10H onto the new run), 3-card
   sets take their 4th card; only ever offered the defender's own loose deadwood (the
   `best_deadwood` leftovers), never called on a gin knock. `_end_hand` recomputes the
   defender's post-layoff deadwood for both the win/undercut comparison and the score,
   and records `result["layoffs"]`. `games/rummy/game.py` `_draw_result` shows a
   "laid off N card(s)" line when present. Tests in `tools/test_rummy.py`: run extension,
   set 4th-card, chained extension, no-layoff-on-gin, an undercut created only by a
   layoff. **Rummy is now feature-complete** (achievements/cosmetics from CAB-5 + this).
2. **Poker** — ✅ **playable** (CAB-7 headless core + CAB-8 table). `games/poker/model.py`:
   `evaluate()` hand classifier (royal_flush .. nothing, ace high/low incl. the wheel
   straight), full-pay 9/6 Jacks-or-Better `PAYTABLE` with the max-bet (5-coin) royal jackpot
   (4000, not 250×5), `VideoPoker` (bet/deal/toggle_hold/draw, credits ledger), deterministic
   from the rng. `games/poker/game.py` (`VideoPokerRun`, TABLETOP category, registered after
   "rummy"): 5-card hand centered, left-side paytable panel highlighting the winning row,
   bet controls (Left/Right, M for max), hold via click or keys 1-5, D deals/draws, R rebuys
   200 credits when tapped out (`vp_credits`/`vp_rebuys` persisted in `section["lifetime"]`);
   reuses `cards/table` felt+picker exactly like rummy. Tests: `tools/test_poker.py` (rules,
   green already), `tools/smoke_test.py` poker block (bet/deal/hold/draw/rebuy live).
   **Achievements done (CAB-9)**: `games/poker/achievements.py` — 6 achievements
   (`first_paid/natural_royal/quads/full_houses_10/vp_hands_500/high_roller`); lifetime
   counters `vp_hands/vp_paid/vp_full_houses/vp_best_credits` wired at deal/draw. New premium
   cosmetics: deck `high_roller` (unlocks on `natural_royal`) + felt `casino_floor` (unlocks
   on `quads`). **Poker is now feature-complete.**
3. **Backgammon** — ✅ **playable** (CAB-10 headless core + CAB-11 table). `games/backgammon/
   model.py` (signed `points[24]` + bar/off, pip_count, dice via the run's rng with doubles =
   four moves, `legal_moves`/`apply` honouring bar-first entry, blocking, hitting, exact/
   overshoot bear-off, and the forced-play/higher-die rule, gammon/backgammon grading) +
   `ai.py` (greedy pip-count/hit/made-point/blot-exposure heuristic AI, beats a random-legal-
   move baseline 96% over 200 seeded games, well over the 80% bar). No doubling cube yet
   (deferred, like Rummy's lay-offs). `games/backgammon/game.py` (`BackgammonRun`, TABLETOP
   category, registered after "poker"): board drawn with `o.rect` only (tapered point strips,
   bar, off trays), felt backdrop reused from `cards/table`; click a highlighted source point
   (or the bar) then a highlighted destination (or an OFF tray) to play one die at a time — the
   view assembles the human's picks against `model.legal_moves()`'s enumerated sequences and
   only calls `model.apply()` once a full sequence is chosen, so it works with the model's
   whole-sequence API without needing its own undo/rollback; U undoes the in-progress turn back
   to the roll. House plays with the same ~0.8s AI beat as Rummy. Tests: `tools/test_backgammon.py`
   (rules, green already), `tools/smoke_test.py` backgammon block (click-driven human turns + AI
   turns, checker-conservation assert). **Board/checker skins + achievements done (CAB-12)**:
   new `BoardSkin` cosmetic category (`games/cards/skins.py`) — 8 boards (6 free incl. Emberlight
   Walnut/Classic Tan/Midnight/High Key/Frost/Garden + 2 premium: Noir Lacquer on `gammon`, Royal
   Marble on `bg_wins_50`), point/checker colors read from `settings["tabletop"]["board"]` /
   `unlocked_boards` (`tabletop_store` + `sync_unlocks` extended). The shared `SkinPicker` is now
   **host-driven**: any run can expose `picker_rows()` to swap in its own cosmetic categories (a
   dict of `kind -> available_*(store)` inside `table.py`, no per-game branching) — Backgammon
   drops the meaningless Deck row and offers Board+Felt instead; card games are unchanged
   (default Deck+Felt). `games/backgammon/achievements.py`: 6 achievements (`bg_first_win/gammon/
   backgammon_win/pip_race/bg_games_100/bg_wins_50`) — `pip_race` (win after trailing 30+ pips)
   reads a live per-run stat (`run_stats()["max_pip_deficit"]`, tracked every frame) rather than
   a lifetime counter; lifetime counters `bg_games/bg_wins/bg_gammons/bg_backgammons` wired at
   game-start/result. **Backgammon — and the whole card/tabletop suite — is now feature-complete.**

**🎉 Card/tabletop suite COMPLETE**: Solitaire, Rummy, Video Poker, and Backgammon are all
playable, achievement-rich, and share one cosmetics system (decks/felts/boards) with a generic,
extensible skin picker. Monopoly remains spec-only per the original design (stretch, deferred).

### 🎨 Tabletop polish (Epic D)
- **Four-color deck accessibility (CAB-18).** ✅ `games/cards/render.py:suit_ink(deck, suit,
  four_color)` — off keeps the deck's own black/red inks; on, ♦→blue and ♣→green (light variants
  auto-picked for dark-faced decks via a `sum(face) < 360` heuristic), ♠/♥ unchanged. `draw_card`
  routes all face ink (rank, corner, pip glyph) through it. Toggle in
  `settings["tabletop"]["four_color"]` (default off, backfilled by `tabletop_store`); the shared
  `SkinPicker` gained a generic boolean "Four-color: On/Off" row (all card games; the preview card
  shows a ♦ so the change is visible). Threaded through solitaire/rummy/poker draw calls. Tests:
  `suit_ink` truth-table (off matches deck inks; on recolors D/C and differs from both; dark decks
  get lighter variants; store backfills) in `tools/test_cards.py`; smoke toggles it live via the picker.
- **Solitaire Vegas scoring mode (CAB-22).** ✅ Third mode `("vegas", "VEGAS")` — classic arcade
  rules: draw-3 with 3 stock passes, −$52 buy-in per deal, +$5 per card home (−$5 taken back off),
  bankroll **cumulative** across deals in `section["lifetime"]["sol_vegas_bank"]` (goes negative,
  that's the fun). `games/solitaire/model.py` gained `pass_limit`/`recycles` (recycle refused past
  the limit — in undo snapshots) and a `vegas_delta` = `5 * cards_home` property (no extra state —
  taking a card off lowers cards_home, so ±$5 falls out naturally). `games/solitaire/game.py`
  applies the buy-in on each deal and banks foundation gains via a per-frame `cards_home` diff
  (covers clicks, autoplay, and undo uniformly; new deals reset the baseline so they never refund);
  HUD shows `BANK $±n` colored by sign + this-deal take + passes used. Two achievements
  (`vegas_in_black` — bank ≥ $0 after 10+ deals; `vegas_deals_50`). Tests: pass-limit refusal,
  delta math incl. take-back, cumulative bank across two deals, achievement predicates
  (`tools/test_cards.py`); smoke runs a live Vegas deal + rematch asserting the bank math.
- **Per-game rules overlay (CAB-24).** ✅ Each tabletop game exports `RULES_TEXT` (objective /
  play / scoring / controls, re-exported from its package `__init__`); `games/cards/table.py`
  gained `draw_rules_overlay()` + a `RulesOverlay` state holder (dim wash + PANEL/GOLD panel,
  arrow-key scroll, styled like the SkinPicker). `H` toggles it in all four games (mutually
  exclusive with the skin picker — opening one closes the other), clicks are swallowed while open,
  and the footer hint gained "H: rules". Tests: every registered TABLETOP module has non-empty
  `RULES_TEXT` with lines under the length cap (`tools/test_cards.py`, iterating the category);
  smoke toggles it live in Solitaire + Rummy.
- **Per-game STATS rows (CAB-21).** ✅ Optional module-level `STATS_ROWS = [(label,
  key_or_callable)]` hook + a pure `arcade.game_api.resolve_stats_rows(rows, life)` resolver
  (key → lifetime value or 0; callable → formatted, e.g. best-time mm:ss, `$bank`). `main.py`'s
  STATS screen uses a game's `STATS_ROWS` when present (else the generic runs/kills block).
  Solitaire (games/wins/streaks/best-time/Vegas bank+deals), Rummy (hands/wins/gins/undercuts/
  games/streak), Poker (hands/paid/full-houses/best-credits/credits/rebuys), Backgammon (games/
  wins/gammons/backgammons) — all re-exported from their package `__init__`. Zero-state friendly
  (`.get`). Tests: resolver + formatters + zero-state in `tools/test_cards.py` and
  `tools/test_rummy.py`; smoke already renders every game's STATS screen.
- **Profile export / import with backup (CAB-27).** ✅ `meta/profile.py`: `export_profile()`
  pretty-dumps to a fixed `cabinet_profile_export.json` beside the profile; `import_profile()`
  parses it and routes through the shared `_from_saved()` merge (factored out of `load()`) so an
  older/minimal export backfills to the current schema — returns None on a missing/corrupt file so
  the caller keeps the current profile; `backup_profile()` copies the live profile to a timestamped
  `profile.backup-*.json` before a swap. `main.py` SETTINGS gained "Export profile" / "Import
  profile" action rows (a new `"action"` choices kind); import confirms on a second press, backs up,
  swaps the live profile, and re-applies cheap settings (audio/quality; display settings need a
  restart). Tests: export→import round-trip, older/minimal backfill, corrupt→None, backup
  (`tools/test_meta.py`); smoke drives the export→import action rows.
- **Leaderboard outbox visibility + manual retry (CAB-28).** ✅ `meta/outbox.py` gained pure
  helpers `pending_count(profile)`, `status_line(pending, available)` ("N scores waiting to sync
  (online/offline) · R: retry now"), and `retry_summary(before, after, available)` — no change to
  the queueing/flush semantics. The HIGH SCORES screen shows the status line when the outbox is
  non-empty; `R` calls the existing `outbox.drain()` and banners the retry summary. Tests: the
  three helpers + queueing-unchanged in `tools/test_meta.py`; smoke queues offline scores and
  drives the R retry.
- **Cabinet-wide achievement completion summary (CAB-26).** ✅ New pure `meta/completion.py`:
  `completion(profile, modules)` rolls achievement progress up across every game module's
  `.ACHIEVEMENTS` plus the two cabinet-level sets (ambient mood, Cabinet Man), returning
  `{"total": (earned,total), "per_game": {gid:(e,t)}, "ambient": (e,4), "cabinet_man": (e,2)}`.
  Read-only (never spawns/mutates profile sections) and earned counts intersect recorded ids with
  each source's own set so stale/unknown ids can't inflate the figure. `completion_line(comp)` →
  "CABINET 12/47 · 26%" (0% when nothing defined, no div-by-zero). Wired into `main.py`'s
  ACHIEVEMENTS screen (header line + slim gold progress bar) and the STATS footer (one cheap line).
  Tests: rollup math / stale-id / zero-state / no-mutation in `tools/test_meta.py`; smoke asserts a
  real unlock moves the total and unknown ids are ignored.
- **Card-table SFX set (CAB-19).** ✅ `tools/gen_sound.py` gained four generated builders —
  `build_card_flip` (filtered-noise snap + pitch-tail), `build_card_place` (low thud + tick),
  `build_card_shuffle` (~14 randomized flips riffling over 0.34s), `build_chip_stack` (2-3 ceramic
  clicks) — all deterministic (fixed seeds) and peak-normalized to sit alongside the existing menu
  set. Registered in `game/assets.py`'s `SFX` volume table and baked to
  `assets/sfx/{card_flip,card_place,card_shuffle,chip_stack}.wav`. Wired into each game's
  `on_event`: Solitaire (draw/undo→flip, move/home→place, deal→shuffle), Gin Rummy
  (draw→flip, discard→place, deal→shuffle), Video Poker (deal→shuffle, hold/no-win draw→flip,
  rebuy/win→chip_stack, alongside the existing win/powerup toast layer). Tests: generation
  determinism/audibility/normalization in `tools/test_meta.py`; smoke stays green through the
  event-driven paths.
- **Card deal/move animations — shared tween layer (CAB-20).** ✅ New `Tweens` helper in
  `games/cards/table.py`: `add(card_key, from_xy, to_xy, dur, now, delay, flip)` queues a flight,
  `pos(card_key, default_xy, now)` returns the eased (out-cubic) render position while one is live
  or `default_xy` otherwise — games keep drawing every card at its logical slot and only the
  render position is diverted, so rules/model/hit-testing never see anything but the final state.
  A flight that hasn't reached its (possibly staggered) start renders at `from_xy`; past its
  duration it expires and is dropped. Caps at `MAX_LIVE=24` concurrent flights (the overflow lands
  instantly) and is a hard no-op under the `particles: low` setting (today's instant behavior,
  unchanged). Wired into **Solitaire**: a staggered ~20ms/card deal cascade (from the stock),
  stock→waste draw slides, tableau/waste/foundation move + auto-home flights (double-click and the
  60ms-cadence auto-complete both queue tweens — the very case `MAX_LIVE` exists for) — hit-testing
  and undo stay entirely on the logical model throughout. Wired into **Gin Rummy**: stock/discard
  draw slides into the regrouped hand fan, a hand→discard-pile slide on discard, and an
  approximate house-fan-center→discard flight when the AI discards (its hand is face-down, so an
  exact seat position would be fiction). Tests: `Tweens` easing/expiry/deferred-start/degrade math
  in `tools/test_cards.py`; per-game integration tests assert real gameplay actions (deal, draw,
  run-move, low-motion) queue the right flights with correct landing coordinates in
  `tools/test_cards.py` and `tools/test_rummy.py`; smoke stays green through solitaire + rummy.

Spec: `docs/superpowers/specs/2026-07-14-card-tabletop-suite-design.md` ·
Plan: `docs/superpowers/plans/2026-07-14-card-tabletop-suite.md`.

### 🗺️ Later (roadmap order)
- ✅ **CAB-14 done** — server: replay upload/fetch endpoints tied to leaderboard entries.
  `server/db.py` gained a `replays` table (blob = zlib + base64 of the CAB-13 signed replay
  dict, stdlib only) plus `score_rank`/`insert_replay`/`list_replays`/`get_replay`/
  `_prune_replays`; `server/app.py` adds `POST /replays`, `GET /replays?game=&mode=`,
  `GET /replays/<id>`. Uploads are HMAC-verified against the shared `ARCADE_API_KEY` (mirrors
  `meta/replay.py`'s canonical-JSON `_canonical_json`/`verify_replay` rather than importing
  it — the Dockerfile only `COPY`s `server/` into the image, so a cross-package import would
  break the running container even though it works fine in the full checkout/tests), capped at
  256 KB canonical JSON, and kept only for entries on/beating the current top-10 per
  `(game, mode)` — `insert_score` now prunes replays that fall off the board on every new
  submission. Score-row matching uses the simpler of the two options the ticket allowed:
  match on `(game, mode, name, score)` rather than round-tripping the score row id, since the
  CAB-13 replay payload carries no player name and scoreboard.py's storage is flat/id-less to
  clients anyway. `server/test_server.py` covers upload→list→fetch, bad signature, oversize,
  retention pruning, api-key requirement, and old-score-submit-path regression — all green.
- **Share/post replays to the leaderboard (client-side)** — the in-game Replay Theater/UI to
  actually call the new endpoints (browse others' uploaded replays, upload your own after a
  run) is still open; CAB-14 only lands the server half.
- **Speedrun category** — Mari0-style portal platformer, a racer, a top-down; replays double as
  speedrun submissions; wants a tamper-resistance mark on replays.
- ✅ **CAB-13 done** — replay HMAC tamper mark: `meta/replay.py` gained `sign_replay`/
  `verify_replay` (stdlib `hmac`/`hashlib`, canonical sorted-key JSON minus `"sig"`),
  `save_last`/`keep` now sign with the cabinet's `CABINET_MAN_API_KEY` (or a per-profile
  `settings["replay_key"]` generated once) when no explicit key is passed, and `load()` returns
  the replay dict with an added `verified` bool — unsigned/old replays still load, just
  unverified (no back-compat break). Canonicalization is stdlib-only so `server/` can reuse it
  later for CAB-14 (server-side re-verification) without a new dependency. Tests in
  `tools/test_meta.py` (`replay_sign_verify_roundtrip`, `replay_tamper_detection`,
  `replay_unsigned_legacy_loads_unverified`, `replay_canonicalization_stable_across_key_order`).
  Spec + plan drafted (CAB-17): `docs/superpowers/specs/2026-07-25-speedrun-category-design.md` ·
  `docs/superpowers/plans/2026-07-25-speedrun-category.md` — flagship is the portal platformer
  (working title "Riftrunner"), any% only for v1, replay-as-submission signed per CAB-13.
  **Awaiting owner approval before implementation starts.**

## Conventions (short)
- **Add a game** = one folder `games/<id>/` exposing `INFO` (`arcade.game_api.GameInfo`),
  `create_run(mode, rng)`, `ACHIEVEMENTS`; register in `games/__init__.py` `CATEGORIES`. Implement
  the `GameRun` duck-type. 2D via the `OverlayRenderer` (`o.text/o.rect/o.image`, `UI_H=860`);
  voxel via `render.renderer` `Batcher` + `renderer.draw_scene`.
- Headless-testable core first (TDD, no GL); GL/scenes/wiring verified live (`python main.py` or a
  hidden-GL capture). Commit per increment; message trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Keep this file current + committed + pushed each increment** — it is the cross-session handoff.
