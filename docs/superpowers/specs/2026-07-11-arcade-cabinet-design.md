# Enhanced Edition: arcade cabinet + backend microservice

Approved design (user Q&A), 2026-07-11. Builds on the Voxel Hell overhaul.

## Phase 1 — performance & graphics settings

- Frame pacing: FPS cap setting (60 / 120 / 144 / unlimited) + vsync toggle. The sim is
  dt-based and clamped, so high refresh needs no sim changes; determinism tests keep fixed dt.
- New SETTINGS screen (menu + persisted in profile): fps cap, vsync, fullscreen, bloom
  quality (off/low/full), particle density (low/med/high), CRT filter, music volume, sfx
  volume, FPS counter overlay, server URL display.
- Fullscreen: borderless desktop resolution. Everything already renders into a fixed
  1280x860 scene FBO; the composite pass letterboxes into an aspect-fit viewport, so HUD
  layout never changes. VSync/fullscreen changes recreate the GL context, so the whole
  Renderer is rebuilt (meshes/textures re-uploaded); settings apply live.

## Phase 2 — arcade cabinet content

- **Gamepad**: left stick/d-pad move, any face button fire, shoulder/trigger focus,
  start = pause/confirm. Hot-plug tolerant. Menu navigation included.
- **Endless mode**: procedurally generated waves (mixed enemy rows, pattern params scaled by
  a difficulty curve), boss every 5th wave with scaled HP. Run ends on death only.
- **Campaign loops**: beating the boss emits LOOP_CLEAR (win jingle, bonus, banner), rebuilds
  the authored waves at higher difficulty (faster/denser patterns, boss +50% HP per loop),
  and continues the same run. RUN_END fires on death; summary.win = cleared >= 1 loop.
- **Attract mode**: after 15s idle on the menu, a bot-driven demo game plays with PRESS
  START overlay; any input returns to the menu. Doubles as a kiosk display.
- **Initials entry**: qualifying scores (local top 10 per mode, or online submit) get a
  3-letter A-Z arcade entry screen.
- **Leaderboards**: local top-10 per mode stored in profile; LEADERBOARD screen with
  local/global tabs. Global comes from the backend; screen degrades gracefully offline.
- **Kiosk**: `--kiosk` CLI flag = fullscreen + straight into attract mode.
- **New content**: 7th skin (Chrome, unlocked by clearing loop 2) and new achievements:
  Second Verse (clear loop 2), Deep Space (reach endless wave 10), Cabinet King (place in
  global top 10). Achievements screen grows to fit.

## Phase 3 — backend microservice ("pivot to service-style development")

- `server/` is a self-contained deployable: own requirements, tests, Dockerfile, versioned
  REST API, healthcheck. Game depends on it only via HTTP.
- FastAPI + SQLite (stdlib sqlite3, WAL mode, file in a mounted volume):
  - `POST /api/v1/scores` {name: 3 chars A-Z, mode: campaign|endless, score, wave, loop,
    stats...} — server-side validation and clamping.
  - `GET /api/v1/scores?mode=&limit=` — top scores.
  - `GET /api/v1/daily` — deterministic daily seed (future daily-run mode).
  - `GET /healthz` — for container healthcheck.
  - Optional `X-Api-Key` auth via env var (off by default for LAN use).
- Game-side client: stdlib urllib on a worker thread (never blocks a frame), short
  timeouts, silent offline degradation. Server URL configurable (profile settings,
  PIXEL_INVADERS_SERVER env var override).
- Docker: python:3.13-slim, non-root user, uvicorn, HEALTHCHECK; docker-compose.yml with a
  named volume for the DB. GitHub Actions builds and pushes to GHCR on server/** changes;
  private repo => private package; the Ubuntu box logs in with a PAT and
  `docker compose pull && docker compose up -d`.

## Testing

- Existing suites extended: endless + loop coverage in test_world/test_meta; settings and
  new screens in smoke_test; attract/initials driven headlessly.
- `server/test_server.py`: API tests via FastAPI TestClient (dev-only dependency).
- Manual: 120fps + fullscreen verified on the desktop; container verified with a local
  build + healthcheck + score round-trip before pushing CI.
