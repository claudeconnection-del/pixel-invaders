# Ambient mode — design

Approved 2026-07-12. First sub-project of the post-Battleship initiative (card/tabletop suite +
skin system + ambient mode); ambient is an **independent, cross-cutting track** and does not
depend on the games. A calm generative visual+audio screen, entered automatically on idle or
manually.

## Goal

Turn the cabinet into a first-class *ambient object* when nobody's actively playing: drifting,
customizable calm scenes with optional soundscapes (or silence). Two entries — **automatic**
(idle fade, with a faint "how to get back" hint) and **manual** (super clean, no chrome). Many
tunable modes, premium unlockables tied to flagship (non-multiplayer) achievements, and
achievements that reward a *mood / take-a-break* play style rather than skill.

## Decisions (locked during brainstorming)

1. **Idle behavior is a setting** — `idle_screen`: **Attract / Ambient / Off**. The MENU idle
   timer fades to whichever is chosen (`Off` disables idle drift). Ambient is *also* manually
   enterable. (Chosen over a two-stage idle or making ambient the forced default.)
2. **Modes are editable presets + save slots** — ship curated, hand-tuned modes; each is
   tweakable (palette / speed / density / sound / dim) and saveable to custom profile slots.
   (Chosen over curated-only or a full from-scratch parametric engine.)

## Architecture

### State & entry
- New app state `AMBIENT` in `main.py`, dispatched for update + draw like `ATTRACT`.
- **Auto:** the existing MENU idle hook (`idle_timer >= ATTRACT_IDLE_SECONDS`) branches on the
  `idle_screen` setting → `start_ambient(auto=True)` instead of `start_attract()` (or nothing if
  `Off`). Auto draws a faint dismissible **hint** ("Ambient · press any key to return").
- **Manual:** a top-level `AMBIENT` entry in `MENU_ITEMS` (and a hotkey, e.g. `F2`, from MENU)
  → `start_ambient(auto=False)`. Manual is **chrome-free** — no hint, no HUD.
- **Exit:** any key / tap / pad button → back to MENU (mirrors `stop_attract`, restores menu
  music). An `entered_auto` flag gates whether the hint is drawn.
- Audio starts per the active preset's sound choice on enter; restores menu audio on exit.

### Module layout (`ambient/`)
- `ambient/preset.py` — `AmbientPreset` (a dataclass: `id, name, scene, palette, speed,
  density, sound, dim, premium`), JSON (de)serialization, the `DEFAULTS` list, and a
  **registry** with unlock-gating (`available_presets(profile)` filters out premium presets
  whose unlock achievement isn't earned; `custom_presets(profile)` loads saved slots).
- `ambient/scenes.py` — the generative scene renderers keyed by `scene` id (`embers`,
  `starfield`, `aurora`, `rain`, `nebula`, `fireplace`), each a pure function of
  `(preset, t, renderer)` built on the existing starfield + `ParticleSystem` + bloom. No new
  asset pipeline; palette-driven.
- `ambient/mode.py` — `AmbientMode`: owns the active preset + elapsed time; `update(dt)`,
  `draw(renderer)` (3D scene) + `draw_overlay(o, w, h, auto)` (hint only when `auto`), and the
  sound start/stop. Pure of `main.py` state.

### Presets (editable + save slots)
`AmbientPreset` fields: `scene` (renderer id), `palette` (list of theme colors / named ramp),
`speed` (motion multiplier), `density` (particle count tier), `sound` (`"silence"` |
`"music:<pool>"` | `"bed:<id>"`), `dim` (0–1 darkening), `premium` (None or an unlock
achievement id). Six defaults: **Embers, Starfield, Aurora, Rain, Nebula, Fireplace**. The
customization screen edits the live preset and can **Save as** a custom preset (stored in
`profile["ambient"]["custom"]`, capped at N slots); `profile["ambient"]["current"]` remembers
the last-used.

### Sound
Per-preset: **silence** (always available), an existing **music pool** (`music:game` etc.), or
a calm **ambient bed** (`bed:<id>`) synthesized via the existing `game/composer` +
`tools/gen_sound` path into a new `"ambient"` pool. Honors the `music_vol` / `sfx_vol` settings.
MVP: silence + music-pool reuse + 1–2 generated beds; more beds later.

### Unlockable premium modes
A few presets carry `premium = <achievement_id>`; `available_presets(profile)` hides them until
that achievement is in `profile`'s unlocked set — reusing the existing achievement→unlock
mechanism (`meta/profile` unlocked skins + `skin_for_achievement`), generalized so ambient
presets unlock the same way. Proposed (all **flagship, non-multiplayer**): *Supernova* (Voxel
Hell boss kill), *Equalizer* — audio-reactive (Voxel Studio export), *Ember Hellscape* (Voxel
Doom clear). **None** tied to multiplayer achievements.

### Ambient achievements (cross-cutting, mood-themed)
Ambient isn't a game, so these are **cabinet-level** achievements evaluated against
profile-level counters, not a game run. Add a small cabinet achievements set in
`meta/achievements` checked when `AMBIENT` updates/exits, backed by new counters in
`profile["ambient"]` (`total_seconds`, `idle_entries`, `manual_entries`, `last_run_end_ts`):
- **Deep Breath** — 10 continuous minutes in ambient.
- **Drifted Off** — idled into ambient 25 times (lifetime).
- **Take a Break** — enter ambient within 60 s of finishing a run.
- **Night Owl** — enter ambient after midnight (local time).
The "lazy / barely-made-it" playstyle achievements attach to individual games as they're built
(out of scope here).

## Settings & menu wiring
- `SETTINGS_ROWS` gains: `("Idle screen", "idle_screen", ["attract", "ambient", "off"])`,
  `("Ambient mode", "ambient_mode", <preset ids>)`, `("Ambient sound", "ambient_sound",
  ["preset", "silence"])` (a global override). Defaults added to `meta/profile.py`
  (`idle_screen="attract"` to preserve current behavior; `ambient` sub-dict).
- `MENU_ITEMS` gains `"AMBIENT"`; `menu_choose("AMBIENT")` → `start_ambient(auto=False)`;
  `menu_rows()` shows it unconditionally (no gating flag needed).
- A lightweight in-ambient **customization** affordance (manual mode): a key toggles an edit
  panel (palette/speed/density/sound/dim + Save-as); the panel is the *only* chrome allowed in
  manual mode and is dismissible back to clean.

## Testing (headless)
- **Preset round-trip** — serialize/deserialize an `AmbientPreset` and a saved custom slot;
  equality holds.
- **Unlock gating** — `available_presets(profile)` excludes a premium preset until its
  achievement is in the unlocked set, then includes it.
- **Idle routing** — a pure helper `idle_target(setting)` returns `"attract" | "ambient" |
  None`; assert the three cases (and that the default preserves attract).
- **Ambient achievement rules** — pure predicates over the counters (`total_seconds>=600`,
  `idle_entries>=25`, run-end delta < 60 s, hour < 6) fire exactly at their thresholds.
- Scenes + audio + the live state transitions are verified on the cabinet (GL) by the user.

## Module / file plan
- New `ambient/__init__.py`, `ambient/preset.py`, `ambient/scenes.py`, `ambient/mode.py`.
- Modify `main.py` — `AMBIENT` state; `start_ambient`/`stop_ambient`/`update_ambient`; idle
  branch on `idle_screen`; `MENU_ITEMS` + `menu_choose` + hotkey; draw dispatch; settings rows.
- Modify `meta/profile.py` — default settings keys + `profile["ambient"]` sub-dict (current,
  custom slots, counters).
- Modify `meta/achievements.py` — a cabinet-level ambient achievements set + evaluation hook.
- New `tools/test_ambient.py`.

## Non-goals
- Audio-reactive scenes and a large preset library (a couple premium unlocks only).
- Rich generative ambient audio (start with silence + existing pools + 1–2 beds).
- Clock/weather/extra overlays; multiplayer-linked unlocks (explicitly excluded).
- The card/tabletop games and their skin system (separate sub-projects).

## Sequencing (increments)
1. **Headless core** — `ambient/preset.py` (dataclass, DEFAULTS, (de)serialize, registry +
   unlock gating) + `idle_target` helper + ambient achievement predicates; `tools/test_ambient.py`.
2. **Engine + scenes** — `ambient/mode.py` + `ambient/scenes.py` (the 6 default scenes on
   starfield/particles/bloom).
3. **Cabinet wiring** — `main.py` AMBIENT state, idle branch, menu item + hotkey, draw/update
   dispatch, exit; `meta/profile.py` settings + `ambient` sub-dict.
4. **Customization + save slots** — in-ambient edit panel (manual), Save-as to profile.
5. **Sound** — silence + music-pool reuse + 1–2 generated ambient beds.
6. **Unlocks + achievements** — premium preset gating wired to existing flagship achievements;
   cabinet-level ambient achievements + counters.
