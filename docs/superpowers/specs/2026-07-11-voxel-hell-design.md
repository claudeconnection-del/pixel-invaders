# Voxel Hell — Pixel Invaders 3D overhaul

Approved design, 2026-07-11. Replaces the classic 2D mode entirely (git history keeps it).

## Core principle

The simulation stays 2D; only presentation goes 3D. Gameplay (positions, bullets,
collisions, graze) runs on a flat 640x720 logical playfield with no GL dependency, so it
remains headlessly testable. The renderer extrudes the same 8x8 pixel-grid art into voxel
models (one cube per pixel) and views the field through a tilted perspective camera.

## Stack

pygame-ce (window/input/audio/timing) + PyOpenGL (GL 3.3 core) + numpy. All art and audio
remain 100% generated from code.

## Rendering

- `game/sprites.py` becomes the single source of truth for pixel grids; both the PNG baker
  (`tools/gen_art.py`) and the voxel mesh builder import from it.
- Voxel meshes: one static VBO per sprite (merged shaded cubes); per-frame instanced draws
  (pos+scale+rotation+color per instance) so hundreds of bullets and thousands of particles
  stay cheap despite PyOpenGL call overhead.
- Tilted "arcade cabinet" perspective camera with subtle drift; directional + rim lighting,
  flat-shaded faces.
- Particles: explosions burst into tumbling voxel cubes with gravity; engine exhaust, bullet
  trails, graze sparks, power-up glitter. CPU sim in numpy, instanced render.
- Post-processing: scene renders to float FBO (emissive colors >1.0) -> bright pass ->
  separable gaussian bloom (half res) -> composite with CRT pass (scanlines, vignette,
  slight barrel distortion) -> chromatic aberration pulse + screen shake on hits.
- HUD/text: pygame font surfaces uploaded as GL textures, drawn in an ortho overlay pass,
  cached by string.
- Starfield: instanced distant cubes drifting for parallax depth.

## Bullet-hell gameplay

- Campaign: 5 escalating waves + 3-phase boss. Wave = choreographed enemy formation that
  flies in, then fires composable patterns from `game/patterns.py` (aimed shots, radial
  bursts, spirals, rotating walls-with-gaps, combinations). Wave clears when all enemies die.
- Focus mode: hold Shift for half speed + hitbox indicator. Player hitbox is a small core
  (radius ~4 logical px), much smaller than the ship sprite. Autofire while Space held.
- Graze: enemy bullets passing within ~18px of the hitbox core without hitting award graze
  points and build a score multiplier (cap x5, decays slowly, resets when hit).
- Power-ups (~12% drop on kill, fall downward): spread shot (10s), rapid fire (10s), shield
  (absorbs one hit, persists until broken). Non-stacking, timers refresh on re-pickup.
- Boss: large multi-grid voxel alien, HP phases at 100/66/33%, phase-specific patterns,
  visible health bar; phase transitions clear bullets + particle burst.
- Death: lose a life, all enemy bullets cleared (mercy), 2s invulnerable respawn, multiplier
  reset. 3 lives; 0 = run over. Simultaneous enemy bullet cap ~400.

## Events

`game/world.py` emits typed events each frame (ENEMY_KILLED, PLAYER_HIT, PLAYER_DEATH,
GRAZE, WAVE_START, WAVE_CLEAR, POWERUP_PICKUP, SHIELD_BREAK, BOSS_SPAWN, BOSS_PHASE,
BOSS_KILLED, SHOT_FIRED, RUN_END, ...). Stats, achievements, toasts, and sfx all consume
events — decoupled and testable.

## Meta layer

- `meta/profile.py`: one local `profile.json` (gitignored), schema-versioned, atomic writes
  (temp + rename). Stores best scores, lifetime stats, unlocked/selected skins, earned
  achievements with timestamps, settings (CRT filter, music on/off). Saved on run end,
  achievement unlock, and quit. Replaces highscore.txt.
- `meta/stats.py`: per-run stats (kills, accuracy, grazes, max multiplier, time) shown on
  run-end screen; lifetime totals on a Stats menu screen.
- `meta/achievements.py`: 12 achievements — First Blood, Warmed Up (wave 1), Halfway There
  (wave 3), Boss Slayer, One Credit Clear, Untouchable (wave without being hit), Graze
  Addict (100 grazes/run), Edge Lord (1000 lifetime grazes), Sharpshooter (>=75% accuracy,
  min 50 shots), Hoarder (5 power-ups/run), Exterminator (1000 lifetime kills), Marathoner
  (1h lifetime play). Toast banner + jingle on unlock; menu screen lists earned/locked with
  progress bars.
- `game/skins.py`: 6 ships, each its own pixel grid + palette (not recolors): Vanguard
  (default), Raider (Warmed Up), Dart (Graze Addict), Gold Ace (Boss Slayer), Ghost
  (Untouchable, translucent), Prismatic (One Credit Clear, hue-cycling tint). Skins menu
  screen with rotating voxel preview and lock hints.

## Audio (all generated, gen_sound.py)

New sfx: graze tick, power-up pickup, shield break, boss roar, phase sting, big boss
explosion. Plus generated looping chiptune music: driving gameplay loop and a calmer menu
loop (square-wave melody/bass + noise percussion, mixed by summing channels).

## Shell

`main.py` state machine: MENU / SKINS / ACHIEVEMENTS / STATS / PLAYING / RUN_END.
Arrow+Enter navigation, Esc back/quit. Menu renders 3D background (starfield + rotating
voxel model) under text overlay.

## Code layout

```
game/    sprites.py, skins.py, events.py, entities.py, patterns.py, waves.py, world.py
meta/    profile.py, stats.py, achievements.py
render/  gl.py, voxel.py, particles.py, post.py, text.py
main.py  state machine + wiring
tools/   gen_art.py (PNG baking from sprites.py), gen_sound.py, smoke_test.py
```

## Verification

- Headless world sim (no GL): drive full campaign including boss via scripted input;
  assert wave progression, achievement unlocks, stats accumulation, profile round-trip.
- GL verification: offscreen render + glReadPixels screenshots reviewed visually.
- Manual playtest before push; README updated with new screenshot, controls, features.

## Dependencies added

numpy (cp314 wheel verified), PyOpenGL (pure Python). requirements.txt updated.
