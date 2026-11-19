# -*- coding: utf-8 -*-
"""Drive the NEW coach (brain2049.Coach) with the same human-paced simulated
player as diag_tips.py, and judge every on-screen tip against the truth of
the current board. Also times the per-move analysis."""
import collections
import math
import random
import sys
import time

from diag_common import B, policy_corner_human, policy_lazy_corner, show

N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
GAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 8
FOLLOW = len(sys.argv) > 3 and sys.argv[3] == 'follow'
DT = 1 / 30


def moved_map(b, n, d):
    """{from_cell: (to_cell, merged)} for one move, like the game's anims."""
    out = {}
    lines = []
    for k in range(n):
        if d == B.LEFT:
            lines.append([k * n + j for j in range(n)])
        elif d == B.RIGHT:
            lines.append([k * n + j for j in range(n - 1, -1, -1)])
        elif d == B.UP:
            lines.append([j * n + k for j in range(n)])
        else:
            lines.append([j * n + k for j in range(n - 1, -1, -1)])
    for cells in lines:
        ent = [(b[c], c) for c in cells if b[c]]
        dest = 0
        i = 0
        while i < len(ent):
            if i + 1 < len(ent) and ent[i][0] == ent[i + 1][0]:
                out[ent[i][1]] = (cells[dest], True)
                out[ent[i + 1][1]] = (cells[dest], True)
                i += 2
            else:
                out[ent[i][1]] = (cells[dest], False)
                i += 1
            dest += 1
    return out


def truth(tip, a, age_m, age_s):
    k = tip.key
    if k == "tip_danger":
        d = tip.params["dir"]
        return (a.survival < B.DANGER_EXIT and d in a.safety
                and a.safety[d] >= max(a.safety.values()) - 0.02)
    if k == "tip_trap":
        d = tip.params["dir"]
        return age_m == 0 and d in a.safety and bool(a.deadly)
    if k == "tip_stuck":
        return a.harm_at.get(tip.track, 0) >= B.CHEAT_T
    if k in ("tip_corner_lost", "tip_corner_back"):
        return not a.corner
    if tip.kind == "praise":
        return age_m <= 2 and age_s <= 4.0
    if k == "tip_better":
        return age_m == 0
    if k == "tip_open":
        return age_m <= 5
    return True


def main():
    rng = random.Random(11)
    pace = lambda: (min(12.0, rng.lognormvariate(math.log(0.65), 0.6))
                    + (rng.random() < 0.06) * rng.uniform(2, 8))
    stats = collections.Counter()
    per = collections.defaultdict(collections.Counter)
    times = []
    examples = []
    for gi in range(GAMES):
        grng = random.Random(100 + gi)
        pol = policy_corner_human if gi % 2 == 0 else policy_lazy_corner
        b = tuple([0] * (N * N))
        from diag_common import spawn
        b = spawn(b, N, grng)
        b = spawn(b, N, grng)
        coach = B.Coach()
        a = B.Analysis(b, N)
        coach.new_game(a)
        shown = coach.current
        shown_at = 0.0
        born_move = 0
        clock = 0.0
        moves = 0
        while a.values and moves < 900:
            d = pol(b, N, rng)
            if FOLLOW and shown is not None and shown.key in ('tip_danger', 'tip_trap'):
                d = shown.params['dir']
            mm = moved_map(b, N, d)
            b, _ = B.move(b, N, d)
            b = spawn(b, N, grng)
            moves += 1
            t0 = time.perf_counter()
            a = B.Analysis(b, N)
            times.append(time.perf_counter() - t0)
            tip = coach.on_move(d, mm, a)
            if tip is not shown:
                shown = tip
                shown_at = clock
                born_move = moves
                if tip is not None:
                    stats["tips"] += 1
                    per[tip.key]["shown"] += 1
            if a.values and (a.survival < B.DANGER_ENTER or a.deadly):
                stats["danger_moves"] += 1
                if shown is not None and shown.key in ("tip_danger",
                                                       "tip_trap"):
                    stats["danger_covered"] += 1
                    # would a player who follows the tip survive this move?
                    sd = shown.params["dir"]
                    if a.safety.get(sd, 0) >= max(a.safety.values()) - 1e-9:
                        stats["tip_points_to_safest"] += 1
            step = pace()
            t = 0.0
            while t < step:
                if shown is not None and clock - shown_at > shown.max_secs:
                    coach.dismiss()
                    shown = None
                if shown is not None:
                    age_m = moves - born_move
                    ok = truth(shown, a, age_m, clock - shown_at)
                    stats["frames"] += 1
                    per[shown.key]["frames"] += 1
                    if not ok:
                        stats["stale"] += 1
                        per[shown.key]["stale"] += 1
                        if len(examples) < 50:
                            examples.append((shown, age_m, show(b, N)))
                t += DT
                clock += DT
        stats["moves"] += moves
        stats["sum_max_tile"] += 1 << max(b)
    print(dict(stats))
    print("stale share of tip screen time: %.1f%%"
          % (100 * stats["stale"] / max(1, stats["frames"])))
    print("danger moves with the danger tip up: %.0f%%"
          % (100 * stats["danger_covered"] / max(1, stats["danger_moves"])))
    print("tips per 100 moves: %.1f" % (100 * stats["tips"] / stats["moves"]))
    for k, c in sorted(per.items()):
        fr = max(1, c["frames"])
        print("%-18s shown %4d  stale %5.1f%%" % (k, c["shown"],
                                                  100 * c["stale"] / fr))
    ts = sorted(times)
    print("analysis ms: p50 %.1f  p95 %.1f  max %.1f" % (
        1000 * ts[len(ts) // 2], 1000 * ts[int(len(ts) * .95)], 1000 * ts[-1]))
    for tip, age, txt in examples[:3]:
        print("\n-- stale %r, %d moves old\n%s" % (tip, age, txt))


if __name__ == "__main__":
    main()
