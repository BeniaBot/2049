# -*- coding: utf-8 -*-
"""Drive the v0.17 tip engine with a human-paced simulated player and
measure how often the tip on screen is stale / irrelevant."""
import random, sys, collections, math, tempfile, os
from diag_common import B, load_game, policy_corner_human, policy_lazy_corner, show

g = load_game(sys.argv[1] if len(sys.argv) > 1 else None)
g.save_config = lambda cfg: None
g.CONFIG_PATH = os.path.join(tempfile.mkdtemp(), "x.json")
g.Game._start_update_check = lambda self: None
game = g.Game()
game.cfg["show_tips"] = True
DT = 1 / 60
EN = g.STRINGS["en"]
key_of_text = {v: k for k, v in EN.items() if isinstance(v, str)}
for i, t in enumerate(EN["tips_list"]):
    key_of_text[t] = "general_%d" % i
game.cfg["language"] = "en"

def facts(board):
    n = board.size
    b, _ = B.to_ranks(board.grid)
    harms = B.tile_harms(b, n, 1)
    mx = max(b)
    unit = B.MONO_W * (mx ** 4 - (mx - 1) ** 4) if mx > 1 else 1
    return dict(corner=board.max_in_corner(), danger=board.in_danger(),
                empties=len(board.empty_cells()), total=n * n,
                stuck_engine=bool(harms and harms[0][0] / unit >= 1.5),
                ordered=board.edge_ordered(), mx=board.max_tile())

def valid(key, f, age_moves):
    if key == "tip_full": return f["danger"] or f["empties"] <= 2
    if key == "tip_stuck": return f["stuck_engine"]
    if key in ("tip_lost_corner", "tip_corner"): return not f["corner"]
    if key.startswith("tip_good"): return age_moves <= 2   # praise is about THIS move
    if key == "general_4": return f["empties"] <= f["total"] * 0.3
    if key == "general_0": return True
    if key == "general_1": return f["corner"] and not f["ordered"]
    if key == "general_2": return f["corner"]
    if key == "general_3": return age_moves <= 30
    return True

rng = random.Random(11)
pace = lambda: min(12.0, rng.lognormvariate(math.log(0.65), 0.6)) + (rng.random() < 0.06) * rng.uniform(2, 8)
stats = collections.Counter(); per_key = collections.defaultdict(lambda: collections.Counter())
examples = []
for gi in range(8):
    random.seed(100 + gi)
    game.new_game()
    pol = policy_corner_human if gi % 2 == 0 else policy_lazy_corner
    moves = 0; cur = None
    while game.board.can_move() and moves < 900:
        b, n = B.to_ranks(game.board.grid)
        d = pol(b, n, rng)
        if d is None: break
        changed, _, _ = game.board.move(B.DIR_NAMES[d])
        game.board.spawn()
        moves += 1
        game._move_no += 1
        game._refresh_board_facts(); game._check_tip_events()
        f = facts(game.board)
        t = pace(); steps = int(t / DT)
        for s in range(steps):
            game._update_tips(DT)
            if game._tip_now:
                txt = game._tip_now[0]; key = key_of_text.get(txt, "?")
                if cur is None or cur[0] != txt:
                    cur = (txt, moves); stats["tips_shown"] += 1; per_key[key]["shown"] += 1
                    if s > 0: per_key[key]["idle_fired"] += 1
                age = moves - cur[1]
                ok = valid(key, f, age)
                stats["frames_on"] += 1; per_key[key]["frames"] += 1
                if not ok:
                    stats["frames_stale"] += 1; per_key[key]["stale_frames"] += 1
                    if len(examples) < 400: examples.append((key, age, show(b := B.to_ranks(game.board.grid)[0], n)))
                if age >= 3: per_key[key]["frames_age3+"] += 1
            else:
                cur = None
        stats["moves"] += 1
        if f["danger"]: stats["danger_moves"] += 1
print(dict(stats))
print("stale share of tip screen time: %.0f%%" % (100 * stats["frames_stale"] / max(1, stats["frames_on"])))
for k, c in sorted(per_key.items()):
    fr = max(1, c["frames"])
    print(f"{k:18s} shown {c['shown']:4d}  (fired while idle {c['idle_fired']:3d})  stale {100*c['stale_frames']/fr:5.1f}%  still up 3+ moves later {100*c['frames_age3+']/fr:5.1f}%")
rng2 = random.Random(5)
for key, age, txt in rng2.sample(examples, min(4, len(examples))):
    print(f"\n-- stale '{key}' shown {age} moves after it fired:\n{txt}")
