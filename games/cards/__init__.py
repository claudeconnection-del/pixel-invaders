"""Shared kit for the TABLETOP category (solo card/tabletop games).

- deck: pure card model (Card, make_deck, shuffle, deal). No pygame/GL.
- skins: deck + felt cosmetic registries with unlock gating (pure data).
- render: overlay card/felt drawing (GL) — added in the view increment.
"""
from games.cards.deck import Card, make_deck, shuffle, SUITS, RANKS  # noqa: F401
