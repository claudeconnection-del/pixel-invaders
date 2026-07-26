"""Cabinet Man's reference pilot: an unorthodox Klondike speed-solver. Once
the board is solvable (no face-down tableau cards remain) it always finishes
via the same auto-complete route the game itself guarantees a win with
(`SolitaireRun._auto_step`) — so Cabinet Man never loses a winnable board.
Before that point it makes visible progress a good player would (clear the
waste to a foundation, advance a tableau pile toward one, else draw), but
with personality: it alternates which end of the tableau it scans each
cycle, and every so often spends a move on a legal-but-pointless
tableau-to-tableau shuffle instead of the most useful action. Cadence is
~90ms between actions with small hesitations, seeded from the run's own rng
(never wall-clock random) so a pilot run is exactly reproducible.

Limitation (v1): if the board isn't solvable and no legal action remains
(everything blocked, stock and waste both empty) the pilot goes idle rather
than finding a clever unstick — losing weirdly is on-brand, but there's no
unstick logic yet.
"""
_BASE_DELAY = 0.09
_JITTER = 0.05
_SHUFFLE_CHANCE = 0.12   # personality: an occasional pointless-but-legal move


class SolitairePilot:
    label = "Cabinet Man"

    def __init__(self, run):
        self.rng = run.rng
        self._scan_dir = 1
        self._timer = self._next_delay()

    def _next_delay(self):
        return _BASE_DELAY + self.rng.random() * _JITTER

    def step(self, run, dt):
        self._timer -= dt
        guard = 0
        while self._timer <= 0 and not run.won_flag and guard < 200:
            guard += 1
            self._timer += self._next_delay()
            if not self._act(run):
                break        # nothing legal happened this tick: go idle
        return None          # table game: acts directly, no InputState

    # ------------------------------------------------------------- actions
    def _act(self, run):
        m = run.model
        if run._solvable():
            result = run._auto_step()
            if result == "home":
                run.emit("sol_home")
                run._check_win()
            elif result == "draw":
                run.emit("sol_draw")
            return result is not None
        if self.rng.random() < _SHUFFLE_CHANCE and self._shuffle(m):
            run.emit("sol_move")
            return True
        if m.waste_to_foundation():
            run.emit("sol_home")
            run._check_win()
            return True
        cols = range(7) if self._scan_dir > 0 else range(6, -1, -1)
        self._scan_dir *= -1        # alternate which end it scans next time
        for i in cols:
            if m.tableau_to_foundation(i):
                run.emit("sol_home")
                run._check_win()
                return True
        if m.stock or m.waste:
            if m.draw():
                run.emit("sol_draw")
                return True
        return False

    def _shuffle(self, m):
        """A harmless legal move: shift the top of one non-empty tableau pile
        onto another. Pointless but legal — a personality flourish, not a
        step toward the win (a real winning move is still tried right after
        if this doesn't find one)."""
        for i, src in enumerate(m.tableau):
            if not src["up"]:
                continue
            for j in range(7):
                if j != i and m.tableau_to_tableau(i, 1, j):
                    return True
        return False


def create_pilot(run):
    return SolitairePilot(run)
