# -*- coding: utf-8 -*-
"""How many tips does a player see at a HUMAN tempo? The real Game, keys
at human intervals (not waiting for the brain between moves - review_tips
does that, and so it never sees what a real player sees), counting every
tip that reaches the screen.

    python tools/tempo_tips.py OUT_DIR [games] [seed] [difficulty] [tempo]

tempo: "human" (0.2-0.45 s per move, a 1-2.5 s think now and then),
       "fast" (0.12-0.25 s), "wait" (wait for the brain, like review_tips)
"""
import collections
import os
import random
import sys
import tempfile
import time

import pygame

from diag_common import B, load_game, policy_corner_human, policy_lazy_corner, policy_noisy

OUT = sys.argv[1]
GAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 3
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 1
DIFF = sys.argv[4] if len(sys.argv) > 4 else "normal"
TEMPO = sys.argv[5] if len(sys.argv) > 5 else "human"
os.makedirs(OUT, exist_ok=True)

g = load_game()
tmp = tempfile.mkdtemp()
g.CONFIG_PATH = os.path.join(tmp, "c.json")
g.GAME_PATH = os.path.join(tmp, "g.json")
g.Game._start_update_check = lambda self: setattr(self, "update_status", "error")
game = g.Game()
game.cfg["show_tips"] = True
game.cfg["language"] = "he"
game.cfg["difficulty"] = DIFF
KEYS = {B.LEFT: pygame.K_LEFT, B.RIGHT: pygame.K_RIGHT, B.UP: pygame.K_UP, B.DOWN: pygame.K_DOWN}


def run_for(secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        game.frame(1 / 60)
        time.sleep(0.004)


def settle():
    end = time.monotonic() + 3
    while time.monotonic() < end:
        game.frame(1 / 60)
        if not game.animating and not game.pop_tiles and game.analyst.idle() \
                and not game._pending_coach:
            break
        time.sleep(0.002)


policies = [("careful", policy_corner_human), ("habit", policy_lazy_corner),
            ("casual", policy_noisy(0.55))]
log = open(os.path.join(OUT, "tempo_tips.txt"), "w", encoding="utf-8")
total_moves = 0
seen = collections.Counter()
for gi in range(GAMES):
    pname, pol = policies[gi % len(policies)]
    rng = random.Random(SEED * 1000 + gi)
    random.seed(SEED * 1000 + gi)
    game.coach = B.Coach()
    game.coach.opened = True            # the opening tip is not what we count
    game.new_game()
    settle()
    last = game._tip
    moves = 0
    shown = []
    while game.board.can_move() and moves < 700:
        b, n = B.to_ranks(game.board.grid)
        d = pol(b, n, rng)
        if d is None:
            break
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": KEYS[d], "mod": 0,
                                                             "unicode": "", "scancode": 0}))
        moves += 1
        if TEMPO == "wait":
            settle()
        else:
            lo, hi = (0.2, 0.45) if TEMPO == "human" else (0.12, 0.25)
            run_for(rng.uniform(lo, hi))
            if TEMPO == "human" and rng.random() < 0.08:
                run_for(rng.uniform(1.0, 2.5))       # a think
        tip = game._tip
        if tip is not None and tip is not last:
            shown.append((moves, tip.key, game.tip_text(tip)))
            seen[tip.key] += 1
        last = tip
    total_moves += moves
    log.write("=== game %d (%s), %d moves, max %d, tips %d, coach steps %d\n"
              % (gi + 1, pname, moves, game.board.max_tile(), len(shown), game.coach.move_no))
    for m, k, t in shown:
        log.write("   move %4d  %-18s %s\n" % (m, k, t))
log.write("\nTOTAL moves %d, tips %d (one per %.0f moves)\n%s\n"
          % (total_moves, sum(seen.values()), total_moves / max(1, sum(seen.values())), dict(seen)))
log.close()
game.shutdown()
print("moves %d tips %d -> one per %.0f moves" % (total_moves, sum(seen.values()),
                                                   total_moves / max(1, sum(seen.values()))))
print(dict(seen))
