# CLAUDE.md — Cabinet Man

Working notes for AI seats/sessions. **Keep the "Current state" section updated as work lands**
so progress persists across seats. Architecture lives in `README.md`; deploy in `DEPLOY.md`.

## What this is
An Emberlight-themed voxel **arcade cabinet** (renamed from "Pixel Invaders" → **Cabinet Man**;
the *look* stays branded Emberlight). Python 3.14, `pygame-ce` + `PyOpenGL`. One app (`main.py`)
hosts many games + a shared engine (menus, profile/stats/achievements, leaderboards, attract,
replays, render + audio).

## Run & test
```bash
# run the cabinet
.venv/Scripts/python.exe main.py          # Windows (mac/linux: .venv/bin/python)
# headless tests (no GL/window)
.venv/Scripts/python.exe tools/test_companion.py   # secret-local MP: secrecy, session, server, replay
.venv/Scripts/python.exe tools/test_battleship.py  # battleship rules + AI
.venv/Scripts/python.exe tools/test_games.py        # classic game sims
.venv/Scripts/python.exe tools/test_render.py tools/test_meta.py tools/test_world.py
```

## Conventions
- **Adding a game** = one folder `games/<id>/` exposing `INFO` (`arcade.game_api.GameInfo`),
  `create_run(mode, rng)`, `ACHIEVEMENTS`; register it in `games/__init__.py` `CATEGORIES`.
  Implement the `GameRun` duck-type (`update/draw/draw_hud/on_event/drain_events/...`).
- **Render**: voxel 3D via `render.renderer` `Batcher` + `renderer.draw_scene(...)`; 2D HUD via
  the `OverlayRenderer` (`o.text/o.rect/o.image`, logical coords, `UI_H=860`). Palette in
  `game/theme.py` (semantic tokens + per-game `Theme` signatures).
- **Networking is stdlib-only** (`game/netclient.py`, `games/board/companion/`) — no new net deps.
  Client env vars: `CABINET_MAN_SERVER` / `CABINET_MAN_API_KEY` (old `PIXEL_INVADERS_*` still honored);
  server env is `ARCADE_*`.
- **Persistence**: `meta/profile.py` (settings dict, per-game section, lifetime counters, unlocked
  skins), `meta/achievements.py`, `meta/replay.py`. Settings UI = `SETTINGS_ROWS` in `main.py`;
  top menu = `MENU_ITEMS` + `menu_rows()`.
- **Commits**: frequent, conventional-ish messages; end with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Branch off `main` for
  features (don't commit features straight to `main`).

## Workflow (Superpowers)
Features go brainstorm → **spec** (`docs/superpowers/specs/YYYY-MM-DD-*.md`) → **plan**
(`docs/superpowers/plans/YYYY-MM-DD-*.md`) → implement (TDD, frequent commits). Check those dirs
for the latest specs/plans before starting related work.

## Current state (update me!)
- ✅ **Battleship — truly-secret local multiplayer** (companion phones): SHIPPED on branch
  `secret-local-multiplayer` (**not merged to `main`**). Each player's phone is a private
  controller over the LAN, the cabinet is the shared TV. Key code: `games/board/companion/`
  (views/session/server), `games/board/phone/app.html`, `games/battleship/`. Per-perspective
  move-stream replay in `games/board/replay.py`. Spec/plan dated `2026-07-12`. New dep: `segno`
  (QR). Deferred: online turn-match relay, VS-AI/HOTSEAT modes.
- 🔧 **Ambient mode** — IN DESIGN (2026-07-12). Locked decisions: idle-screen is a setting
  (Attract / **Ambient** / Off) + a manual chrome-free entry; modes are **editable presets + save
  slots**. Spec pending under `docs/superpowers/specs/`.
- 🗺️ **Roadmap next** (see also `README.md`): single-player card/tabletop suite (Rummy,
  Backgammon, Poker, Solitaire) + a deck/playmat-felt/board skin system → share-replays-to-
  leaderboard → speedrun category. Ambient mode runs as a parallel track.
