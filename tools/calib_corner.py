# -*- coding: utf-8 -*-
"""Collect the moments the corner tips are about, from brand-new games,
with what the game's own brain thinks of each; tools/calib_corner.js then
asks the deep referee the same question. Together they show where the
coach's thresholds (LOST_MARGIN, GOAL_REGRET) must sit for its corner tips
to be right.

    python tools/calib_corner.py OUT.jsonl [games_per_policy] [seed] [size]

  lost: the biggest tile just left its corner although another move kept
        it there -> gain = how much better (harm units) the best keeping
        move was than the move played, by the game's brain
  goal: the biggest tile has been out of a corner for 4+ moves and some
        move puts it back -> cost = regret of the best such move
"""
import json
import os
import random
import sys

from diag_common import B, spawn, policy_corner_human, policy_lazy_corner, policy_noisy

OUT = sys.argv[1]
GAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 4
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 1
N = int(sys.argv[4]) if len(sys.argv) > 4 else 4

policies = [("careful", policy_corner_human), ("habit", policy_lazy_corner),
            ("casual", policy_noisy(0.55))]
out = open(OUT, "w", encoding="utf-8")
counts = {"lost": 0, "goal": 0}
for pname, pol in policies:
    for gi in range(GAMES):
        rng = random.Random(SEED * 7919 + gi * 31 + len(pname))
        b = spawn(spawn(tuple([0] * N * N), N, rng), N, rng)
        off = 0
        moves = 0
        while B.can_move(b, N) and moves < 3000:
            a = B.Analysis(b, N, harms=False)
            if not a.corner and a.max_rank >= 6 and off >= B.OFF_CORNER_MOVES:
                into = [x for x in a.values if a.keeps_corner(x) and x not in a.deadly]
                if into:
                    gd = min(into, key=a.regret)
                    out.write(json.dumps({"type": "goal", "b": list(b), "n": N,
                                          "rec": gd, "cost": a.regret(gd),
                                          "policy": pname}) + "\n")
                    counts["goal"] += 1
            d = pol(b, N, rng)
            if d is None:
                break
            nb, _ = B.move(b, N, d)
            if a.corner and not B.max_in_corner(nb, N) and a.max_rank >= 6:
                keep = [x for x in a.values if x != d and a.keeps_corner(x)]
                if keep:
                    k = max(keep, key=lambda x: a.values[x])
                    out.write(json.dumps({"type": "lost", "b": list(b), "n": N,
                                          "played": d, "keep": k,
                                          "gain": (a.values[k] - a.values[d]) / a.unit,
                                          "policy": pname}) + "\n")
                    counts["lost"] += 1
            b = spawn(nb, N, rng)
            off = 0 if B.max_in_corner(b, N) else off + 1
            moves += 1
out.close()
print(counts)
