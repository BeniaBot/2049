# -*- coding: utf-8 -*-
"""
brain2049 - the thinking engine of 2049.

Everything the game "understands" about a position lives here:
  * fast move generation on an immutable board of ranks
    (rank 0 = empty, rank k = tile 2**k)
  * a positional evaluation: monotonic edges, merge chances, free space
  * an expectimax search that weighs every possible spawn (2 or 4, any cell)
  * survival odds - how close game over really is
  * stuck-tile analysis - which low tile is really in the way, and how much
  * spawn choices for the hidden assists and for the evil difficulty

Pure Python, no pygame: the game imports it, the tests drive it directly.

The evaluation weights are the well-known tuned set from the open-source
expectimax 2048 player (monotonicity / merges / empties / sum); they are
evaluated per line and memoized, so a search of a few thousand nodes costs
a few dozen milliseconds even in Python.
"""

import random

LEFT, RIGHT, UP, DOWN = 0, 1, 2, 3
DIRS = (LEFT, RIGHT, UP, DOWN)
DIR_NAMES = ("left", "right", "up", "down")
NAME_TO_DIR = {n: i for i, n in enumerate(DIR_NAMES)}

# --- evaluation weights ----------------------------------------------------
LOST_PENALTY = 200000.0
MONO_POW = 4.0
MONO_W = 47.0
SUM_POW = 3.5
SUM_W = 11.0
MERGE_W = 700.0
EMPTY_W = 270.0

PROB_FOUR = 0.1          # chance a spawn is a 4
CPROB = 1e-4             # ignore branches less likely than this
NODE_BUDGET = 6000       # rough cap on leaf evaluations per search

_SLIDE = {}              # line -> (slid line, score gained)
_HEUR = {}               # line -> heuristic value
_CACHE_LIMIT = 400000


def _trim_caches():
    if len(_SLIDE) > _CACHE_LIMIT:
        _SLIDE.clear()
    if len(_HEUR) > _CACHE_LIMIT:
        _HEUR.clear()


# ===========================================================================
#  Conversions
# ===========================================================================
def to_ranks(grid):
    """Value grid (list of rows, 0 = empty) -> flat rank tuple, n."""
    n = len(grid)
    out = []
    for row in grid:
        for v in row:
            out.append(v.bit_length() - 1 if v else 0)
    return tuple(out), n


def to_grid(b, n):
    return [[(1 << b[r * n + c]) if b[r * n + c] else 0 for c in range(n)]
            for r in range(n)]


# ===========================================================================
#  Moves
# ===========================================================================
def _slide(line):
    """Slide a line toward index 0, merging equal neighbours once."""
    res = _SLIDE.get(line)
    if res is None:
        vals = [x for x in line if x]
        out = []
        gain = 0
        i = 0
        while i < len(vals):
            if i + 1 < len(vals) and vals[i] == vals[i + 1]:
                out.append(vals[i] + 1)
                gain += 1 << (vals[i] + 1)
                i += 2
            else:
                out.append(vals[i])
                i += 1
        out.extend([0] * (len(line) - len(out)))
        res = (tuple(out), gain)
        _SLIDE[line] = res
    return res


def move(b, n, d):
    """Apply direction d to board b. Returns (new_board, gain).
    new_board is b itself (same object) when nothing moves."""
    gain = 0
    if d == LEFT or d == RIGHT:
        out = []
        for r in range(n):
            row = b[r * n:(r + 1) * n]
            if d == LEFT:
                nl, g = _slide(row)
                out.extend(nl)
            else:
                nl, g = _slide(row[::-1])
                out.extend(nl[::-1])
            gain += g
    else:
        out = [0] * (n * n)
        for c in range(n):
            col = b[c::n]
            if d == UP:
                nl, g = _slide(col)
            else:
                nl, g = _slide(col[::-1])
                nl = nl[::-1]
            out[c::n] = nl
            gain += g
    nb = tuple(out)
    if nb == b:
        return b, 0
    return nb, gain


def legal_moves(b, n):
    out = []
    for d in DIRS:
        nb, _ = move(b, n, d)
        if nb is not b:
            out.append(d)
    return out


def can_move(b, n):
    if 0 in b:
        return True
    for r in range(n):
        for c in range(n):
            v = b[r * n + c]
            if c + 1 < n and b[r * n + c + 1] == v:
                return True
            if r + 1 < n and b[(r + 1) * n + c] == v:
                return True
    return False


def empties(b):
    return [i for i, v in enumerate(b) if v == 0]


# ===========================================================================
#  Evaluation
# ===========================================================================
# rank**3.5 and rank**4 as tables, computed with operations that are exactly
# rounded in every language (products and sqrt), so the browser port
# (brain2049.js) gets bit-identical evaluations
import math as _math
_SUMP = [r * r * r * _math.sqrt(r) for r in range(32)]
_MONOP = [float(r * r * r * r) for r in range(32)]


def _line_heur(line):
    h = _HEUR.get(line)
    if h is None:
        s = 0.0
        empty = 0
        merges = 0
        prev = 0
        counter = 0
        for rank in line:
            s += _SUMP[rank]
            if rank == 0:
                empty += 1
            else:
                if prev == rank:
                    counter += 1
                elif counter > 0:
                    merges += 1 + counter
                    counter = 0
                prev = rank
        if counter > 0:
            merges += 1 + counter
        ml = mr = 0.0
        for i in range(1, len(line)):
            a, c = line[i - 1], line[i]
            if a > c:
                ml += _MONOP[a] - _MONOP[c]
            else:
                mr += _MONOP[c] - _MONOP[a]
        h = (LOST_PENALTY + EMPTY_W * empty + MERGE_W * merges
             - MONO_W * min(ml, mr) - SUM_W * s)
        _HEUR[line] = h
    return h


def heuristic(b, n):
    h = 0.0
    for r in range(n):
        h += _line_heur(b[r * n:(r + 1) * n])
    for c in range(n):
        h += _line_heur(b[c::n])
    return h


# ===========================================================================
#  Expectimax search
# ===========================================================================
class _Search:
    """One search: owns its transposition table and node counter."""

    def __init__(self, n):
        self.n = n
        self.tt = {}
        self.nodes = 0

    def chance(self, b, depth, prob):
        """Expected value of board b right after a move, before the spawn."""
        n = self.n
        if depth <= 0 or prob < CPROB:
            self.nodes += 1
            return heuristic(b, n)
        key = (b, depth)
        v = self.tt.get(key)
        if v is not None:
            return v
        cells = [i for i, x in enumerate(b) if x == 0]
        if not cells:
            self.nodes += 1
            return heuristic(b, n)
        k = len(cells)
        p_cell = prob / k
        total = 0.0
        lst = list(b)
        for i in cells:
            lst[i] = 1
            total += (1 - PROB_FOUR) * self.best(tuple(lst), depth,
                                                 p_cell * (1 - PROB_FOUR))
            lst[i] = 2
            total += PROB_FOUR * self.best(tuple(lst), depth,
                                           p_cell * PROB_FOUR)
            lst[i] = 0
        v = total / k
        self.tt[key] = v
        return v

    def best(self, b, depth, prob):
        """Value of board b with the player to move (0 = no move left)."""
        n = self.n
        best = None
        for d in DIRS:
            nb, _ = move(b, n, d)
            if nb is b:
                continue
            v = self.chance(nb, depth - 1, prob)
            if best is None or v > best:
                best = v
        return 0.0 if best is None else best


def pick_depth(b, n):
    """Search depth that stays within ~50 ms in pure Python (measured with
    cold caches: depth 2 peaks at ~9k nodes on 4x4, ~19k on 5x5, ~27k on 6x6;
    depth 3 is 5-10x more and only pays off on very tight 4x4 boards)."""
    e = b.count(0)
    if n <= 4:
        return 2
    if n == 5:
        return 2 if e <= 10 else 1
    return 2 if e <= 6 else 1


def move_values(b, n, depth=None):
    """{direction: expected value} for every legal move."""
    _trim_caches()
    if depth is None:
        depth = pick_depth(b, n)
    s = _Search(n)
    out = {}
    for d in DIRS:
        nb, _ = move(b, n, d)
        if nb is b:
            continue
        out[d] = s.chance(nb, depth, 1.0)
    return out


def best_move(b, n, depth=None):
    vals = move_values(b, n, depth)
    if not vals:
        return None
    return max(vals, key=vals.get)


def position_value(b, n, depth=1):
    """Value of a position with the player to move."""
    _trim_caches()
    return _Search(n).best(b, depth + 1, 1.0)


# ===========================================================================
#  Survival odds
# ===========================================================================
def survival(b, n, horizon):
    """Probability that the player can still move after `horizon` more
    move+spawn rounds, playing to survive. Exact (no heuristic)."""
    if b.count(0) > horizon:
        return 1.0                       # each round fills at most one cell
    tt = {}

    def best(bb, h):
        if h == 0:
            return 1.0 if can_move(bb, n) else 0.0
        top = 0.0
        for d in DIRS:
            nb, _ = move(bb, n, d)
            if nb is bb:
                continue
            v = chance(nb, h)
            if v > top:
                top = v
                if top >= 1.0:
                    break
        return top

    def chance(bb, h):
        key = (bb, h)
        v = tt.get(key)
        if v is not None:
            return v
        cells = [i for i, x in enumerate(bb) if x == 0]
        if not cells or bb.count(0) > h:
            tt[key] = 1.0
            return 1.0
        lst = list(bb)
        total = 0.0
        for i in cells:
            lst[i] = 1
            total += (1 - PROB_FOUR) * best(tuple(lst), h - 1)
            lst[i] = 2
            total += PROB_FOUR * best(tuple(lst), h - 1)
            lst[i] = 0
        v = total / len(cells)
        tt[key] = v
        return v

    return best(b, horizon)


def harm_unit(max_rank):
    """One 'monotonic step' at the top of the board - harms are measured in
    these units so a 4x4 at 128 and a 6x6 at 4096 read on the same scale."""
    if max_rank < 2:
        return MONO_W
    return MONO_W * (_MONOP[max_rank] - _MONOP[max_rank - 1])


def tile_harms(b, n, depth=1, min_ratio=4):
    """For every low tile (value <= max/min_ratio), how much better the
    position gets if that tile simply vanished: value(without) - value(with),
    both searched `depth` plies deep. Large = the tile is in the way."""
    mx = max(b)
    if mx < 3:
        return []
    base = position_value(b, n, depth)
    out = []
    lst = list(b)
    for i, r in enumerate(b):
        if r == 0 or (1 << r) * min_ratio > (1 << mx):
            continue
        lst[i] = 0
        v = position_value(tuple(lst), n, depth)
        lst[i] = r
        out.append((v - base, i))
    out.sort(reverse=True)
    return out


def move_survival(b, n, horizon):
    """{direction: survival odds after making that move}."""
    out = {}
    for d in DIRS:
        nb, _ = move(b, n, d)
        if nb is b:
            continue
        if nb.count(0) > horizon:
            out[d] = 1.0
            continue
        # after the move comes a spawn, then horizon-1 more rounds
        cells = [i for i, x in enumerate(nb) if x == 0]
        lst = list(nb)
        total = 0.0
        for i in cells:
            lst[i] = 1
            total += (1 - PROB_FOUR) * survival(tuple(lst), n, horizon - 1)
            lst[i] = 2
            total += PROB_FOUR * survival(tuple(lst), n, horizon - 1)
            lst[i] = 0
        out[d] = total / len(cells) if cells else 1.0
    return out


# ===========================================================================
#  Structure: corners, edges, chain breakers, places
# ===========================================================================
def corners(n):
    return (0, n - 1, n * (n - 1), n * n - 1)


def neighbours(i, n):
    r, c = divmod(i, n)
    out = []
    if r > 0:
        out.append(i - n)
    if r < n - 1:
        out.append(i + n)
    if c > 0:
        out.append(i - 1)
    if c < n - 1:
        out.append(i + 1)
    return out


def max_in_corner(b, n):
    mx = max(b)
    return any(b[ci] == mx for ci in corners(n))


def edge_lines(ci, n):
    """The row and the column that run away from corner ci."""
    r, c = divmod(ci, n)
    dc = 1 if c == 0 else -1
    dr = 1 if r == 0 else -1
    row = [r * n + (c + k * dc) for k in range(n)]
    col = [(r + k * dr) * n + c for k in range(n)]
    return row, col


def chain_breaker(b, n, i):
    """True when the low tile at i wrecks the classic corner structure:
    it sits in a corner right next to the biggest tile (it stole the
    corner), or it is a dip inside an edge line that runs from the biggest
    tile's corner (bigger on both sides along that line)."""
    v = b[i]
    mx = max(b)
    if v == 0 or v >= mx:
        return False
    for ci in corners(n):
        if i == ci and any(b[j] == mx for j in neighbours(i, n)):
            return True
        if b[ci] != mx:
            continue
        for line in edge_lines(ci, n):
            if i in line:
                k = line.index(i)
                if 0 < k < n - 1 and b[line[k - 1]] > v and b[line[k + 1]] > v:
                    return True
    return False


def stuck_kind(b, n, i):
    """Why a low tile counts as stuck - in the three situations a player
    recognises at a glance - or None:
      ("block", v):  it sits between two equal tiles of v (>= 4x itself,
                     32+) in its row or column, keeping them from merging
      ("chain", v):  the biggest tile v holds a corner and this tile is a
                     dip in the row/column running out of that corner
      ("corner", v): it occupies a corner right next to the biggest tile v
                     (which is not in a corner itself)
    Reviewing simulated games tip by tip showed that anything else called
    'stuck' - e.g. small tiles around a biggest tile sitting in the middle
    of a messy board - reads as nonsense to a player."""
    v = b[i]
    if v == 0:
        return None
    r, c = divmod(i, n)
    # block: nearest non-empty neighbours on both sides along a line
    for line in ([r * n + k for k in range(n)], [k * n + c for k in range(n)]):
        k = line.index(i)
        left = next((b[j] for j in reversed(line[:k]) if b[j]), 0)
        right = next((b[j] for j in line[k + 1:] if b[j]), 0)
        if left and left == right and left >= v + 2 and left >= 5:
            return ("block", left)
    mx = max(b)
    if v >= mx or mx < 6:
        return None          # corner talk starts at 64 - earlier it is noise
    in_corner = any(b[ci] == mx for ci in corners(n))
    for ci in corners(n):
        if b[ci] != mx:
            continue
        for line in edge_lines(ci, n):
            if i in line:
                k = line.index(i)
                if 0 < k < n - 1 and b[line[k - 1]] > v and b[line[k + 1]] > v:
                    return ("chain", mx)
    if not in_corner and i in corners(n) \
            and any(b[j] == mx for j in neighbours(i, n)):
        # only with ONE top tile: with two of them "the 128's corner" means
        # nothing and joining them comes first (review rounds 3+4: right
        # 74 of 75 times with one top tile, 1 of 3 with two)
        if b.count(mx) == 1:
            return ("corner", mx)
    return None


STUCK_ORDER = {"block": 0, "chain": 1, "corner": 2}


def big_tiles_scattered(b, n):
    """The biggest tile (64+) sits in a corner, but another big tile - at
    least a quarter of it - stands alone, next to no other big tile: the
    big numbers are spread out instead of side by side. From 64 up: early
    in the game is exactly when this habit is formed."""
    mx = max(b)
    if mx < 6 or not max_in_corner(b, n):
        return False
    big = {i for i, v in enumerate(b) if v >= mx - 2}
    if len(big) < 2:
        return False
    return any(not any(j in big for j in neighbours(i, n)) for i in big)


def compose_moves(first, then):
    """The tiles' paths through two moves in a row: {from: (to, merged)}
    maps, as on_move takes them. A tile the first move does not list stayed
    where it was."""
    out = {}
    for cell, (mid, merged) in first.items():
        to, merged2 = then.get(mid, (mid, False))
        out[cell] = (to, merged or merged2)
    for cell, v in then.items():
        if cell not in out and cell not in {mid for mid, _ in first.values()}:
            out[cell] = v
    return out


def place_of(i, n):
    """Where a cell is, in words the UI can localize."""
    r, c = divmod(i, n)
    top, bottom = r == 0, r == n - 1
    left, right = c == 0, c == n - 1
    if top and left:
        return "corner_tl"
    if top and right:
        return "corner_tr"
    if bottom and left:
        return "corner_bl"
    if bottom and right:
        return "corner_br"
    if top:
        return "edge_top"
    if bottom:
        return "edge_bottom"
    if left:
        return "edge_left"
    if right:
        return "edge_right"
    return "middle"


# ===========================================================================
#  Spawn choices (hidden assists)
# ===========================================================================
def best_spawn(b, n, ranks=(1, 2), cells=None, shortlist=8):
    """The spawn (cell, rank) that is best for the PLAYER - what a lucky
    tile would be. Shortlisted by a cheap one-move look, then searched."""
    if cells is None:
        cells = [i for i, x in enumerate(b) if x == 0]
    if not cells:
        return None
    lst = list(b)
    rough = []
    for i in cells:
        for r in ranks:
            lst[i] = r
            nb = tuple(lst)
            top = None
            for d in DIRS:
                mb, _ = move(nb, n, d)
                if mb is nb:
                    continue
                h = heuristic(mb, n)
                if top is None or h > top:
                    top = h
            rough.append((-1e18 if top is None else top, i, r))
            lst[i] = 0
    rough.sort(reverse=True)
    best = None
    for _, i, r in rough[:shortlist]:
        lst[i] = r
        v = position_value(tuple(lst), n, 1)
        lst[i] = 0
        if best is None or v > best[0]:
            best = (v, i, r)
    return best[1], best[2]


# ===========================================================================
#  Analysis: everything the game wants to know about one settled position
# ===========================================================================
DANGER_ENTER = 0.85     # survive the next 3 rounds with < 85% -> danger
DANGER_EXIT = 0.97      # ...and it is over only once we are back above 97%
HORIZON = 3
TRAP_T = 0.5            # a move that survives 3 rounds less than half the time
CHEAT_T = 0.25         # a tile worth removing (harm units)
CHAIN_T = 0.5           # a chain breaker this harmful counts as stuck
STUCK_T = 1.2           # anything this harmful counts as stuck


class Analysis:
    """One settled position, analysed once. Cheap to keep around."""

    def __init__(self, b, n, harms=True):
        self.b = b
        self.n = n
        self.max_rank = max(b)
        self.empties = b.count(0)
        self.unit = harm_unit(self.max_rank)
        self.values = move_values(b, n)
        self.best = (max(self.values, key=self.values.get)
                     if self.values else None)
        if self.values and self.empties <= HORIZON:
            self.safety = move_survival(b, n, HORIZON)
            self.survival = max(self.safety.values())
        else:
            self.safety = {d: 1.0 for d in self.values}
            self.survival = 1.0 if self.values else 0.0
        # moves that very likely end the game while a safer one exists:
        # measured on simulated human games, this is how nearly every game
        # is lost - one deadly move played next to a perfectly safe one
        self.deadly = sorted(d for d, s in self.safety.items()
                             if s < TRAP_T and self.survival >= TRAP_T)
        self.corner = max_in_corner(b, n)
        self.harms = []
        if harms:
            self.harms = [(h / self.unit, i) for h, i in tile_harms(b, n, 1)]
        self.harm_at = {i: h for h, i in self.harms}
        self.problems = {i for h, i in self.harms if h >= CHEAT_T}
        # "stuck" (what a tip may call stuck): a tile that really hurts
        # (harm) AND sits in one of the three situations a player sees at a
        # glance (stuck_kind). Chain/corner cases are for clearly low tiles,
        # at most 1/8 of the top tile; the assist may still take up to 1/4.
        low = self.max_rank - 3
        self.stuck_info = {}
        for h, i in self.harms:
            if h < CHAIN_T:
                continue
            kind = stuck_kind(b, n, i)
            if kind is None:
                continue
            if kind[0] != "block" and b[i] > low:
                continue
            self.stuck_info[i] = kind
        self.stuck = set(self.stuck_info)

    @classmethod
    def of_grid(cls, grid, harms=True):
        b, n = to_ranks(grid)
        return cls(b, n, harms)

    @property
    def problem(self):
        """The tile a 'clear stuck tile' assist should remove, or None."""
        if self.harms and self.harms[0][0] >= CHEAT_T:
            return self.harms[0][1]
        return None

    def safest(self):
        """Best move by survival first, then by value."""
        if not self.values:
            return None
        return max(self.values,
                   key=lambda d: (round(self.safety.get(d, 1.0), 6),
                                  self.values[d]))

    def regret(self, d):
        if d not in self.values or self.best is None:
            return 0.0
        return (self.values[self.best] - self.values[d]) / self.unit

    def keeps_corner(self, d):
        nb, _ = move(self.b, self.n, d)
        return nb is not self.b and max_in_corner(nb, self.n)

    def brings_max_to_corner(self, d):
        """d moves an EXISTING top tile into a corner - not a merge that
        makes a new one there (a review game showed 'you can get your 64
        back' where only two 32s could make another 64 in the corner)."""
        nb, _ = move(self.b, self.n, d)
        mx = self.max_rank
        return (nb is not self.b and max(nb) == mx
                and nb.count(mx) == self.b.count(mx) and max_in_corner(nb, self.n))


# ===========================================================================
#  Coach: turns analyses into a few well-timed, true, concrete tips
# ===========================================================================
class Tip:
    """A tip the UI shows. `key` picks the localized template, `params`
    fills it. Validity is re-checked after every move; the UI also enforces
    min/max seconds."""
    __slots__ = ("key", "params", "prio", "born", "max_moves", "kind",
                 "track", "max_secs")

    def __init__(self, key, prio, born, params=None, max_moves=4,
                 kind="warn", track=None, max_secs=6.0):
        self.key = key
        self.params = params or {}
        self.prio = prio
        self.born = born
        self.max_moves = max_moves
        self.kind = kind
        self.track = track
        self.max_secs = max_secs

    def __repr__(self):
        return "Tip(%s, %r)" % (self.key, self.params)


PRIO_OPEN, PRIO_PRAISE, PRIO_HINT, PRIO_CORNER, PRIO_STUCK, PRIO_DANGER = \
    range(6)

COOLDOWN = {             # moves between two tips of the same key
    "stuck": 8, "tip_corner_lost": 6, "tip_corner_made": 6,
    "tip_corner_goal": 20, "tip_good_escape": 10, "tip_good_freed": 6,
    "tip_good_corner": 20, "tip_good_record": 0, "tip_danger": 0,
    "tip_hint_order": 40, "tip_hint_dirs": 40,
}
RECORD_RANK = 8          # praise new records from 256 up
OFF_CORNER_MOVES = 4     # biggest tile out of a corner this long -> corner tip
# Corner tips name no move: the move itself is often a close call that a
# much deeper search (tools/referee.js) decides differently. What the coach
# is sure of is the SITUATION - so that is what they say, and only when:
LOST_MARGIN = 0.25       # leaving the corner cost at least this much (harm
                         # units) against the best move that kept it
GOAL_REGRET = 0.15       # "you can get it back now": some move does it, is
                         # not deadly, and costs at most this against the best
# Both measured, not guessed (tools/calib_corner.py + .js, 19.11.2026: 130
# corner exits and 86 chances to return, from brand-new games, each judged
# by deep search AND paired play-outs). Exits blamed at a cost >= 0.25: the
# referee never found leaving had been better (the one such case: 0.15).
# Returns offered at <= 0.15: never clearly worse than the best move; the
# clearly worse ones started at 0.19.
STUCK_KEYS = ("tip_stuck_block", "tip_stuck_chain", "tip_stuck_corner")
SCATTER_MOVES = 3        # big tiles spread out this long -> the general tip
DIRS_WINDOW = 12         # "all four directions in turn": the last 12 moves...
DIRS_EACH = 2            # ...use every direction at least twice
GOAL_RANK = 5            # "you can get it back into a corner" from 32 up
OPEN_KEEP = 0.7          # the corner habit the opening tip asks for: kept for
                         # at least this share of the last game -> not repeated
# Pacing. Review games (19.11) gave a careful player a tip every 12 moves
# and the same "left the corner" every 6 moves to someone who keeps doing
# it: right each time, but a good coach does not repeat himself. So each
# repeat of a key in a game doubles its cooldown (x2, x4, at most x8), and
# two non-urgent tips are at least GAP moves apart. Danger, traps and a new
# record are never held back.
GAP = 5
URGENT = ("tip_danger", "tip_trap", "tip_good_record")
URGENT_BOARD = ("tip_danger", "tip_trap")    # about the board on screen only


class Coach:
    def __init__(self):
        self.opened = False          # the opening tip was shown this session
        self.habit = None            # share of the last game the top tile kept a corner
        self.reset()

    def reset(self):
        self.move_no = 0
        self.last = {}
        self.times = {}              # key -> tips of that key so far this game
        self.last_any = None         # move of the last non-urgent tip
        self.prev = None
        self.track = {}              # cell -> {"age", "told"}
        self.danger = False
        self.corner_told = None      # move number of the last corner tip
        self.off_corner = 0          # moves the biggest tile spent off a corner
        self.scattered = 0           # moves the big tiles stayed spread out
        self.recent_dirs = []        # directions of the last DIRS_WINDOW moves
        self.corner_moves = 0        # moves (top tile 32+) with it in a corner
        self.counted_moves = 0       # moves (top tile 32+) counted at all
        self.current = None

    # ---- lifecycle ------------------------------------------------------
    def new_game(self, analysis):
        # how the last game went: a player who already keeps the corner is
        # not told again; one who does not, is - at the start of every game,
        # where this matters most
        if self.counted_moves >= 20:
            self.habit = self.corner_moves / self.counted_moves
        self.reset()
        self.prev = analysis
        if not self.opened or self.habit is None or self.habit < OPEN_KEEP:
            self.opened = True
            self.current = Tip("tip_open", PRIO_OPEN, 0, max_moves=5,
                               kind="info", max_secs=7.0)

    def resync(self, analysis):
        """After an assist / undo, or a burst of moves too fast to analyse
        one by one: adopt the board, never praise. Tiles cannot be followed
        across the gap - but danger and traps depend on THIS board alone,
        and the pause after a burst is exactly when a warning helps (found
        playing fast in the browser: the coach used to stay silent here)."""
        self.prev = analysis
        self.track = {}
        self.danger = analysis.survival < DANGER_ENTER
        if self.current is not None and (self.current.key in URGENT_BOARD or
                                         not self.is_valid(self.current, analysis)):
            self.current = None          # warnings are re-derived from THIS board
        if not analysis.values:
            return
        if self.danger:
            tip = Tip("tip_danger", PRIO_DANGER, self.move_no,
                      {"dir": analysis.safest()}, max_moves=1, max_secs=8.0)
        elif analysis.deadly:
            tip = Tip("tip_trap", PRIO_DANGER, self.move_no,
                      {"dir": analysis.safest(), "bad": analysis.deadly},
                      max_moves=0, max_secs=10.0)
        else:
            return
        cur = self.current
        if cur is None or cur.key != tip.key or cur.params != tip.params:
            self.current = tip

    def dismiss(self):
        """The UI took the tip down (its time ran out)."""
        self.current = None

    def _ready(self, key):
        key = "stuck" if key in STUCK_KEYS else key
        last = self.last.get(key)
        cd = COOLDOWN.get(key, 5) << min(3, max(0, self.times.get(key, 0) - 1))
        if last is not None and self.move_no - last < cd:
            return False
        return key in URGENT or self.last_any is None \
            or self.move_no - self.last_any >= GAP

    # ---- validity -------------------------------------------------------
    def is_valid(self, tip, a):
        if self.move_no - tip.born > tip.max_moves:
            return False
        k = tip.key
        if k == "tip_danger":
            return a.survival < DANGER_EXIT and tip.params["dir"] in a.values
        if k == "tip_trap":
            return self.move_no == tip.born and tip.params["dir"] in a.values
        if k in STUCK_KEYS:
            return tip.track is not None and tip.track in a.problems
        if k == "tip_hint_order":
            return big_tiles_scattered(a.b, a.n)
        if k in ("tip_corner_lost", "tip_corner_made"):
            return not a.corner
        if k == "tip_corner_goal":
            return not a.corner and bool(self._ways_back(a))
        return True

    @staticmethod
    def _ways_back(a):
        """Moves that put the biggest tile into a corner at a fair price
        (only with ONE top tile - see stuck_kind)."""
        if a.b.count(a.max_rank) != 1:
            return []
        return [x for x in a.values if a.brings_max_to_corner(x)
                and x not in a.deadly and a.regret(x) <= GOAL_REGRET]

    # ---- the per-move step ---------------------------------------------
    def on_move(self, d, moved, a, cheated=False, steps=1, dirs=None):
        """d: direction played on self.prev; moved: {from_cell: (to_cell,
        merged)} for every tile of that move; a: analysis after the spawn.
        A burst of moves too fast to analyse one by one arrives as ONE call:
        steps = how many moves, dirs = their directions, moved = the tiles'
        paths through all of them (compose_moves). Everything about the
        board works the same; only the tips about one particular move (the
        corner just lost or a tile made outside it) need steps == 1.
        Returns the tip to show now (may be the same object as before)."""
        p = self.prev
        self.move_no += steps
        m = self.move_no
        cands = []
        self.recent_dirs = (self.recent_dirs + list(dirs or [d]))[-DIRS_WINDOW:]
        if a.max_rank >= GOAL_RANK:
            self.counted_moves += steps
            if a.corner:
                self.corner_moves += steps

        # -- stuck tracking, through the move --------------------------------
        new_track = {}
        freed = None
        for cell, t in self.track.items():
            to, merged = moved.get(cell, (cell, False))
            if to in a.problems:
                nt = dict(t)
                nt["age"] = t["age"] + 1
                if to in new_track:              # two tracks merged
                    nt["told"] = nt["told"] or new_track[to]["told"]
                new_track[to] = nt
            elif t["told"] and merged and not cheated:
                freed = (to, t.get("kind"))      # the player merged it away
        for cell in sorted(a.stuck):             # sorted: same order as the JS port
            if cell not in new_track:
                new_track[cell] = {"age": 0, "told": False}
            new_track[cell]["kind"] = a.stuck_info[cell][0]
        self.track = new_track
        self.off_corner = 0 if a.corner else self.off_corner + steps
        self.scattered = self.scattered + steps if big_tiles_scattered(a.b, a.n) else 0

        # -- danger ------------------------------------------------------------
        was_danger = self.danger
        if a.survival < DANGER_ENTER:
            self.danger = True
        elif a.survival >= DANGER_EXIT:
            self.danger = False
        if self.danger and a.values:
            cands.append(Tip("tip_danger", PRIO_DANGER, m,
                             {"dir": a.safest()}, max_moves=1, max_secs=8.0))
        elif a.deadly:
            cands.append(Tip("tip_trap", PRIO_DANGER, m,
                             {"dir": a.safest(), "bad": a.deadly},
                             max_moves=0, max_secs=10.0))
        elif was_danger and not self.danger and not cheated \
                and self._ready("tip_good_escape"):
            cands.append(Tip("tip_good_escape", PRIO_PRAISE, m, max_moves=2,
                             kind="praise", max_secs=3.5))

        # -- a stuck tile that stayed stuck (not a one-move flicker), and
        #    not right on the heels of a corner tip about the same trouble --
        corner_quiet = self.corner_told is not None and m - self.corner_told <= 3
        if self._ready("stuck") and not corner_quiet:
            best_cell = None
            def rank(cell):
                return (STUCK_ORDER[a.stuck_info[cell][0]], -a.harm_at.get(cell, 0))
            for cell, t in self.track.items():
                if t["age"] >= 1 and not t["told"] and cell in a.stuck:
                    if best_cell is None or rank(cell) < rank(best_cell):
                        best_cell = cell
            if best_cell is not None:
                kind, big = a.stuck_info[best_cell]
                cands.append(Tip("tip_stuck_" + kind, PRIO_STUCK, m,
                                 {"value": 1 << a.b[best_cell], "big": 1 << big,
                                  "place": place_of(best_cell, a.n)},
                                 max_moves=6, track=best_cell))

        # -- the biggest tile left its corner ---------------------------------
        if p is not None and p.corner and not a.corner \
                and a.max_rank >= 6 and d in p.values and steps == 1:
            # blamed only when it was avoidable AND it mattered: a move that
            # kept the corner was clearly better. A forced or sensible exit
            # gets no tip at all.
            # If this very move MADE the biggest tile (a merge), it was never
            # in the corner: it was built outside it - say that, not "left".
            key = "tip_corner_made" if a.max_rank > p.max_rank else "tip_corner_lost"
            # With two top tiles, leaving the corner to join them is often
            # right (review rounds 3+4: 'left the corner' was right 65 of 71
            # times with one top tile, 4 of 8 with two) - so only then. A
            # tile just MADE from two is one tile: that case stays.
            keep = [x for x in p.values if x != d and p.keeps_corner(x)]
            if key == "tip_corner_lost" and p.b.count(p.max_rank) != 1:
                keep = []
            if keep and self._ready(key) and \
                    (max(p.values[x] for x in keep) - p.values[d]) / p.unit >= LOST_MARGIN:
                cands.append(Tip(key, PRIO_CORNER, m,
                                 {"value": 1 << a.max_rank}, max_moves=3))
        elif not a.corner and a.max_rank >= GOAL_RANK \
                and self.off_corner >= OFF_CORNER_MOVES \
                and (self.corner_told is None or m - self.corner_told > 8) \
                and self._ready("tip_corner_goal"):
            # out of a corner for a while, and right now one move brings it
            # back at a fair price: the moment to say so
            if self._ways_back(a):
                cands.append(Tip("tip_corner_goal", PRIO_CORNER, m,
                                 {"value": 1 << a.max_rank}, max_moves=2))
        elif p is not None and not p.corner and a.corner \
                and self.corner_told is not None \
                and m - self.corner_told <= 6 and not cheated \
                and self._ready("tip_good_corner"):
            cands.append(Tip("tip_good_corner", PRIO_PRAISE, m,
                             {"value": 1 << a.max_rank}, max_moves=2,
                             kind="praise", max_secs=3.5))

        # -- a general tip, when the board shows exactly what it is about:
        #    big tiles spread out (not a passing moment of a merge), and the
        #    player is not in trouble right now
        if self.scattered >= SCATTER_MOVES and not self.danger and not a.deadly \
                and self._ready("tip_hint_order"):
            cands.append(Tip("tip_hint_order", PRIO_HINT, m, max_moves=4,
                             kind="info", max_secs=6.0))
        # ...and the beginner's habit behind most lost corners: every one of
        # the four directions in turn (each at least twice in the last 12
        # moves). Pick one and leave it alone, and the corner holds.
        elif len(self.recent_dirs) >= DIRS_WINDOW and a.max_rank >= 4 \
                and min(self.recent_dirs.count(x) for x in DIRS) >= DIRS_EACH \
                and not self.danger and not a.deadly and self._ready("tip_hint_dirs"):
            cands.append(Tip("tip_hint_dirs", PRIO_HINT, m, max_moves=4,
                             kind="info", max_secs=6.0))

        # -- earned praise --------------------------------------------------------
        # freed: only for a blocker / chain breaker, and only if the board
        # really is in shape afterwards (the review caught praise for moves
        # that had just wrecked the structure)
        if freed is not None and freed[1] in ("block", "chain") and a.corner \
                and not a.deadly and self._ready("tip_good_freed"):
            cands.append(Tip("tip_good_freed", PRIO_PRAISE, m,
                             max_moves=2, kind="praise", max_secs=3.5))
        if p is not None and a.max_rank > p.max_rank \
                and a.max_rank >= RECORD_RANK and not cheated:
            cands.append(Tip("tip_good_record", PRIO_PRAISE, m,
                             {"value": 1 << a.max_rank}, max_moves=2,
                             kind="praise", max_secs=3.5))

        # -- choose ----------------------------------------------------------------
        cur = self.current
        if cur is not None and cur.track is not None:
            cur.track = moved.get(cur.track, (cur.track, False))[0]
        if cur is not None and not self.is_valid(cur, a):
            cur = None
        if not a.values:                 # game over: the board says it all
            cands, cur = [], None
        if cands:
            top = max(cands, key=lambda t: t.prio)
            if cur is None or top.prio >= cur.prio:
                if not (cur is not None and cur.key == top.key
                        and cur.params == top.params):
                    cur = top
                    k = "stuck" if top.key in STUCK_KEYS else top.key
                    self.last[k] = m
                    self.times[k] = self.times.get(k, 0) + 1
                    if k not in URGENT:
                        self.last_any = m
                    if top.key in STUCK_KEYS:
                        self.track[top.track]["told"] = True
                    if top.key in ("tip_corner_lost", "tip_corner_made",
                                   "tip_corner_goal"):
                        self.corner_told = m
        self.current = cur
        self.prev = a
        return cur
