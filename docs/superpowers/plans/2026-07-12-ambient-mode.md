# Ambient Mode — Implementation Plan

> REQUIRED SUB-SKILL for agentic execution: superpowers:subagent-driven-development or
> executing-plans. Steps use `- [ ]`. Spec: `docs/superpowers/specs/2026-07-12-ambient-mode-design.md`.

**Goal:** A calm generative visual+audio screen for the cabinet — auto on idle (setting-gated,
with a faint "how to get back" hint) or manual (chrome-free) — with editable presets + save
slots, flagship-tied premium unlocks, and mood-themed cabinet achievements.

**Architecture:** New `ambient/` package (preset data + registry, scene renderers, `AmbientMode`
engine). `main.py` gains an `AMBIENT` state, an idle branch on the `idle_screen` setting, a menu
entry + hotkey, and settings rows. `meta/profile.py` stores the `ambient` sub-dict (current /
custom slots / counters). Cross-cutting achievements evaluated at the cabinet level.

**Tech stack:** Python 3.14 stdlib + existing engine (render starfield/`ParticleSystem`/bloom,
`AudioBank`, `OverlayRenderer`, `game/theme.py`). No new deps.

## Global constraints
- Preserve current behavior: `idle_screen` default = `"attract"`.
- Headless-testable core (no GL) in `ambient/preset.py`; scenes/engine/wiring are GL and
  verified live. Manual ambient is chrome-free except an opt-in, dismissible edit panel.
- Commit per increment; message trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## File structure
- Create `ambient/__init__.py`, `ambient/preset.py`, `ambient/scenes.py`, `ambient/mode.py`.
- Modify `main.py`, `meta/profile.py`, `meta/achievements.py`.
- Create `tools/test_ambient.py`.

---

## Increment 1 — headless preset core (this plan details it fully)

### Task 1: `AmbientPreset` + registry + idle routing + achievement predicates + tests

**Files:** Create `ambient/__init__.py`, `ambient/preset.py`, `tools/test_ambient.py`.

**Interfaces produced:**
- `AmbientPreset` dataclass (`id,name,scene,palette,speed,density,sound,dim,premium`) with
  `to_dict()` / `from_dict(d)`.
- `DEFAULTS: list[AmbientPreset]` (embers, starfield, aurora, rain, nebula, fireplace, + premium
  supernova/equalizer/ember_hellscape).
- `available_presets(unlocked: set[str]) -> list[AmbientPreset]` (hides premium until unlocked).
- `custom_presets(ambient_profile: dict) -> list[AmbientPreset]`.
- `idle_target(idle_screen: str) -> str|None` (`"attract"|"ambient"|None`).
- `AMBIENT_ACHIEVEMENTS: list[(id, name, desc, predicate)]`; predicate takes a context dict
  (`session_seconds, idle_entries, since_run_end_s, hour`).

- [ ] **Step 1 — failing test** (`tools/test_ambient.py`): round-trip a preset; `available_presets`
  excludes a premium until its id is in `unlocked`; `idle_target` maps the 3 settings; each
  achievement predicate fires exactly at threshold. Run `.venv/Scripts/python.exe tools/test_ambient.py` → fails (no module).
- [ ] **Step 2 — implement `ambient/preset.py`** (dataclass + DEFAULTS built from `game.theme`
  colors as `[r,g,b]`; registry + `idle_target` + `AMBIENT_ACHIEVEMENTS` predicates as above).
- [ ] **Step 3 — run test → pass.**
- [ ] **Step 4 — commit** `feat(ambient): preset model, registry + unlock gating, idle routing, achievement rules + tests`.

---

## Increment 2 — scenes + engine (GL; verified live)
**Files:** `ambient/scenes.py`, `ambient/mode.py`.
- `scenes.py`: `SCENES = {id: fn}` where `fn(preset, t, renderer)` builds the frame using the
  starfield + a `Batcher` of cubes/particles + bloom; palette-driven. Six scenes: embers
  (rising warm cubes), starfield (drift), aurora (flowing bands), rain (falling streaks),
  nebula (swirl), fireplace (flicker).
- `mode.py`: `AmbientMode(preset)` → `update(dt)`, `draw(renderer)`, `draw_overlay(o,w,h,auto)`
  (faint hint only when `auto`), `start_sound(audio)` / `stop_sound(audio)`.
- Commit `feat(ambient): generative scenes + AmbientMode engine`.

## Increment 3 — cabinet wiring (`main.py`, `meta/profile.py`)
- `AMBIENT` state; `start_ambient(auto)`, `stop_ambient()`, `update_ambient(dt)`; idle branch:
  in the MENU idle block, `t = idle_target(settings["idle_screen"])` → attract / ambient / none.
  Any keydown in `AMBIENT` → `stop_ambient()`. Draw dispatch (3D `mode.draw`, overlay
  `mode.draw_overlay`). `MENU_ITEMS += ["AMBIENT"]`; `menu_choose("AMBIENT")`; a MENU hotkey.
  `SETTINGS_ROWS` += idle_screen / ambient_mode / ambient_sound. `meta/profile.py` defaults:
  `idle_screen="attract"`, `ambient={"current":..., "custom":[], "counters":{...}}`.
- Commit `feat(ambient): cabinet state, idle-screen setting, menu entry + wiring`.

## Increment 4 — customization + save slots
- In-ambient edit panel (manual only): cycle palette/speed/density/sound/dim; **Save as** →
  append to `profile["ambient"]["custom"]` (cap N); update `current`. Dismissible to clean.
- Commit `feat(ambient): live customization + custom save slots`.

## Increment 5 — sound
- `sound` resolution in `AmbientMode`: `silence` → `audio.music(None)`; `music:<pool>` →
  `audio.music(pool)`; `bed:<id>` → a new `"ambient"` pool synthesized via `game/composer` +
  `tools/gen_sound.py`. Honor volume settings. Commit `feat(ambient): soundscapes (silence / pool / beds)`.

## Increment 6 — unlocks + achievements
- Premium preset gating wired to real flagship achievement ids (look them up in each game's
  `ACHIEVEMENTS`); `meta/achievements.py` gains the cabinet-level `AMBIENT_ACHIEVEMENTS` eval
  against `profile["ambient"]["counters"]`, checked on ambient update/exit. Commit
  `feat(ambient): flagship-tied premium unlocks + mood achievements`.

## Self-review
- Spec coverage: idle-screen setting (I1 `idle_target`, I3 wiring), presets+save (I1/I4),
  scenes (I2), sound (I5), unlocks + mood achievements (I1 rules, I6 wiring), chrome-free manual
  + auto hint (I2 `draw_overlay`). Headless core fully testable before any GL (I1).
