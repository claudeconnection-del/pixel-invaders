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

## Status — 2026-07-14

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

### 🔧 Next — finish the card/tabletop suite (reuse the `games/cards/` kit)
1. **Rummy lay-offs** onto the knocker's melds (CAB-6, deferred from the first Rummy pass).
2. **Poker** — ✅ **Video poker headless core done** (CAB-7): `games/poker/model.py` (+
   `games/poker/__init__.py`) — `evaluate()` hand classifier (royal_flush .. nothing, ace
   high/low incl. the wheel straight), full-pay 9/6 Jacks-or-Better `PAYTABLE` with the
   max-bet (5-coin) royal jackpot (4000, not 250×5), `VideoPoker` (bet/deal/toggle_hold/draw,
   credits ledger), deterministic from the rng. `tools/test_poker.py` green (evaluator
   truth-table, payout math, deal/draw determinism, credits ledger, 10k-hand rng sweep RTP
   smoke-check). **NEXT: cabinet view** `games/poker/game.py` (hold/draw table, register
   TABLETOP, CAB-8), then achievements (CAB-9).
3. **Backgammon** — ✅ **headless core done** (CAB-10): `games/backgammon/model.py`
   (signed `points[24]` + bar/off, pip_count, dice via the run's rng with doubles = four
   moves, `legal_moves`/`apply` honouring bar-first entry, blocking, hitting, exact/overshoot
   bear-off, and the forced-play/higher-die rule, gammon/backgammon grading) + `ai.py` (greedy
   pip-count/hit/made-point/blot-exposure heuristic AI, beats a random-legal-move baseline 96%
   over 200 seeded games in `tools/test_backgammon.py`, well over the 80% bar). No doubling
   cube yet (deferred, like Rummy's lay-offs). **NEXT: cabinet view + board/checker skins +
   TABLETOP registration** (CAB-11) — not wired into `games/__init__.py`/`main.py` yet.

Spec: `docs/superpowers/specs/2026-07-14-card-tabletop-suite-design.md` ·
Plan: `docs/superpowers/plans/2026-07-14-card-tabletop-suite.md`.

### 🗺️ Later (roadmap order)
- **Share/post replays to the leaderboard** — upload a run's replay tied to its high-score entry;
  others watch it in the Replay Theater.
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
