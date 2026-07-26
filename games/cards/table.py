"""Shared table plumbing for the tabletop games (Solitaire, Rummy, ...): the
felt backdrop (solid / gradient / geometric pattern / living ambient-scene) and
the TAB deck+felt skin picker. Games compose these instead of duplicating them.

A "host" for the picker is any run exposing `deck`, `felt`, `settings`,
`save_cb`, and `_set_felt(felt)`.
"""
import pygame

from game.theme import TEXT, DIM, EMBER, GOLD, PANEL
from render.renderer import Batcher
from ambient import scenes as ambient_scenes
from ambient.preset import AmbientPreset
from games.cards import render as card_render
from games.cards import skins
from games.cards.deck import Card


class Tweens:
    """Short flight animations for card moves (CAB-20): games keep drawing
    every card at its LOGICAL slot but ask this layer for the render
    position while a flight is live. Rules/model/hit-testing always operate
    on the logical position — a flight is a visual overlay only, so input
    during a live 150ms flight simply lands on the already-current state.

    `card_key` identifies one physical card (games use (rank, suit)) so a
    flight tracks correctly even if the same logical slot is redrawn with a
    different card next frame.
    """
    MAX_LIVE = 24

    def __init__(self):
        self._live = {}  # card_key -> [from_xy, to_xy, start_t, dur, flip]

    def __len__(self):
        return len(self._live)

    def add(self, card_key, from_xy, to_xy, dur=0.15, flip=False, now=0.0,
           delay=0.0):
        """Queue a flight from `from_xy` to `to_xy` starting at `now + delay`
        (deal cascades stagger many cards this way). `dur <= 0` (the
        low-motion settings path) is a no-op — the card then renders at its
        logical position every frame, exactly like before this feature."""
        if dur <= 0:
            return
        if card_key not in self._live and len(self._live) >= self.MAX_LIVE:
            return  # too many in flight at once: this one lands instantly
        self._live[card_key] = [from_xy, to_xy, now + delay, dur, flip]

    def flipping(self, card_key):
        tw = self._live.get(card_key)
        return tw is not None and tw[4]

    def pos(self, card_key, default_xy, now):
        """The render position for `card_key` this frame: `default_xy`
        (the logical slot) unless a flight is live, in which case an
        out-cubic eased point along it — front-loaded motion that settles
        gently, matching the rest of the cabinet's UI easing."""
        tw = self._live.get(card_key)
        if tw is None:
            return default_xy
        from_xy, to_xy, start_t, dur, _flip = tw
        if now < start_t:
            return from_xy
        frac = (now - start_t) / dur
        if frac >= 1.0:
            del self._live[card_key]
            return default_xy
        eased = 1 - (1 - frac) ** 3
        fx, fy = from_xy
        tx, ty = to_xy
        return (fx + (tx - fx) * eased, fy + (ty - fy) * eased)


class PadCursor:
    """Shared pad-driven cursor for the tabletop games (CAB-23): couch play
    without a mouse. `host` supplies `pad_targets() -> [(target_id, x, y, w,
    h)]` each frame — its logical hit targets, the same source of truth its
    own mouse hit-testing already uses. D-pad/stick `step(direction)` moves
    to the nearest target strictly in that halfplane from the current one
    (no wraparound: at an edge, the far side just doesn't step); `confirm()`
    dispatches the host's own `_click` at the target's center, so a pad
    press and a mouse click land identically; `clear()` clears the host's
    current selection (`sel = None`, matching Solitaire/Rummy's own
    board-state shape). Any mouse motion calls `hide()` (mirrors menu focus:
    the two input methods never fight over the same frame)."""

    def __init__(self, host):
        self.host = host
        self.target_id = None
        self.visible = False

    def show_for(self, target_id):
        self.target_id = target_id
        self.visible = True

    def hide(self):
        self.visible = False

    def _current(self, targets):
        if self.target_id is not None:
            for t in targets:
                if t[0] == self.target_id:
                    return t
        return targets[0] if targets else None

    def step(self, direction):
        targets = self.host.pad_targets()
        if not targets:
            return
        cur = self._current(targets)
        if cur is None:
            return
        if cur[0] != self.target_id:
            self.show_for(cur[0])   # first step: land on the default target
            return
        _, cx, cy, cw, ch = cur
        ccx, ccy = cx + cw / 2, cy + ch / 2
        ux, uy = {"left": (-1, 0), "right": (1, 0),
                 "up": (0, -1), "down": (0, 1)}[direction]
        best, best_dist = None, None
        for tid, x, y, w, h in targets:
            if tid == cur[0]:
                continue
            tcx, tcy = x + w / 2, y + h / 2
            ddx, ddy = tcx - ccx, tcy - ccy
            if ux and ddx * ux <= 0:
                continue
            if uy and ddy * uy <= 0:
                continue
            dist = ddx * ddx + ddy * ddy
            if best_dist is None or dist < best_dist:
                best, best_dist = tid, dist
        if best is not None:
            self.target_id = best
        self.visible = True

    def confirm(self):
        targets = self.host.pad_targets()
        cur = self._current(targets)
        if cur is None:
            return
        _, x, y, w, h = cur
        self.host._click(x + w / 2, y + h / 2)

    def clear(self):
        self.host.sel = None

    def draw(self, o):
        if not self.visible:
            return
        cur = self._current(self.host.pad_targets())
        if cur is None:
            return
        _, x, y, w, h = cur
        card_render.hover_outline(o, x, y, w, h)


def tabletop_store(settings):
    """The shared cosmetics store settings['tabletop'], defaults backfilled."""
    tt = settings.setdefault("tabletop", {}) if settings is not None else {}
    tt.setdefault("deck", "classic")
    tt.setdefault("felt", "emberlight")
    tt.setdefault("board", "emberlight_walnut")
    tt.setdefault("four_color", False)     # accessibility: 4-color suit inks
    tt.setdefault("unlocked_decks", [])
    tt.setdefault("unlocked_felts", [])
    tt.setdefault("unlocked_boards", [])
    return tt


def make_felt_preset(felt):
    return AmbientPreset("felt", "felt", felt.scene or "nebula",
                         [list(c) for c in felt.colors], speed=0.5, density="medium")


def available_decks(store):
    return skins.available_decks(set(store.get("unlocked_decks", [])))


def available_felts(store):
    return skins.available_felts(set(store.get("unlocked_felts", [])))


def available_boards(store):
    return skins.available_boards(set(store.get("unlocked_boards", [])))


def sync_unlocks(section, settings, save_cb):
    """Mirror any earned cosmetic-unlock achievements (a game's
    section["achievements"]) into the shared tabletop store so the tied
    premium deck/felt/board becomes selectable. Shared by every tabletop game
    so unlocks earned in one game (e.g. Rummy's `first_gin`) show up as soon
    as any tabletop game's `settings["tabletop"]` is consulted."""
    if section is None or settings is None:
        return
    tt = tabletop_store(settings)
    got = set(section.get("achievements", {}).keys())
    changed = False
    for d in skins.DECKS:
        if d.premium in got and d.id not in tt["unlocked_decks"]:
            tt["unlocked_decks"].append(d.id)
            changed = True
    for f in skins.FELTS:
        if f.premium in got and f.id not in tt["unlocked_felts"]:
            tt["unlocked_felts"].append(f.id)
            changed = True
    for b in skins.BOARDS:
        if b.premium in got and b.id not in tt["unlocked_boards"]:
            tt["unlocked_boards"].append(b.id)
            changed = True
    if changed:
        save_cb()


# ------------------------------------------------------------- felt drawing
def draw_felt_backdrop(renderer, felt, felt_preset, t):
    """3D pass: a living ambient-scene felt, or an empty backdrop otherwise."""
    b = Batcher()
    if felt.scene:
        fn = ambient_scenes.SCENES.get(felt.scene)
        if fn:
            fn(felt_preset, t, renderer, b)
        renderer.draw_scene(b, walls=False,
                            stars=ambient_scenes.SCENE_STARS.get(felt.scene, True))
    else:
        renderer.draw_scene(b, walls=False, stars=False)


def draw_felt_wash(o, W, H, felt):
    """Overlay pass: solid / gradient / geometric-pattern wash. Scene felts get
    a gentle darken so cards keep contrast."""
    if felt.scene:
        o.rect(0, 0, W, H, (8, 8, 12, 70))
        return
    if felt.pattern:
        _draw_pattern(o, W, H, felt.colors, felt.pattern)
        return
    cols = felt.colors
    if felt.kind == "solid" or len(cols) < 2:
        c = cols[0]
        o.rect(0, 0, W, H, (c[0], c[1], c[2], 255))
        return
    top, bot, n = cols[0], cols[-1], 24
    for k in range(n):
        f = k / (n - 1)
        c = (int(top[0] + (bot[0] - top[0]) * f),
             int(top[1] + (bot[1] - top[1]) * f),
             int(top[2] + (bot[2] - top[2]) * f), 255)
        o.rect(0, H * k / n, W + 2, H / n + 1, c)


def _draw_pattern(o, W, H, cols, pat):
    base = cols[0]
    fg = cols[1] if len(cols) > 1 else base
    o.rect(0, 0, W, H, (base[0], base[1], base[2], 255))
    strong = (fg[0], fg[1], fg[2], 120)
    faint = (fg[0], fg[1], fg[2], 70)
    Wi, Hi = int(W), int(H)
    if pat == "grid":
        for x in range(0, Wi + 64, 64):
            o.rect(x, 0, 2, H, strong)
        for y in range(0, Hi + 64, 64):
            o.rect(0, y, W, 2, strong)
    elif pat == "carbon":
        for x in range(0, Wi + 26, 26):
            o.rect(x, 0, 1, H, faint)
        for y in range(0, Hi + 26, 26):
            o.rect(0, y, W, 1, faint)
    elif pat == "checker":
        step = 74
        wash = (fg[0], fg[1], fg[2], 55)
        for j in range(Hi // step + 2):
            for i in range(Wi // step + 2):
                if (i + j) % 2 == 0:
                    o.rect(i * step, j * step, step, step, wash)
    elif pat == "dots":
        step = 66
        for y in range(step // 2, Hi + step, step):
            for x in range(step // 2, Wi + step, step):
                o.rect(x - 3, y - 3, 6, 6, strong)


# ------------------------------------------------------------- rules overlay
def draw_rules_overlay(o, W, H, title, lines, scroll=0):
    """A centered rules/help panel (dim wash + PANEL card with a GOLD accent
    bar), styled like the SkinPicker. `scroll` is the first visible line index
    when the text is taller than the panel. Returns the max scroll so the
    caller can clamp arrow-key paging."""
    o.rect(0, 0, W, H, (8, 6, 4, 190))
    pw = min(W - 120, 620)
    line_h = 24
    max_visible = 16
    visible = min(len(lines), max_visible)
    ph = 70 + visible * line_h + 30
    px = (W - pw) / 2
    py = (H - ph) / 2
    o.rect(px, py, pw, ph, PANEL)
    o.rect(px, py, 4, ph, GOLD)
    o.text(title, px + 24, py + 18, size=22, color=EMBER)
    max_scroll = max(0, len(lines) - max_visible)
    scroll = max(0, min(scroll, max_scroll))
    for i in range(visible):
        line = lines[scroll + i]
        y = py + 54 + i * line_h
        o.text(line, px + 24, y, size=15, color=TEXT if line else DIM)
    hint = "H or Tab: close"
    if max_scroll:
        hint = "Up/Down: scroll   " + hint
    o.text(hint, px + 24, py + ph - 24, size=13, color=DIM)
    return max_scroll


class RulesOverlay:
    """Small state holder for the H-key rules overlay, shared across tabletop
    games. `host` must expose `RULES_TEXT`-style `rules_lines()` + `rules_title`."""

    def __init__(self, host):
        self.host = host
        self.open = False
        self.scroll = 0
        self._max_scroll = 0

    def toggle(self):
        self.open = not self.open
        self.scroll = 0

    def handle_key(self, key):
        if key in (pygame.K_h, pygame.K_TAB):
            self.open = False
        elif key in (pygame.K_UP, pygame.K_w):
            self.scroll = max(0, self.scroll - 1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.scroll = min(self._max_scroll, self.scroll + 1)

    def draw(self, o, W, H):
        self._max_scroll = draw_rules_overlay(
            o, W, H, self.host.rules_title, self.host.rules_lines(), self.scroll)


# ------------------------------------------------------------- skin picker
# kind -> (attribute name on the host == kind, available_*(store) lookup,
# whether setting it needs the host's special setter instead of plain assign)
_KIND_LOOKUP = {
    "deck": available_decks,
    "felt": available_felts,
    "board": available_boards,
}
_DEFAULT_ROWS = (("Deck", "deck"), ("Felt", "felt"), ("Four-color", "four_color"))


class SkinPicker:
    """The TAB cosmetics picker, shared across tabletop games. Operates on a
    `host` run exposing `settings`, `save_cb`, one attribute per row kind
    (`deck`/`felt`/`board`), and `_set_felt(felt)` for the felt kind (a plain
    attribute for the others). Hosts customize which rows they offer via an
    optional `picker_rows() -> [(label, kind), ...]` (default Deck/Felt) —
    e.g. Backgammon drops Deck and adds Board — so this stays generic across
    cosmetic *kinds* with no per-game branching."""

    def __init__(self, host):
        self.host = host
        self.open = False
        self.row = 0

    def rows(self):
        get_rows = getattr(self.host, "picker_rows", None)
        return get_rows() if get_rows is not None else _DEFAULT_ROWS

    def toggle(self):
        self.open = not self.open
        self.row = 0

    def handle_key(self, key):
        n = len(self.rows())
        if key == pygame.K_TAB:            # Esc is the cabinet's pause key
            self.open = False
        elif key in (pygame.K_UP, pygame.K_w):
            self.row = (self.row - 1) % n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.row = (self.row + 1) % n
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._cycle(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._cycle(1)

    def _cycle(self, direction):
        h = self.host
        store = tabletop_store(h.settings)
        _, kind = self.rows()[self.row]
        if kind == "four_color":               # boolean accessibility toggle
            store["four_color"] = not store.get("four_color", False)
            h.four_color = store["four_color"]
            h.save_cb()
            return
        opts = _KIND_LOOKUP[kind](store)
        cur = getattr(h, kind)
        i = next((k for k, opt in enumerate(opts) if opt.id == cur.id), 0)
        new = opts[(i + direction) % len(opts)]
        if kind == "felt":
            h._set_felt(new)
        else:
            setattr(h, kind, new)
        store[kind] = new.id
        h.save_cb()

    def draw(self, o):
        h = self.host
        rows = self.rows()
        x, y0 = 90, 220
        ph = 44 + len(rows) * 42 + 84
        o.rect(x - 26, y0 - 44, 480, ph, PANEL)
        o.rect(x - 26, y0 - 44, 4, ph, GOLD)
        o.text("TABLE SKINS", x, y0 - 26, size=20, color=EMBER)
        four_color = tabletop_store(h.settings).get("four_color", False)
        for i, (label, kind) in enumerate(rows):
            yy = y0 + 18 + i * 42
            sel = i == self.row
            if kind == "four_color":
                val = "On" if four_color else "Off"
            else:
                val = getattr(h, kind).name
            o.text(("> " if sel else "  ") + label, x, yy, size=18,
                   color=TEXT if sel else DIM)
            o.text(f"< {val} >" if sel else val, x + 150, yy, size=18,
                   color=GOLD if sel else DIM)
        preview_y = y0 + 18 + len(rows) * 42
        if any(kind == "deck" for _, kind in rows):
            # preview a diamond so the four-color toggle is visible at a glance
            card_render.draw_card(o, x + 300, preview_y, 66, 92, Card(1, "D"), h.deck,
                                  four_color=four_color)
            card_render.draw_card(o, x + 372, preview_y, 66, 92, None, h.deck,
                                  face_up=False)
        o.text("Up/Down: pick   Left/Right: change   Tab: close",
               x, preview_y + 84, size=13, color=DIM)
