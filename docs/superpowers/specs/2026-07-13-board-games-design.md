# Board games + turn-based multiplayer — design

Approved direction (2026-07-13). A new **BOARD** cabinet category of recognizable,
easy-to-play tabletop clones, Emberlight-themed, playable **hotseat**, **vs local AI**,
and **online turn-based multiplayer** over the existing LAN-local REST backend. Board
games join the arcade games and the FPS games in the category carousel.

Games (in build order): **Battleship** (first vertical slice) → **Backgammon** →
**Candyland** → **Game of Life** → **Poker** → **Monopoly** (spec-only stretch).

## Backend: turn-match API (game-agnostic relay)

The home-box backend already relays async score sessions. Board games add a **turn-match**
relay that is deliberately a *dumb state store* — it knows nothing about any game's rules,
so all six games share one endpoint set. Authority is client-side (fine for family/LAN;
noted as a non-goal to prevent cheating).

Per match it stores: `id` (4-char code), `game`, `state` (opaque JSON blob), `turn` (opaque
string — whose move is next, or null), `version` (int), `players[]`, timestamps. TTL cleanup
like sessions.

- `POST /api/v1/matches` `{game, host, state, turn}` → `{id, version, state, turn, players}`
- `POST /api/v1/matches/{id}/join` `{name}` → full match (rejects dup name / full / missing)
- `POST /api/v1/matches/{id}/move` `{name, base_version, state, turn}` → **turn-gated
  optimistic concurrency**: accepted iff `base_version == current version` AND
  (`turn is None` or `turn == name`). On accept: `version += 1`, store new `state`/`turn`;
  else `409` (re-poll and retry). Returns the authoritative match.
- `GET /api/v1/matches/{id}?since=<version>` → the match if `version > since` (poll for the
  opponent's move); `304`-style empty otherwise so polling is cheap.

Optimistic concurrency + turn-gating means two clients can't both move: the server only
accepts the current turn-holder at the current version. Clients poll ~1-2s, apply the new
`state` with an animation, and it becomes their turn.

## Cabinet-side board framework

`games/board/` shared kit so each game is just rules + art:

- **BoardRun** (implements the GameRun duck-type): owns a game `model`, a `mode`
  (HOTSEAT / AI / ONLINE), an animation queue, and a cursor. `update(dt, inp)` tweens
  animations and handles pointer/keys; `draw()` renders the voxel board + pieces; `draw_hud()`
  shows whose turn / status. No per-frame sim — it's event-driven.
- **Turn model**: the game model exposes `state` (serialisable), `current_turn`,
  `legal_moves()`, `apply(move)` (returns animations), `winner`. HOTSEAT alternates local
  players; AI fills the opponent via `ai_move(model)`; ONLINE syncs `state`/`turn` through
  the match client and animates applied opponent moves.
- **Match client**: cabinet-level, extends the net client — create/join/move/poll for the
  turn-match API, offline-safe. Reuses the existing lobby UI (host code / join code) and adds
  a "your turn / their turn / waiting" banner.
- **Selection input**: pointer pick (mouse) with a keyboard/gamepad cursor fallback, themed
  highlight on the hovered cell/piece.
- **Elegant animation** is a first-class concern: pieces tween (ease), dice tumble, cards
  flip, missiles arc, tokens hop cell-to-cell. The animation queue gates turn handoff so a
  move fully plays before the next begins (and, online, before `move` is pushed).

## Per-game notes

- **Battleship** — 2 grids of voxel cells; hidden ship placement phase, then alternate firing
  a shot (missile arc → splash/explosion). State = both boards + shot history + phase + turn.
  Cleanest first slice: grid, hidden state, clear turns, obvious online, great animation.
- **Backgammon** — 24 points + bar/off; tumbling dice, checker slides, hit/enter, bearing off,
  optional doubling cube. Rich animation; medium rules.
- **Candyland** — linear colour track, draw a card, hop token to the next matching colour,
  shortcuts/sticky spots. Trivial rules, lots of warm board art; great for young family.
- **Game of Life** — spinner + branching track, cars with peg people, pay-days/choices,
  simplified money. Roll-and-move with light decisions.
- **Poker** — 5-card draw or Texas hold'em (TBD at build), hidden hands, betting rounds, hand
  evaluator, chips. Most UI/logic-heavy; later.
- **Monopoly** — **spec only** (stretch): 40-space board, property/rent/houses, chance/chest,
  jail, trading. Design captured; implementation deferred.

## Modes & solo fallback

Every board game ships HOTSEAT + VS-AI so it's fully playable solo/offline; ONLINE is additive
and degrades to "server unreachable" gracefully. AI ranges from trivial (Candyland is
deterministic) to a simple heuristic (Battleship hunt/target; Backgammon pip-count greedy).

## Testing

- Backend: `server/test_server.py` gains match create/join/move(turn-gated, version-conflict)/
  poll cases; `deploy_smoke.py` gains a match round-trip on the hidden `_ci` game.
- Each game: a headless rules test (legal moves, apply, winner, AI plays a full game to a
  terminal state deterministically) with no GL, plus smoke coverage of a hotseat game driven
  to completion.

## Sequencing

1. Turn-match backend API + tests (this increment). 2. Board framework + **Battleship**
(hotseat + AI, then online). 3. Backgammon. 4. Candyland + Life. 5. Poker. 6. Monopoly spec.
