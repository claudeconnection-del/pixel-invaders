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


def tabletop_store(settings):
    """The shared cosmetics store settings['tabletop'], defaults backfilled."""
    tt = settings.setdefault("tabletop", {}) if settings is not None else {}
    tt.setdefault("deck", "classic")
    tt.setdefault("felt", "emberlight")
    tt.setdefault("board", "emberlight_walnut")
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


# ------------------------------------------------------------- skin picker
# kind -> (attribute name on the host == kind, available_*(store) lookup,
# whether setting it needs the host's special setter instead of plain assign)
_KIND_LOOKUP = {
    "deck": available_decks,
    "felt": available_felts,
    "board": available_boards,
}
_DEFAULT_ROWS = (("Deck", "deck"), ("Felt", "felt"))


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
        for i, (label, kind) in enumerate(rows):
            yy = y0 + 18 + i * 42
            sel = i == self.row
            val = getattr(h, kind).name
            o.text(("> " if sel else "  ") + label, x, yy, size=18,
                   color=TEXT if sel else DIM)
            o.text(f"< {val} >" if sel else val, x + 150, yy, size=18,
                   color=GOLD if sel else DIM)
        preview_y = y0 + 18 + len(rows) * 42
        if any(kind == "deck" for _, kind in rows):
            card_render.draw_card(o, x + 300, preview_y, 66, 92, Card(1, "S"), h.deck)
            card_render.draw_card(o, x + 372, preview_y, 66, 92, None, h.deck,
                                  face_up=False)
        o.text("Up/Down: pick   Left/Right: change   Tab: close",
               x, preview_y + 84, size=13, color=DIM)
