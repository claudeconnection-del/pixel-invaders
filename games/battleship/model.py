"""Battleship rules — pure logic, no pygame/GL, fully deterministic given an
rng. The model is the single source of truth (both fleets); the *view* decides
what each side is allowed to see (fog of war). State is JSON-serialisable so it
can ride the turn-match relay verbatim.

Two players, "P1"/"P2". Standard fleet on a 10x10 grid. Phases: place -> fire
-> over. Classic turn rule: one shot per turn, then the opponent moves (hit or
miss). A player loses when their whole fleet is sunk.
"""
import random

SIZE = 10
FLEET = [("Carrier", 5), ("Battleship", 4), ("Cruiser", 3),
         ("Submarine", 3), ("Destroyer", 2)]
PLAYERS = ("P1", "P2")
OTHER = {"P1": "P2", "P2": "P1"}


class BattleshipModel:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.size = SIZE
        self.phase = "place"          # place -> fire -> over
        self.turn = "P1"              # whose action is next
        self.ships = {"P1": [], "P2": []}   # [{name,size,cells:[[x,y]...]}]
        self.shots = {"P1": [], "P2": []}   # cells fired AT this player: [[x,y]]
        self.winner = None

    # -------------------------------------------------------- placement
    def cells_for(self, x, y, size, horizontal):
        """The cells a ship would occupy, or None if off-board."""
        out = []
        for i in range(size):
            cx = x + (i if horizontal else 0)
            cy = y + (0 if horizontal else i)
            if not (0 <= cx < self.size and 0 <= cy < self.size):
                return None
            out.append([cx, cy])
        return out

    def _occupied(self, player):
        return {tuple(c) for s in self.ships[player] for c in s["cells"]}

    def can_place(self, player, x, y, size, horizontal):
        cells = self.cells_for(x, y, size, horizontal)
        if cells is None:
            return False
        occ = self._occupied(player)
        return all(tuple(c) not in occ for c in cells)

    def place_ship(self, player, name, size, x, y, horizontal):
        if not self.can_place(player, x, y, size, horizontal):
            return False
        self.ships[player].append(
            {"name": name, "size": size,
             "cells": self.cells_for(x, y, size, horizontal)})
        return True

    def random_place(self, player):
        """Auto-deploy a full fleet for `player` (used by AI and quick-place)."""
        self.ships[player] = []
        for name, size in FLEET:
            while True:
                horizontal = self.rng.random() < 0.5
                if horizontal:
                    x = self.rng.randrange(self.size - size + 1)
                    y = self.rng.randrange(self.size)
                else:
                    x = self.rng.randrange(self.size)
                    y = self.rng.randrange(self.size - size + 1)
                if self.place_ship(player, name, size, x, y, horizontal):
                    break

    def fleet_complete(self, player):
        return len(self.ships[player]) == len(FLEET)

    def begin_fire(self, first="P1"):
        self.phase = "fire"
        self.turn = first

    # ------------------------------------------------------------ firing
    def already_shot(self, target, x, y):
        return [x, y] in self.shots[target]

    def can_fire(self, shooter, x, y):
        return (self.phase == "fire" and self.turn == shooter
                and self.winner is None
                and 0 <= x < self.size and 0 <= y < self.size
                and not self.already_shot(OTHER[shooter], x, y))

    def fire(self, shooter, x, y):
        """`shooter` fires at OTHER(shooter). Returns a result dict describing
        the outcome (for animation/audio), or None if the shot is illegal."""
        if not self.can_fire(shooter, x, y):
            return None
        target = OTHER[shooter]
        self.shots[target].append([x, y])
        ship = self.ship_at(target, x, y)
        hit = ship is not None
        sunk = ship if (hit and self.is_sunk(target, ship)) else None
        if hit and self.all_sunk(target):
            self.winner = shooter
            self.phase = "over"
        else:
            self.turn = target  # classic: one shot, then hand off
        return {
            "shooter": shooter, "target": target, "x": x, "y": y,
            "hit": hit,
            "sunk": sunk["name"] if sunk else None,
            "sunk_cells": [list(c) for c in sunk["cells"]] if sunk else None,
            "win": self.winner is not None,
        }

    # --------------------------------------------------------- queries
    def ship_at(self, player, x, y):
        for s in self.ships[player]:
            if [x, y] in s["cells"]:
                return s
        return None

    def is_sunk(self, player, ship):
        return all(self.already_shot(player, cx, cy) for cx, cy in ship["cells"])

    def all_sunk(self, player):
        ships = self.ships[player]
        return bool(ships) and all(self.is_sunk(player, s) for s in ships)

    def remaining_ships(self, player):
        """Count of un-sunk ships (for the HUD fleet readout)."""
        return sum(0 if self.is_sunk(player, s) else 1 for s in self.ships[player])

    # --------------------------------------------------- serialisation
    def to_state(self):
        return {
            "phase": self.phase, "turn": self.turn, "size": self.size,
            "ships": self.ships, "shots": self.shots, "winner": self.winner,
        }

    @classmethod
    def from_state(cls, data, rng=None):
        m = cls(rng)
        m.phase = data["phase"]
        m.turn = data["turn"]
        m.size = data.get("size", SIZE)
        m.ships = {"P1": list(data["ships"]["P1"]),
                   "P2": list(data["ships"]["P2"])}
        m.shots = {"P1": list(data["shots"]["P1"]),
                   "P2": list(data["shots"]["P2"])}
        m.winner = data["winner"]
        return m
