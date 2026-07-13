# Truly secret local multiplayer (companion phones) — design

Approved 2026-07-12. Builds on [board games design](2026-07-13-board-games-design.md) and the shipped
Replay Theater. First (and, for now, only) consumer: **Battleship**.

## Goal

Two people in the same room play a hidden-information board game with their secret state — ship
placement now, card hands / piece identities later — **genuinely un-seeable by the opponent**, without a
second full game cabinet.

The problem is physical, not algorithmic. On one shared cabinet screen, "polite" hotseat (blank-and-pass)
still leaks to a motivated onlooker and leans on trust. *Truly* secret requires a private per-player
channel. The answer: **each player's own phone is their private screen + controller**, and the cabinet is
the shared "TV." `games/battleship/model.py` was already written for this — it holds both fleets as the
single source of truth and leaves it to the *view* to decide what each side may see. This design
formalizes that view boundary and moves each side's view onto its owner's phone.

## Decisions (locked during brainstorming)

1. **Companion phones.** Secret pixels live on a device the opponent never holds. (Chosen over
   single-screen blank-and-pass and over a second full cabinet.)
2. **Model B — phone is the controller, cabinet is the shared TV.** Each player does *everything* on
   their phone (place fleet, tap to fire). During a match the cabinet is display-only: the public board
   plus animations; before the match, the lobby/QR. One consistent input rule; the cabinet never
   arbitrates shared controls. (Chosen over "phone as a mere private panel" with input split across
   devices.)
3. **Cabinet self-hosts now; host-agnostic client for the relay later (hybrid).** For in-room play the
   cabinet runs the server the phones talk to directly — lowest latency, no external dependency, secrets
   never leave the room. The phone app talks to whatever origin served it, so the *same* client can later
   point at the home-box relay for the separate online-between-cabinets mode.
4. **General seam, Battleship-only build.** Build the reusable companion layer in `games/board/` with
   clean interfaces; wire only Battleship now. Poker / Stratego slot in later by writing their model +
   views + projections against the same seam — no speculative code.
5. **Opponent chosen up front; lobby waits gracefully.** `VS AI` is its own mode at mode-select, never a
   silent lobby fallback. The secret-local lobby waits indefinitely, states *why* it is waiting, and ends
   only when the host cancels.
6. **Default port 1983, auto-fallback to a free port, manual override.** The real bound port is baked
   into the QR so players never type it.

## Architecture

### Cabinet = authority + shared TV + tiny web server

- Keeps running the authoritative `BattleshipModel` on the game thread (unchanged — already
  truth/view-separable, JSON-serialisable, deterministic).
- A **stdlib** HTTP server (`http.server` / `socketserver`, threaded) runs on a daemon thread — the same
  "never block a frame, communicate through a results queue" discipline `game/netclient.py` already uses
  for outbound calls, applied inbound.
- Renders only the **public projection**: both fog grids (hit/miss pegs, sunk ships revealed), the
  missile arc, splashes, the turn banner; plus the lobby/QR overlay before the match.
- **Thread model:** HTTP handler threads only *enqueue* phone actions and *read* the latest published
  view snapshot. The model is mutated **only** on the game thread. One inbound `queue.Queue`; one guarded
  outbound snapshot per seat. No locks on the model itself.

### Two projections per game — the generalisable seam

- `public_view(model) -> dict` — what the cabinet may draw. Never an un-hit ship.
- `secret_view(model, seat) -> dict` — what one seat's phone may see: its own fleet, incoming shots on
  it, its own shot-tracking (hit/miss/sunk on the enemy), phase, whose turn, winner. **Never** the
  opponent's un-hit ships.
- This is the fog-of-war principle from `model.py`, enforced per seat. Later: Poker's `secret_view` is
  your hand + the public table; Stratego's is your piece identities + the shared board.

### Phone = thin client (one self-contained HTML/JS file)

- Served by the cabinet at `GET /`; **host-agnostic** — it talks only to its own origin, so the same file
  works self-hosted now and via the relay later.
- Screens: **join** (name; code prefilled from the QR URL) → **place fleet** (drag, plus one-tap *Auto*
  and *Rotate*; *Ready* locks it) → **play** (your turn: tap target → *FIRE*; their turn: watch, see your
  own fleet + incoming) → **game over**.
- Renders only its own `secret_view`. Reconnect-safe: seat token in `localStorage`; re-opening the URL
  re-attaches to the seat and re-syncs from the cabinet's authoritative state.

## Modes

Selected at mode-select via the existing `create_run(mode, rng)` mechanism: `HOTSEAT`, `VS AI`,
**`SECRET_LOCAL`** (this design), and later `ONLINE`. `HOTSEAT` and `VS AI` keep the game fully playable
solo/offline with no phone; `SECRET_LOCAL` is the two-humans / two-phones mode.

## Lobby & join flow

- The cabinet shows a **QR** (its URL embeds the join code and the real bound port), the short **code**,
  and the LAN URL, plus a live **seat list** (P1/P2, name, ready state).
- Each player scans → the phone app loads → they enter a name → a seat is assigned.
- Both players place their fleets privately; when both are locked the match starts and the cabinet begins
  the fire phase.

### Waiting & failure states (the lobby states *why* it is waiting)

- **Waiting · normal** — host up, QR/code shown, no scans yet. Benign; waits indefinitely.
- **Join attempted · rejected** — a device tried and was refused; the cabinet names the reason
  (`wrong_code`, with the mistyped value + source IP; `seat_taken`; `name_taken`; `version_mismatch`) and
  stays open.
- **Can't host** — the server could not bind (e.g. a forced port is busy). No QR; shows the exact reason;
  offers a **manual port field** + retry. The only state with nothing to wait for.
- **Joined · then dropped** — a seat connected then lost liveness; the cabinet holds the seat, shows how
  long ago it dropped, preserves the board, and lets the player resume by re-opening the URL.
- The lobby **never** times out into a bot. Only the host ends the wait (*Cancel*).

## Port handling

- Prefer **1983**. If it is busy, auto-step to the next free port; worst case, bind to an OS-assigned free
  port. The actual bound port is written into the QR/URL, so players never type it.
- Manual override lives in Settings and on the "can't host" card.

## Transport & endpoints

Stdlib HTTP + **long-poll** — no third-party dependency, consistent with `netclient.py`'s stdlib-only
stance. Long-poll is ample for a turn-based game; WebSockets are a noted future upgrade only if continuous
sub-second updates are ever wanted.

- `GET /` → the phone app (inlined single file).
- `POST /join {code, name}` → `{seat, token}` or a typed rejection:
  `wrong_code` | `seat_taken` | `name_taken` | `version_mismatch`.
- `GET /poll?seat=&token=&v=<version>` → held open until that seat's view version advances (or ~25s →
  `{v, changed:false}`); on change returns `{v, secret_view}`.
- `POST /action {seat, token, kind, ...}` → `kind` ∈ {`ready` (commits the whole fleet layout — ship
  placement happens locally on the phone until then, so the cabinet only tracks ready / not-ready per
  seat), `fire` (x, y), `cancel`}; validated on the game thread; returns accept or a typed reject.
- A per-seat **token** gates `/poll` and `/action`.

## Data flow — one turn

1. Cabinet shows the lobby (QR). Phones join → seats assigned → cabinet: "both place your fleets."
2. Both place fleets on their phones (parallel, secret) → *Ready* → match starts.
3. On P1's turn, P1's phone: tap target → *FIRE* → `POST /action {fire, x, y}`.
4. The cabinet (game thread) drains the action, validates `can_fire`, applies `fire()`, and enqueues the
   missile-arc + splash/explosion on the `board/anim` queue. **The anim queue gates handoff** — the shot
   fully plays out on the TV before the turn passes (exactly its documented purpose).
5. The cabinet bumps both seats' view versions; the open long-polls return fresh `secret_view` (P1 sees
   the hit recorded, P2 sees the incoming hit on their board). The TV shows the arc + HIT / miss / SUNK.
6. The turn passes to P2; repeat. On a win the TV plays the finale and reveals the sunk fleet.

## Robustness & secrecy

- **Reconnect:** token in `localStorage`; re-open the URL → re-attach + re-sync from cabinet authority.
- **Liveness:** per-seat last-seen derived from polls; a gap flips the seat to "disconnected" in the
  HUD/lobby but never mutates game state.
- **Thread safety:** actions are enqueued from HTTP threads and applied only on the game thread; a single
  guarded outbound snapshot per seat.
- **Authz / secrecy:** the per-seat token gates private views; secret state exists only on the owning
  phone and never leaves the cabinet. Anti-cheat is a **non-goal** — cabinet authority bounds casual
  tampering, but "truly secret" here means *un-seeable*, not tamper-proof.

## Replay tie-in (free)

The cabinet is the authority and observes every applied move, so a secret-local match records as an
ordinary deterministic replay (seed + move stream). Replay Theater, export, and (roadmap #3)
share-to-leaderboard all work unchanged for secret-local matches.

## Testing

- **Secrecy invariant (critical):** across a fully played-out game, assert that `secret_view(model, "P1")`
  and `public_view(model)` never contain P2's un-hit ship cells (and vice-versa). This property *is*
  "truly secret."
- **Session / transport (headless):** drive `SecretLocalSession` with two in-process fake phone clients
  over loopback (join → place → fire → poll → win); assert turn-gating (out-of-turn action rejected),
  version bumps, typed join rejections, and reconnect re-sync. No GL.
- Existing `tools/test_battleship.py` stays green (the model is unchanged).
- **Phone app + on-cabinet rendering:** verified via the `/verify` flow against the running cabinet (real
  browser + device) — a verification step, not a unit test.

## Module / file plan

- **New `games/board/companion/`** — the reusable seam:
  - `session.py` — `SecretLocalSession`: seats, tokens, inbound action queue, per-seat view versioning,
    liveness.
  - `views.py` — the `public_view` / `secret_view` protocol + shared helpers.
  - `server.py` — stdlib HTTP + long-poll; serves the phone app and the endpoints above; port selection.
- **New `games/board/phone/app.html`** — the one-file, host-agnostic phone client (inlined JS/CSS).
- **New / extended `games/board/run.py`** — `BoardRun` base wiring model ↔ session ↔ `anim` queue ↔
  public renderer, exposing the `SECRET_LOCAL` mode. (`games/board/anim.py` is reused as-is.)
- **New `games/battleship/game.py`** — `INFO`, `BattleshipRun(BoardRun)`, `create_run(mode, rng)`, the
  public renderer (voxel grids, missile arc), and battleship's `public_view` / `secret_view`; plus
  `games/battleship/__init__.py` and `games/battleship/achievements.py`.
- **Edit `games/__init__.py`** — add the `BOARD` category containing `battleship`.
- **Tests** — extend `tools/test_battleship.py`; add `tools/test_companion.py`.

## Non-goals

- Anti-cheat / tamper-resistance (cabinet authority only; consistent with the board spec).
- Other board games (Poker, Stratego, …) — the seam is designed for them, but none are built here.
- WebSockets — long-poll suffices for turn-based play.
- The online-between-cabinets mode — separate, uses the home-box relay; kept compatible only via the
  host-agnostic phone client.

## Sequencing (increments)

1. `games/board/companion/session.py` + `views.py` + battleship's projections; headless **secrecy** and
   session tests (no server, no GL).
2. `games/board/companion/server.py` (stdlib HTTP + long-poll) + a loopback transport test; port
   selection (1983 → fallback → manual override).
3. `games/board/phone/app.html` — join → place → play, host-agnostic; reconnect.
4. `games/battleship/game.py` (`BoardRun` + public renderer + missile-arc animation) + the lobby/QR
   overlay and waiting/failure states; register the `BOARD` category.
5. Replay-recording hook for secret-local matches; `/verify` end-to-end pass on the cabinet.

## Implementation status (2026-07-12)

Shipped on branch `secret-local-multiplayer` (plan: `docs/superpowers/plans/2026-07-12-secret-local-multiplayer.md`).
**SECRET LOCAL is fully implemented and headless-tested**; VS-AI and HOTSEAT are deferred
follow-ups (the run + renderer are structured to add them). Deviations from this design as
first written:

- **Replay is richer than the "free" claim.** It is *not* the existing input-bitmask replay
  reused — that records held keys and doesn't fit move-driven board games. Instead
  `games/board/replay.py` records a **move stream** and offers **per-perspective playback**:
  rewatch a finished match as P1, as P2 (each hiding what was hidden to *them* at that step),
  or as an omniscient Director. Verified in `tools/test_companion.py` (secrecy holds through
  time per perspective).
- **One small `main.py` edit** beyond the "registration only" estimate: a guarded
  `run.close()` call in `abandon_run` so the host server/port is released on exit.
- **New dependency `segno`** (pure-Python QR; degrades to a text code if absent).
- Cabinet input for a would-be VS-AI/HOTSEAT mode is unbuilt (secret-local needs none — the
  phones are the controllers).
