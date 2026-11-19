# -*- coding: utf-8 -*-
"""Shared helpers for the engine diagnostics: load the game module headless,
generate realistic game states with human-like play."""
import importlib.util, os, random, sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import brain2049 as B


def load_game(path=None):
    path = path or os.path.join(ROOT, "2049.py")
    spec = importlib.util.spec_from_file_location("game2049", path)
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


def spawn(b, n, rng):
    cells = [i for i, x in enumerate(b) if x == 0]
    if not cells:
        return b
    i = rng.choice(cells)
    l = list(b)
    l[i] = 2 if rng.random() < 0.1 else 1
    return tuple(l)


def policy_lazy_corner(b, n, rng):
    """The classic casual habit: down, left, right - up only when forced."""
    for d in (B.DOWN, B.LEFT, B.RIGHT, B.UP):
        nb, _ = B.move(b, n, d)
        if nb is not b:
            return d
    return None


def policy_noisy(skill):
    def pol(b, n, rng):
        legal = B.legal_moves(b, n)
        if not legal:
            return None
        if rng.random() < skill:
            return B.best_move(b, n, 1)
        return rng.choice(legal)
    return pol


def policy_corner_human(b, n, rng):
    """A decent human: keeps the corner (down/left) unless the engine sees a
    clearly better move; sometimes slips."""
    legal = B.legal_moves(b, n)
    if not legal:
        return None
    if rng.random() < 0.15:
        return rng.choice(legal)
    vals = B.move_values(b, n, 1)
    best = max(vals, key=vals.get)
    for d in (B.DOWN, B.LEFT):
        if d in vals and vals[d] >= vals[best] - 2000:
            return d
    return best


def play_states(n, policy, seed, every=1, max_moves=4000):
    """Yield (move_no, board) after each settled move of one game."""
    rng = random.Random(seed)
    b = tuple([0] * (n * n))
    b = spawn(b, n, rng)
    b = spawn(b, n, rng)
    mv = 0
    while B.can_move(b, n) and mv < max_moves:
        d = policy(b, n, rng)
        if d is None:
            break
        b, _ = B.move(b, n, d)
        b = spawn(b, n, rng)
        mv += 1
        if mv % every == 0:
            yield mv, b


def show(b, n, marks=()):
    lines = []
    for r in range(n):
        cells = []
        for c in range(n):
            v = b[r * n + c]
            s = str(1 << v) if v else "."
            if (r * n + c) in marks:
                s = "[" + s + "]"
            cells.append(s.rjust(6))
        lines.append("".join(cells))
    return "\n".join(lines)
