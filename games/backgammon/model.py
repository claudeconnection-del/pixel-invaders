"""Backgammon rules — pure logic, no pygame/GL, deterministic from a seed.
Two players "A" and "B" on a 24-point board.

Board representation: `points[24]` signed ints — a positive n means N of A's
checkers on that point, negative n means N of B's checkers; `bar = {"A": n,
"B": n}` (hit checkers waiting to re-enter); `off = {"A": n, "B": n}` (borne
off). Every checker is always accounted for in exactly one of points/bar/off
(15 per side) — see `checker_count`.

Direction & home boards (fixed by this implementation, not a house rule):
A moves from high index to low index (24-point = index 23, down to the
1-point = index 0) and bears off past index 0; A's home board is indices
0-5 (points 1-6). B moves the opposite way (index 0 up to index 23) and
bears off past index 23; B's home board is indices 18-23 (points 19-24). A
enters from the bar into B's home (indices 18-23); B enters into A's home
(indices 0-5).

`legal_moves(player, dice)` returns every legal *sequence* of moves for a
roll (a list of move-dicts each), honouring: bar-first entry, blocked points
(>=2 opposing checkers), hitting a blot (single opposing checker -> bar),
bearing off only once all 15 of a player's checkers are in its home board
(exact roll, or a higher roll borne off from the highest occupied point when
no checker sits on the exact point), and the standard forced-play rule: you
must use as many of the dice as any legal sequence does, and if only one of
two distinct dice can be played *at all* (never both, in either order) you
must play the larger one.

`apply(seq)` applies a chosen sequence for the current turn, hands off to
the other player (or ends the game and grades it: single / gammon / loser
bore off none / backgammon / gammon + a loser checker still in the winner's
home board or on the bar).

No doubling cube in this version — v1 plays straight points, no double/redouble
negotiation or stake multiplier. Deferred, like Rummy's lay-offs, for a later
pass once the headless core + AI are solid.
"""
import random

PLAYERS = ("A", "B")
OTHER = {"A": "B", "B": "A"}
NUM_POINTS = 24

# Standard starting position, indices 0..23 (points 1..24). A (+) moves
# toward index 0; B (-) moves toward index 23.
START_POINTS = [0] * NUM_POINTS
START_POINTS[23] = 2    # A: 24-point
START_POINTS[12] = 5    # A: 13-point
START_POINTS[7] = 3     # A: 8-point
START_POINTS[5] = 5     # A: 6-point
START_POINTS[0] = -2    # B: 1-point
START_POINTS[11] = -5   # B: 12-point
START_POINTS[16] = -3   # B: 17-point
START_POINTS[18] = -5   # B: 19-point
START_POINTS = tuple(START_POINTS)

HOME_RANGE = {"A": range(0, 6), "B": range(18, 24)}


def own_count(points, i, player):
    """How many of `player`'s checkers sit on point index i (0 if none/opponent's)."""
    v = points[i]
    if player == "A":
        return v if v > 0 else 0
    return -v if v < 0 else 0


def dist(i, player):
    """Pips from point index i to bearing off, for `player`."""
    return i + 1 if player == "A" else NUM_POINTS - i


def entry_index(player, die):
    """Board index a checker entering from the bar lands on with this die."""
    return NUM_POINTS - die if player == "A" else die - 1


def home_indices(player):
    return HOME_RANGE[player]


def highest_occupied_home_index(points, player):
    """Index of the home point farthest from bearing off that still holds one
    of `player`'s checkers, or None if the home board is empty."""
    idxs = [i for i in home_indices(player) if own_count(points, i, player) > 0]
    if not idxs:
        return None
    return max(idxs) if player == "A" else min(idxs)


def all_in_home(points, bar, player):
    if bar[player] > 0:
        return False
    home = set(home_indices(player))
    for i in range(NUM_POINTS):
        if own_count(points, i, player) > 0 and i not in home:
            return False
    return True


def pip_count(points, bar, player):
    """Total pips `player` needs to bear off every checker (bar counts 25)."""
    total = bar[player] * (NUM_POINTS + 1)
    for i in range(NUM_POINTS):
        n = own_count(points, i, player)
        if n:
            total += n * dist(i, player)
    return total


def made_points(points, player):
    """Count of points `player` has 'made' (>=2 own checkers)."""
    return sum(1 for i in range(NUM_POINTS) if own_count(points, i, player) >= 2)


def checker_count(points, bar, off, player):
    """Total of `player`'s checkers across points/bar/off — always 15."""
    on_points = sum(own_count(points, i, player) for i in range(NUM_POINTS))
    return on_points + bar[player] + off[player]


def blot_exposure(points, bar, player):
    """Count of `player`'s blots (lone checkers) reachable by a single direct
    die (1-6) from the opponent — either an on-board opposing checker, or the
    opponent entering from the bar directly onto the blot's point."""
    opp = OTHER[player]
    exposed = 0
    for i in range(NUM_POINTS):
        if own_count(points, i, player) != 1:
            continue
        hit = False
        for d in range(1, 7):
            if player == "A":
                j = i - d
                if j >= 0 and own_count(points, j, opp) > 0:
                    hit = True
                    break
            else:
                j = i + d
                if j <= NUM_POINTS - 1 and own_count(points, j, opp) > 0:
                    hit = True
                    break
        if not hit and bar[opp] > 0:
            d = entry_die_for(player, i)
            if d is not None:
                hit = True
        if hit:
            exposed += 1
    return exposed


def entry_die_for(landing_player_side, i):
    """If the OPPONENT of the checker on point i were entering from the bar,
    which die (1-6) would land exactly on index i? None if none does.
    (landing_player_side is the blot's owner; the opponent enters using its
    own entry_index formula — invert it for index i.)"""
    opp = OTHER[landing_player_side]
    d = NUM_POINTS - i if opp == "A" else i + 1
    return d if 1 <= d <= 6 else None


def _atomic_moves(points, bar, off, player, die):
    """Every legal single-die move from this exact position: dicts with
    from (int index or 'bar'), to (int index or 'off'), die, hit (bool)."""
    moves = []
    opp = OTHER[player]
    if bar[player] > 0:
        idx = entry_index(player, die)
        if own_count(points, idx, opp) < 2:
            moves.append({"from": "bar", "to": idx, "die": die,
                          "hit": own_count(points, idx, opp) == 1})
        return moves
    home = all_in_home(points, bar, player)
    top = highest_occupied_home_index(points, player) if home else None
    for i in range(NUM_POINTS):
        if own_count(points, i, player) <= 0:
            continue
        dest = i - die if player == "A" else i + die
        if 0 <= dest < NUM_POINTS:
            if own_count(points, dest, opp) < 2:
                moves.append({"from": i, "to": dest, "die": die,
                              "hit": own_count(points, dest, opp) == 1})
        elif home and i in home_indices(player):
            d_i = dist(i, player)
            if d_i == die or (die > d_i and i == top):
                moves.append({"from": i, "to": "off", "die": die, "hit": False})
    return moves


def _do_move(points, bar, off, player, move):
    """Apply one atomic move to fresh copies of points/bar/off; return them."""
    points = list(points)
    bar = dict(bar)
    off = dict(off)
    opp = OTHER[player]
    src = move["from"]
    if src == "bar":
        bar[player] -= 1
    else:
        points[src] += -1 if player == "A" else 1
    if move["to"] == "off":
        off[player] += 1
    else:
        dst = move["to"]
        if move.get("hit"):
            bar[opp] += 1
            points[dst] = 0
        points[dst] += 1 if player == "A" else -1
    return points, bar, off


def simulate(points, bar, off, player, seq):
    """Apply a whole move sequence to fresh copies; return (points, bar, off)."""
    for mv in seq:
        points, bar, off = _do_move(points, bar, off, player, mv)
    return points, bar, off


def _enumerate_sequences(points, bar, off, player, dice):
    """All maximal legal sequences for `player` given the dice multiset
    (list of ints; 4 equal values for doubles). Returns a list of tuples of
    move-dicts, always non-empty (a lone empty tuple if nothing is legal)."""
    completed = []

    def dfs(pts, br, of, remaining, seq):
        tried = set()
        branched = False
        for pos, d in enumerate(remaining):
            if d in tried:
                continue
            tried.add(d)
            for mv in _atomic_moves(pts, br, of, player, d):
                branched = True
                npts, nbr, nof = _do_move(pts, br, of, player, mv)
                nremaining = remaining[:pos] + remaining[pos + 1:]
                dfs(npts, nbr, nof, nremaining, seq + [mv])
        if not branched:
            completed.append(tuple(seq))

    dfs(points, bar, off, list(dice), [])
    max_len = max(len(s) for s in completed)
    best = [s for s in completed if len(s) == max_len]
    # Forced higher-die rule: exactly one die playable (not two in either
    # order) out of two distinct values -> must play the larger if it, on
    # its own, is legal.
    distinct = sorted(set(dice))
    if max_len == 1 and len(distinct) == 2:
        hi = distinct[-1]
        hi_playable = any(s[0]["die"] == hi for s in best)
        if hi_playable:
            best = [s for s in best if s[0]["die"] == hi]
    return best


class Backgammon:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.points = list(START_POINTS)
        self.bar = {"A": 0, "B": 0}
        self.off = {"A": 0, "B": 0}
        self.turn = "A"
        self.dice = []
        self.winner = None
        self.result = None

    # ------------------------------------------------------------- dice
    def roll(self):
        d1 = self.rng.randint(1, 6)
        d2 = self.rng.randint(1, 6)
        self.dice = [d1, d1, d1, d1] if d1 == d2 else [d1, d2]
        return list(self.dice)

    # ------------------------------------------------------------ queries
    def pip_count(self, player):
        return pip_count(self.points, self.bar, player)

    def all_in_home(self, player):
        return all_in_home(self.points, self.bar, player)

    def checker_count(self, player):
        return checker_count(self.points, self.bar, self.off, player)

    def legal_moves(self, player, dice):
        """All maximal legal move sequences for `player` given `dice`
        (a list from roll(): 2 values, or 4 equal ones for doubles)."""
        return _enumerate_sequences(self.points, self.bar, self.off, player, dice)

    # -------------------------------------------------------------- apply
    def apply(self, seq):
        """Apply a chosen move sequence for the player whose turn it is.
        Hands off the turn, or ends + grades the game if it finishes it."""
        player = self.turn
        for mv in seq:
            self.points, self.bar, self.off = _do_move(
                self.points, self.bar, self.off, player, mv)
        self.dice = []
        if self.off[player] == 15:
            self._finish(player)
        else:
            self.turn = OTHER[player]
        return seq

    def _finish(self, winner):
        loser = OTHER[winner]
        self.winner = winner
        if self.off[loser] > 0:
            grade = "single"
        else:
            home = home_indices(winner)
            loser_in_winner_home = any(
                own_count(self.points, i, loser) > 0 for i in home)
            if self.bar[loser] > 0 or loser_in_winner_home:
                grade = "backgammon"
            else:
                grade = "gammon"
        self.result = {"winner": winner, "loser": loser, "grade": grade}
