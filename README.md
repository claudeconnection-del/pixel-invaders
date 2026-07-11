# Pixel Invaders

A small 8-bit-style Space Invaders clone, built with [pygame](https://www.pygame.org/) as a
demo/experiment. Fully self-contained: all pixel-art sprites and chiptune sound effects are
generated from code (no downloaded assets), and the baked output is committed to the repo so
the game runs standalone.

![gameplay](docs/screenshot.png)

## Play

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

(On macOS/Linux: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python main.py`)

**Controls**

| Key              | Action        |
|------------------|---------------|
| Left/Right, A/D  | Move          |
| Space            | Shoot         |
| Enter            | Start/restart |
| Esc              | Quit          |

Clear all the descending aliens to win, or lose all 3 lives (or let the formation reach your
ship) for game over. High score persists locally to `highscore.txt` (not committed).

## How it's built

- `main.py` — game loop and state machine (menu / playing / game over / win)
- `game/entities.py` — `Player`, `Enemy`, `Bullet`, `Barrier`, `Explosion`
- `game/assets.py` — loads the baked sprites/sound effects
- `tools/gen_art.py` — bakes every sprite PNG under `assets/images/` from small pixel-grid
  definitions, using `pygame.Surface` + `pygame.image.save` (no image library needed)
- `tools/gen_sound.py` — synthesizes every chiptune sound effect under `assets/sfx/` using only
  the stdlib (`wave`, `struct`, `math`) — square waves and a small xorshift noise generator for
  explosions, no audio library needed
- `tools/smoke_test.py` — headless sanity check (`SDL_VIDEODRIVER=dummy`) that runs a simulated
  play session to catch import/runtime errors before committing

Regenerate assets after tweaking a sprite or sound definition:

```powershell
.venv\Scripts\python tools\gen_art.py
.venv\Scripts\python tools\gen_sound.py
```

This is a demo/experiment repo, not a production project.
