"""Overlay drawing for cards + felts. 2D only (uses OverlayRenderer o.rect /
o.text), so it runs post-CRT and stays crisp. A card is drawn procedurally
(edge + face + rank/suit ink), themed by a DeckSkin; felts are drawn by the
game (solid/gradient wash or an ambient-scene backdrop).

Suits are shown as letters (S/H/D/C) coloured by suit — the overlay font is an
ASCII atlas, so letters are safe where ♠♥♦♣ glyphs might not render.
"""
_EDGE = (16, 12, 10, 255)
_SEL = (255, 210, 90, 255)
_HOVER = (255, 236, 170, 130)


def _rgba(c, a=255):
    return (c[0], c[1], c[2], a)


def draw_card(o, x, y, w, h, card, skin, face_up=True, selected=False):
    """Draw one card at (x, y). `card` may be None for a face-down/empty slot
    when face_up is False."""
    o.rect(x, y, w, h, _EDGE)                          # edge / drop shadow
    if not face_up:
        trim = skin.trim
        o.rect(x + 2, y + 2, w - 4, h - 4, _rgba(trim))
        dark = (max(0, trim[0] - 46), max(0, trim[1] - 46), max(0, trim[2] - 46))
        o.rect(x + 9, y + 9, w - 18, h - 18, _rgba(dark))
        o.rect(x + w / 2 - 3, y + 9, 6, h - 18, _rgba(trim))   # simple back motif
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
    if selected:
        _outline(o, x, y, w, h, _SEL)


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
