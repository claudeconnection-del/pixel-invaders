"""Companion kit for truly-secret local multiplayer.

Two people in one room play a hidden-information board game with their secret
state genuinely un-seeable by the opponent: each player's phone is a private
controller, the cabinet is the shared TV. The cabinet keeps the authoritative
model and hands each seat only its own *view*.

Pieces (added incrementally):
- views: the public_view / secret_view projection protocol (per game) — the
  secrecy boundary and the generalisable seam.
- session (SecretLocalSession): game-agnostic seats / tokens / turn-gated
  action queue / per-seat versioned views.
- server (CompanionServer): stdlib HTTP + long-poll; serves the phone app.
"""
