# -*- coding: utf-8 -*-
"""Compare the v0.17 stuck detector with the engine's harm measure on
realistic states. Prints distributions and examples."""
import random, sys, collections
from diag_common import B, load_game, play_states, policy_lazy_corner, \
    policy_noisy, policy_corner_human, show

g = load_game()
pols = {"lazy": policy_lazy_corner, "human": policy_corner_human,
        "noisy": policy_noisy(0.7)}
rows = []
for pname, pol in pols.items():
    for seed in range(6):
        for mv, b in play_states(4, pol, seed * 7 + 1):
            if mv < 20 or mv % 3:
                continue
            n = 4
            grid = B.to_grid(b, n)
            ob = g.Board(n); ob.grid = [r[:] for r in grid]
            old = ob.remove_stuck_low()
            harms = B.tile_harms(b, n, 1)
            mx = max(b)
            rows.append((pname, mv, b, old, harms, mx))
print("states:", len(rows))
by = collections.Counter()
for pname, mv, b, old, harms, mx in rows:
    top = harms[0][0] if harms else 0
    by[(pname, old is not None)] += 1
print(by)
# distribution of top harm per max tile
dist = collections.defaultdict(list)
for pname, mv, b, old, harms, mx in rows:
    if harms:
        dist[mx].append(harms[0][0])
for mx in sorted(dist):
    v = sorted(dist[mx]); k = len(v)
    print("max", 1 << mx, "n", k, "p25 %.0f p50 %.0f p75 %.0f p90 %.0f p97 %.0f" % (
        v[k//4], v[k//2], v[3*k//4], v[int(k*.9)], v[int(k*.97)]))
import pickle
pickle.dump(rows, open(sys.argv[1] if len(sys.argv) > 1 else "stuck_rows.pkl", "wb"))
