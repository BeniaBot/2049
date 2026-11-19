# -*- coding: utf-8 -*-
"""Play simulated games through the REAL Game object (the same code path as
the exe: Analyst thread, coach, drawing) and record every tip at the moment
it appears: the board, the tip text, and a screenshot of what the player
sees. The log is for a human (or Claude) to read and judge tip by tip.

    python tools/review_tips.py OUT_DIR [games] [seed] [lang]
"""
import os
import random
import sys
import tempfile
import time

import pygame

from diag_common import B, load_game, policy_corner_human, policy_lazy_corner, policy_noisy

OUT = sys.argv[1]
GAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 6
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 1
LANG = sys.argv[4] if len(sys.argv) > 4 else "en"
os.makedirs(OUT, exist_ok=True)

g = load_game()
tmp = tempfile.mkdtemp()
g.CONFIG_PATH = os.path.join(tmp, "c.json")
g.GAME_PATH = os.path.join(tmp, "g.json")
g.Game._start_update_check = lambda self: setattr(self, "update_status", "error")
game = g.Game()
game.cfg["show_tips"] = True
game.cfg["language"] = LANG
KEYS = {B.LEFT: pygame.K_LEFT, B.RIGHT: pygame.K_RIGHT, B.UP: pygame.K_UP, B.DOWN: pygame.K_DOWN}
ARROW = {B.LEFT: "<-", B.RIGHT: "->", B.UP: "^", B.DOWN: "v"}


def settle():
    end = time.time() + 3
    while time.time() < end:
        game.frame(1 / 60)
        if not game.animating and not game.pop_tiles and game.analyst.idle() \
                and not game._pending_coach:
            break
        time.sleep(0.002)
    game.frame(1 / 60)


def board_text(grid):
    return "\n".join("    " + " ".join(("%5d" % v) if v else "    ." for v in row)
                     for row in grid)


log = open(os.path.join(OUT, "tips.txt"), "w", encoding="utf-8")
policies = [("careful", policy_corner_human), ("habit", policy_lazy_corner),
            ("casual", policy_noisy(0.55))]
n_tips = 0
for gi in range(GAMES):
    pname, pol = policies[gi % len(policies)]
    rng = random.Random(SEED * 1000 + gi)
    random.seed(SEED * 1000 + gi)
    game.coach = B.Coach()
    game.new_game()
    settle()
    last_tip = game._tip
    moves = 0
    while game.board.can_move() and moves < 700:
        b, n = B.to_ranks(game.board.grid)
        d = pol(b, n, rng)
        if d is None:
            break
        before = [row[:] for row in game.board.grid]
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": KEYS[d], "mod": 0,
                                                             "unicode": "", "scancode": 0}))
        settle()
        moves += 1
        tip = game._tip
        if tip is not None and tip is not last_tip and game.cfg["show_tips"]:
            n_tips += 1
            text = game.tip_text(tip)
            log.write("#%d  game %d (%s player)  move %d  played %s  [%s]\n    TIP: %s\n"
                      % (n_tips, gi + 1, pname, moves, ARROW[d], tip.key, text))
            log.write("  before the move:\n%s\n  now:\n%s\n\n" % (board_text(before),
                                                             board_text(game.board.grid)))
            shot = pygame.transform.smoothscale(game._render_surf, (game.W, game.H))
            pygame.image.save(shot, os.path.join(OUT, "tip_%03d.png" % n_tips))
        last_tip = tip
    log.write("=== game %d over after %d moves, max tile %d\n\n" % (gi + 1, moves,
                                                                  game.board.max_tile()))
log.close()
game.shutdown()
print("tips recorded:", n_tips, "->", os.path.join(OUT, "tips.txt"))
