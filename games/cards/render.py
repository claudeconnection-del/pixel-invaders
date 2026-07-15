"""Overlay drawing for cards + felts. 2D only (uses OverlayRenderer o.rect /
o.text), so it runs post-CRT and stays crisp. A card is drawn procedurally
(edge + face + rank/suit ink) and its BACK is a geometric pattern selected by
`skin.back` — themed by the DeckSkin's colours. Felts are drawn by the game
(solid / gradient / geometric pattern wash, or an ambient-scene backdrop).

Suits show as letters (S/H/D/C) coloured by suit — the overlay font is an ASCII
atlas, so letters are safe where suit glyphs might not render.
"""
_EDGE = (16, 12, 10, 255)
_SEL = (255, 210, 90, 255)
_HOVER = (255, 236, 170, 130)


def _rgba(c, a=255):
    return (c[0], c[1], c[2], a)


def _darken(c, k):
    return (int(c[0] * k), int(c[1] * k), int(c[2] * k))


def draw_card(o, x, y, w, h, card, skin, face_up=True, selected=False):
    """Draw one card at (x, y). `card` may be None for a face-down slot."""
    o.rect(x, y, w, h, _EDGE)                          # edge / drop shadow
    if not face_up:
        _draw_back(o, x, y, w, h, skin)
        if selected:
            _outline(o, x, y, w, h, _SEL)
        return
    o.rect(x + 2, y + 2, w - 4, h - 4, _rgba(skin.face))
    ink = _rgba(skin.ink_red if card.red else skin.ink_black)
    o.text(card.rank_label, x + 8, y + 5, size=int(h * 0.18), color=ink)
    o.text(card.suit, x + 9, y + 5 + int(h * 0.2), size=int(h * 0.14), color=ink)
    o.text(card.suit, x + w / 2, y + h * 0.36, size=int(h * 0.32),
           color=_rgba(skin.ink_red if card.red else skin.ink_black, 210),
           center=True)
    _outline(o, x + 2, y + 2, w - 4, h - 4, _rgba(skin.trim, 120), t=2)
    if selected:
        _outline(o, x, y, w, h, _SEL)


# ------------------------------------------------------------- card backs
def _draw_back(o, x, y, w, h, skin):
    bg = tuple(skin.back_bg) if getattr(skin, "back_bg", None) else _darken(skin.trim, 0.4)
    fg = tuple(skin.trim)
    o.rect(x + 2, y + 2, w - 4, h - 4, _rgba(bg))
    ix, iy, iw, ih = x + 7, y + 7, w - 14, h - 14
    _BACKS.get(skin.back, _back_frames)(o, ix, iy, iw, ih, fg)
    _outline(o, x + 2, y + 2, w - 4, h - 4, _rgba(fg, 200), t=2)


def _back_solid(o, x, y, w, h, fg):
    _outline(o, x, y, w, h, _rgba(fg, 150), t=2)


def _back_grid(o, x, y, w, h, fg):
    cols, rows = 4, 6
    for i in range(cols + 1):
        o.rect(x + i * w / cols - 1, y, 2, h, _rgba(fg, 150))
    for j in range(rows + 1):
        o.rect(x, y + j * h / rows - 1, w, 2, _rgba(fg, 150))


def _back_checker(o, x, y, w, h, fg):
    cols, rows = 4, 6
    cw, ch = w / cols, h / rows
    for j in range(rows):
        for i in range(cols):
            if (i + j) % 2 == 0:
                o.rect(x + i * cw, y + j * ch, cw + 1, ch + 1, _rgba(fg, 120))


def _back_stripes(o, x, y, w, h, fg):
    n = 6
    for i in range(n):
        o.rect(x + (i + 0.25) * w / n, y, w / n * 0.5, h, _rgba(fg, 130))


def _back_bars(o, x, y, w, h, fg):
    n = 7
    for j in range(n):
        o.rect(x, y + (j + 0.22) * h / n, w, h / n * 0.5, _rgba(fg, 130))


def _back_frames(o, x, y, w, h, fg):
    for k in range(4):
        m = k * 7
        if w - 2 * m > 6 and h - 2 * m > 6:
            _outline(o, x + m, y + m, w - 2 * m, h - 2 * m, _rgba(fg, 165 - k * 22), t=2)


def _back_dots(o, x, y, w, h, fg):
    cols, rows = 4, 6
    for j in range(rows):
        for i in range(cols):
            cx = x + (i + 0.5) * w / cols
            cy = y + (j + 0.5) * h / rows
            o.rect(cx - 3, cy - 3, 6, 6, _rgba(fg, 150))


def _back_cross(o, x, y, w, h, fg):
    o.rect(x + w / 2 - 3, y, 6, h, _rgba(fg, 150))
    o.rect(x, y + h / 2 - 3, w, 6, _rgba(fg, 150))
    _outline(o, x, y, w, h, _rgba(fg, 120), t=2)


def _back_brick(o, x, y, w, h, fg):
    rows = 6
    rh = h / rows
    for j in range(rows):
        o.rect(x, y + j * rh, w, 2, _rgba(fg, 120))
        for i in range(3):
            sx = x + i * w / 3 + (w / 6 if j % 2 else 0)
            o.rect(min(sx, x + w - 2), y + j * rh, 2, rh, _rgba(fg, 120))


def _back_diamond(o, x, y, w, h, fg):
    cx, cy = x + w / 2, y + h / 2
    base = min(w, h)
    for k, frac in enumerate((0.44, 0.30, 0.16)):
        s = base * frac
        _outline(o, cx - s / 2, cy - s / 2, s, s, _rgba(fg, 175 - k * 34), t=2)


def _back_emblem(o, x, y, w, h, fg):
    _outline(o, x, y, w, h, _rgba(fg, 150), t=2)
    cx, cy = x + w / 2, y + h / 2
    _outline(o, cx - 15, cy - 22, 30, 44, _rgba(fg, 150), t=2)
    o.rect(cx - 4, cy - 4, 8, 8, _rgba(fg, 190))


def _back_pinstripe(o, x, y, w, h, fg):
    n = 11
    for i in range(n):
        o.rect(x + i * w / n, y, 1, h, _rgba(fg, 100))


_BACKS = {
    "solid": _back_solid, "grid": _back_grid, "checker": _back_checker,
    "stripes": _back_stripes, "bars": _back_bars, "frames": _back_frames,
    "dots": _back_dots, "cross": _back_cross, "brick": _back_brick,
    "diamond": _back_diamond, "emblem": _back_emblem, "pinstripe": _back_pinstripe,
}
BACK_PATTERNS = tuple(_BACKS)


# ------------------------------------------------------------- slots / util
def draw_slot(o, x, y, w, h, label="", label_color=(120, 108, 92, 200)):
    """A faint empty slot outline (foundation / empty tableau / empty stock)."""
    _outline(o, x, y, w, h, (92, 80, 64, 150))
    if label:
        o.text(label, x + w / 2, y + h * 0.34, size=int(h * 0.3),
               color=label_color, center=True)


def hover_outline(o, x, y, w, h):
    _outline(o, x, y, w, h, _HOVER, t=3)


def _outline(o, x, y, w, h, color, t=3):
    o.rect(x, y, w, t, color)
    o.rect(x, y + h - t, w, t, color)
    o.rect(x, y, t, h, color)
    o.rect(x + w - t, y, t, h, color)
