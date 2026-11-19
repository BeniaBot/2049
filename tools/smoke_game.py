# -*- coding: utf-8 -*-
"""Headless end-to-end drive of the real Game object: moves (fast, mid-slide),
every assist, undo, game over, win, save/resume, every screen in both
languages. Fails loudly on any exception. Screens go to OUT_DIR as PNG.

    python tools/smoke_game.py OUT_DIR
"""
import os
import sys
import tempfile
import time

import pygame

from diag_common import B, load_game

OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(OUT, exist_ok=True)

g = load_game()
TMP = tempfile.mkdtemp(prefix="2049_smoke_")
g.CONFIG_PATH = os.path.join(TMP, "2049_config.json")
g.GAME_PATH = os.path.join(TMP, "2049_game.json")
g.Game._start_update_check = lambda self: setattr(self, "update_status", "error")

checks = []


def check(name, cond):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


def snap(game, name):
    game.frame(0.0)
    small = pygame.transform.smoothscale(game._render_surf, (game.W, game.H))
    pygame.image.save(small, os.path.join(OUT, name + ".png"))


def key(game, k, mods=()):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": k, "mod": 0,
                                                         "unicode": "", "scancode": 0}))


def settle(game, secs=0.6):
    """Let animations finish and the brain deliver."""
    t_end = time.time() + secs
    while time.time() < t_end:
        game.frame(1 / 60)
        if not game.animating and game.analyst.idle() and not game._pending_coach:
            break
        time.sleep(0.005)
    game.frame(1 / 60)


def set_board(game, rows, score=0):
    game._finish_now()
    game.board = g.Board(len(rows))
    game.board.grid = [list(r) for r in rows]
    game.board.score = score
    game.history = []
    game._board_changed("resync")
    settle(game)


game = g.Game()
game.cfg["show_tips"] = True
settle(game)
check("starts with a board", game.board.max_tile() > 0)

# --- fast moves: four keys inside one slide must make four moves --------
set_board(game, [[2, 0, 0, 2], [0, 4, 0, 4], [0, 0, 8, 0], [2, 0, 0, 0]])
mv0 = game._move_no
for k in (pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_UP):
    key(game, k)          # no frame in between: each arrives mid-slide
settle(game)
check("4 fast keys -> 4 moves (none swallowed)", game._move_no - mv0 == 4)

# --- clear stuck tile: arms, then vanishes inside the next move ----------
set_board(game, [[2, 4, 8, 2], [32, 4, 16, 0], [256, 64, 8, 8], [4, 1024, 4, 4]])
tile_before = game.board.grid[3][0]
game.cfg["active_profile"] = 3            # Mode 4: C = clean, Z = undo
key(game, pygame.K_c)
check("clean arms (no toast, board untouched yet)",
      game._armed_clean is not None and game.toast is None
      and game.board.grid[3][0] == tile_before)
key(game, pygame.K_RIGHT)
check("armed clean rides inside the move as a ghost tile",
      any(a.get("ghost") for a in game.anim_tiles))
settle(game)
flat = [v for row in game.board.grid for v in row]
check("the 4 that stole the 1024's corner is gone",
      game.board.grid[3][0] != 4 or flat.count(4) < 4)
check("cheat taints the game", game.cheat_used_this_game)
snap(game, "after_clean")

# --- nothing worth cleaning -> silent dot, no toast -----------------------
set_board(game, [[2, 0, 0, 0], [0] * 4, [0] * 4, [0, 0, 0, 4]])
key(game, pygame.K_c)
check("nothing to clean: not armed, no toast",
      game._armed_clean is None and game.toast is None and game.flash)

# --- undo ------------------------------------------------------------------
set_board(game, [[2, 2, 0, 0], [0] * 4, [0] * 4, [0] * 4])
key(game, pygame.K_LEFT); settle(game)
key(game, pygame.K_z); settle(game)
check("undo restores the board", game.board.grid[0][:2] == [2, 2])
key(game, pygame.K_z); settle(game)
check("undo with no history: silent", game.toast is None)

# --- smart spawn: hold X -> the brain picks the tile ------------------------
set_board(game, [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 4], [64, 32, 16, 8]])
orig_pressed = pygame.key.get_pressed


class Held:
    def __init__(self, keys):
        self.keys = set(keys)

    def __getitem__(self, k):
        return k in self.keys


pygame.key.get_pressed = lambda: Held({pygame.K_x})
key(game, pygame.K_LEFT)
pygame.key.get_pressed = orig_pressed
check("smart spawn chose a cell", game.pending_spawn and game.pending_spawn[2] is not None)
settle(game)

# --- dead board + clean = immediate rescue -----------------------------------
set_board(game, [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 1024]])
check("board is dead", not game.board.can_move())
snap(game, "game_over_he")
key(game, pygame.K_c); settle(game)
check("clean on a dead board rescues it now", game.board.can_move())

# --- danger / trap tip ------------------------------------------------------------
game.coach = B.Coach(); game.coach.opened = True
set_board(game, [[2, 8, 2, 8], [16, 32, 16, 4], [8, 64, 128, 2], [16, 32, 0, 4]])
a = game._analysis_now()
print("   trap board: deadly", a.deadly, "safety", a.safety)

# --- coach tips render in both languages -------------------------------------------
for lang in ("he", "en"):
    game.cfg["language"] = lang
    for t in (B.Tip("tip_trap", 5, game.coach.move_no, {"dir": 3, "bad": [0, 1]}),
              B.Tip("tip_stuck", 4, game.coach.move_no, {"value": 4, "place": "corner_bl"}),
              B.Tip("tip_corner_lost", 3, game.coach.move_no, {"value": 256, "dir": 0}),
              B.Tip("tip_good_record", 1, game.coach.move_no, {"value": 512}, kind="praise")):
        game._tip = t; game._tip_since = time.monotonic()
        set_board(game, [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 2048, 4096],
                         [8192, 16384, 0, 2]])
        game._tip = t; game._tip_since = time.monotonic()
        snap(game, "tip_%s_%s" % (t.key, lang))
    game.state = "settings"; snap(game, "settings_" + lang)
    game.enter_preferences(); snap(game, "prefs_" + lang)
    game.cfg["active_profile"] = 3; snap(game, "prefs4_" + lang)
    game.state = "game"
    game.cfg["infinite"] = False
    set_board(game, [[2048, 4, 0, 0], [0] * 4, [0] * 4, [0] * 4])
    game.won = True; game.keep_going = False
    snap(game, "won_" + lang)
    game.cfg["infinite"] = True; game.won = False

# --- save / resume ------------------------------------------------------------------
game.cfg["language"] = "he"
set_board(game, [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 4, 0], [0, 0, 0, 2]], score=1234)
game.cheat_used_this_game = True
game.shutdown()
check("game file written", os.path.exists(g.GAME_PATH))
game2 = g.Game()
settle(game2)
check("resumed board", game2.board.grid[0] == [2, 4, 8, 16] and game2.board.score == 1234)
check("resumed cheat taint (no best-score laundering)", game2.cheat_used_this_game)
game2.shutdown()

# --- corrupt config falls back to .bak ------------------------------------------------
with open(g.CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write('{"language": "xx", "grid_size": 9, "highscore": ')
cfg = g.load_config()
check("corrupt config -> sane values", cfg["language"] in ("he", "en") and cfg["grid_size"] in (4, 5, 6))

bad = sum(1 for _, ok in checks if not ok)
print("\n%d checks, %d failed. screens in %s" % (len(checks), bad, OUT))
sys.exit(1 if bad else 0)
