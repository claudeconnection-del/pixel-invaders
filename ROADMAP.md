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
  cosmetic unlocks). Cosmetics store: `settings["tabletop"]`. **Rich skin library**: 21 decks
  (geometric backs — grid/checker/dots/brick/diamond/cross/pinstripe/frames/emblem — via
  `cards.render` BACK_PATTERNS + `back_bg`; high-contrast light/dark faces) and 24 felts
  (solids incl. high-contrast, gradients, `pattern:` geometric washes carbon/grid/checker/dots,
  and dynamic `scene:` felts). The geometric `lattice` scene is shared with ambient mode (a new
  free "Lattice" preset — 7 free / 3 premium ambient scenes now). This is the solid base for the
  remaining card games.

### 🔧 Next — finish the card/tabletop suite (reuse the `games/cards/` kit)
1. **Rummy (Gin)** — 🔧 headless core DONE: `games/rummy/model.py` (deal/draw/discard/knock,
   `best_deadwood` meld engine, gin/undercut scoring) + `games/rummy/ai.py` (fair heuristic) +
   `tools/test_rummy.py` (green: meld engine, scoring, AI-vs-AI to completion). **NEXT: the
   cabinet view** — `games/rummy/game.py` (INFO, GinRummyRun, hand render via `cards/render`, AI
   opponent, knock UI), register in TABLETOP; then achievements. (Lay-offs onto the knocker's
   melds were deferred — noted in model.py.)
2. **Poker** — 5-card **video poker** (hold/draw + payouts) first; heads-up vs-AI optional later.
3. **Backgammon** — 24 points + dice, pip-count greedy AI; adds **board/checker skins**.

Spec: `docs/superpowers/specs/2026-07-14-card-tabletop-suite-design.md` ·
Plan: `docs/superpowers/plans/2026-07-14-card-tabletop-suite.md`.

### 🗺️ Later (roadmap order)
- **Share/post replays to the leaderboard** — upload a run's replay tied to its high-score entry;
  others watch it in the Replay Theater.
- **Speedrun category** — Mari0-style portal platformer, a racer, a top-down; replays double as
  speedrun submissions; wants a tamper-resistance mark on replays.

## Conventions (short)
- **Add a game** = one folder `games/<id>/` exposing `INFO` (`arcade.game_api.GameInfo`),
  `create_run(mode, rng)`, `ACHIEVEMENTS`; register in `games/__init__.py` `CATEGORIES`. Implement
  the `GameRun` duck-type. 2D via the `OverlayRenderer` (`o.text/o.rect/o.image`, `UI_H=860`);
  voxel via `render.renderer` `Batcher` + `renderer.draw_scene`.
- Headless-testable core first (TDD, no GL); GL/scenes/wiring verified live (`python main.py` or a
  hidden-GL capture). Commit per increment; message trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Keep this file current + committed + pushed each increment** — it is the cross-session handoff.
