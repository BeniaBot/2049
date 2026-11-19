# -*- coding: utf-8 -*-
"""Frame pacing while the brain thinks: play a real Game (headless) at a
fast human pace and record how long each 60-fps frame takes. The brain runs
on a worker thread; this shows whether it steals frames from the UI.

    python tools/perf_frames.py [size] [seconds] [move_every_ms] [nowait]
"""
import os
import random
import sys
import tempfile
import time

import pygame

from diag_common import B, load_game

N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 20
EVERY = float(sys.argv[3]) / 1000 if len(sys.argv) > 3 else 0.18
NO_MAX_WAIT = len(sys.argv) > 4 and sys.argv[4] == "nowait"   # the old rule: think only at rest

g = load_game()
tmp = tempfile.mkdtemp()
g.CONFIG_PATH = os.path.join(tmp, "c.json")
g.GAME_PATH = os.path.join(tmp, "g.json")
g.Game._start_update_check = lambda self: None
if NO_MAX_WAIT:
    g.Analyst.MAX_WAIT = 1e9
if os.environ.get("PERF_MAXWAIT"):
    g.Analyst.MAX_WAIT = float(os.environ["PERF_MAXWAIT"])
if os.environ.get("PERF_SWITCH"):
    sys.setswitchinterval(float(os.environ["PERF_SWITCH"]))
game = g.Game()
game.cfg["grid_size"] = N
game.cfg["show_tips"] = True
game.new_game()
rng = random.Random(1)
keys = [pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_UP]
frames = []
t_end = time.perf_counter() + SECS
next_move = time.perf_counter()
last = time.perf_counter()
moves = 0
while time.perf_counter() < t_end:
    now = time.perf_counter()
    if now >= next_move:
        b, n = B.to_ranks(game.board.grid)
        d = B.best_move(b, n, 1) if rng.random() < 0.8 else rng.randrange(4)
        if d is None:
            game.new_game()
        else:
            game.handle_event(pygame.event.Event(
                pygame.KEYDOWN, {"key": keys[[B.LEFT, B.DOWN, B.RIGHT, B.UP].index(d)],
                                 "mod": 0, "unicode": "", "scancode": 0}))
            moves += 1
        next_move = now + EVERY
    moving = bool(game.animating or game.pop_tiles)
    t0 = time.perf_counter()
    game.frame(min(now - last, 0.1))
    frames.append((time.perf_counter() - t0, moving))
    last = now
    sl = 1 / 60 - (time.perf_counter() - now)
    if sl > 0:
        time.sleep(sl)
game.shutdown()
for label, sel in (("ALL", lambda m: True), ("while tiles move", lambda m: m),
                   ("board at rest", lambda m: not m)):
    fs = sorted(f for f, m in frames if sel(m))
    k = len(fs)
    over = sum(1 for f in fs if f > 1 / 60)
    print(label + ": ", end="")
    hitches = sum(1 for f in fs if f > 2 / 60)      # 2+ frames late: what an eye sees
    print("%dx%d, %d moves, %d frames: frame ms p50 %.1f  p95 %.1f  p99 %.1f  max %.1f;"
      " frames over 16.7ms: %.1f%%; hitches (>33ms) per minute: %.0f"
          % (N, N, moves, k, 1000 * fs[k // 2], 1000 * fs[int(k * .95)],
             1000 * fs[int(k * .99)], 1000 * fs[-1], 100 * over / k, hitches * 60.0 / SECS))

