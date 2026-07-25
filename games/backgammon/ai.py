"""A fair, greedy Backgammon AI: enumerate every legal move sequence for the
roll, apply each to a scratch copy of the board, and score the result —
minimise your own pip count, add a bonus per checker hit and per point newly
made, subtract a penalty per own blot left within the opponent's direct
(single-die) shot range. No hidden information is used (the whole board is
public in Backgammon), just a simple heuristic instead of full rollouts.

Also provides `random_move`, a uniformly-random-legal-sequence baseline used
by the AI-vs-baseline win-rate test.
"""
from games.backgammon.model import blot_exposure, made_points, pip_count, simulate

PIP_WEIGHT = 1.0
HIT_BONUS = 12
MADE_POINT_BONUS = 8
BLOT_PENALTY = 6


def score_sequence(model, player, seq):
    """Heuristic score (higher is better for `player`) of applying `seq`."""
    points, bar, off = simulate(model.points, model.bar, model.off, player, seq)
    pips = pip_count(points, bar, player)
    hits = sum(1 for mv in seq if mv.get("hit"))
    gained_points = max(
        0, made_points(points, player) - made_points(model.points, player))
    blots = blot_exposure(points, bar, player)
    return (-PIP_WEIGHT * pips + HIT_BONUS * hits
            + MADE_POINT_BONUS * gained_points - BLOT_PENALTY * blots)


def ai_move(model, player=None):
    """Play the best-scoring legal sequence for `player` (default: whoever's
    turn it is) given model.dice, apply it, and return the sequence chosen."""
    player = player or model.turn
    seqs = model.legal_moves(player, model.dice)
    best_seq, best_score = seqs[0], None
    for seq in seqs:
        score = score_sequence(model, player, seq)
        if best_score is None or score > best_score:
            best_score, best_seq = score, seq
    model.apply(best_seq)
    return best_seq


def random_move(model, rng, player=None):
    """Baseline: pick a uniformly random *legal* sequence (still respects the
    forced-play rule — `legal_moves` only returns maximal sequences — it just
    doesn't reason about which is best). Used to measure the greedy AI's edge."""
    player = player or model.turn
    seqs = model.legal_moves(player, model.dice)
    seq = rng.choice(seqs)
    model.apply(seq)
    return seq
