# -*- coding: utf-8 -*-
"""Tests for 2049 (game) and brain2049 (its thinking engine).

Run:  python test_2049.py
The game module is imported headless (SDL dummy drivers); no window opens
and the user's real config in %APPDATA%\\2049 is never touched (every test
that saves points the config and game files at a temp folder).
"""
import copy
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

_HERE = os.path.dirname(os.path.abspath(__file__))
_GAME_PY = os.path.join(_HERE, "2049.py")
sys.path.insert(0, _HERE)

spec_ = importlib.util.spec_from_file_location("game2049", _GAME_PY)
g = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(g)
import brain2049 as B  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="2049_tests_")
g.CONFIG_PATH = os.path.join(_TMP, "2049_config.json")
g.GAME_PATH = os.path.join(_TMP, "2049_game.json")
_REAL_UPDATE_CHECK = g.Game._start_update_check      # TestUpdates uses it
g.Game._start_update_check = lambda self: setattr(self, "update_status", "error")

import pygame  # noqa: E402


def board(rows):
    """Build a game Board directly from a list of rows."""
    b = g.Board(len(rows))
    b.grid = [list(r) for r in rows]
    return b


def ana(rows):
    return B.Analysis.of_grid(rows)


Z = [0, 0, 0, 0]


# ===========================================================================
#  Movement
# ===========================================================================
class TestMovement(unittest.TestCase):
    def test_left_merge_and_score(self):
        b = board([[2, 2, 4, 0], Z, Z, Z])
        changed, anims, merges = b.move("left")
        self.assertTrue(changed)
        self.assertEqual(b.grid[0], [4, 4, 0, 0])
        self.assertEqual(b.score, 4)
        self.assertIn((0, 0, 4), merges)

    def test_merge_once_rule(self):
        b = board([[2, 2, 2, 2], Z, Z, Z])
        changed, _, merges = b.move("left")
        self.assertTrue(changed)
        self.assertEqual(b.grid[0], [4, 4, 0, 0])   # NOT [8,0,0,0]
        self.assertEqual(b.score, 8)
        self.assertEqual(sorted(merges), [(0, 0, 4), (0, 1, 4)])

    def test_brain_moves_match_the_game(self):
        """The brain must see exactly the board the player gets."""
        rng = random.Random(7)
        for n in (4, 5, 6):
            for _ in range(150):
                rows = [[rng.choice([0, 0, 2, 4, 8, 16, 32]) for _ in range(n)]
                        for _ in range(n)]
                for d in B.DIR_NAMES:
                    gb = board(rows)
                    changed, _, _ = gb.move(d)
                    rb, gain = B.move(B.to_ranks(rows)[0], n, B.NAME_TO_DIR[d])
                    self.assertEqual(B.to_grid(rb, n), gb.grid)
                    self.assertEqual(gain, gb.score)


# ===========================================================================
#  The brain: what is stuck, what is dangerous
# ===========================================================================
class TestStuck(unittest.TestCase):
    """Positions judged by a human player first; the brain must agree."""

    def test_small_tile_stole_the_corner(self):
        # the 4 sits in the 1024's corner: the most common real stuck tile,
        # and the one the old detector always missed
        a = ana([[4, 2, 8, 2], [32, 4, 16, 0], [256, 64, 8, 8], [4, 1024, 4, 4]])
        self.assertEqual(a.problem, 12)
        self.assertIn(12, a.stuck)

    def test_two_in_the_512_corner(self):
        a = ana([[2, 512, 64, 4], [0, 32, 8, 16], [0, 8, 4, 4], [2, 0, 0, 0]])
        self.assertEqual(a.problem, 0)

    def test_blocker_between_equal_pair(self):
        a = ana([[128, 2, 0, 128], Z, Z, Z])
        self.assertEqual(a.problem, 1)

    def test_dip_in_the_top_row(self):
        a = ana([[256, 4, 64, 8], [16, 32, 8, 2], [2, 4, 2, 0], Z])
        self.assertEqual(a.problem, 1)
        self.assertIn(1, a.stuck)

    def test_calm_boards_have_nothing_stuck(self):
        for rows in ([[2, 0, 0, 0], Z, Z, [0, 0, 0, 4]],
                     [[2, 2, 4, 4], [8, 8, 16, 16], [32, 32, 64, 64],
                      [128, 128, 256, 256]],
                     [[256, 128, 64, 32], [2, 4, 8, 16], [0, 0, 0, 2], Z]):
            a = ana(rows)
            self.assertIsNone(a.problem, rows)
            self.assertEqual(a.stuck, set(), rows)

    def test_stuck_only_names_low_tiles(self):
        # removing the 256 helps too, but nobody calls a 256 "stuck" at 1024
        a = ana([[4, 2, 8, 2], [32, 4, 16, 0], [256, 64, 8, 8], [4, 1024, 4, 4]])
        self.assertNotIn(8, a.stuck)

    def test_game_assist_removes_the_right_tile(self):
        b = board([[2, 512, 64, 4], [0, 32, 8, 16], [0, 8, 4, 4], [2, 0, 0, 0]])
        self.assertEqual(b.remove_stuck_low(), (0, 0))
        self.assertEqual(b.grid[0][0], 0)

    def test_chain_breaker(self):
        b, n = B.to_ranks([[256, 4, 64, 8], Z, Z, Z])
        self.assertTrue(B.chain_breaker(b, n, 1))
        b, n = B.to_ranks([[256, 64, 4, 8], Z, Z, Z])   # 64 > 4 < 8: a dip
        self.assertTrue(B.chain_breaker(b, n, 2))
        b, n = B.to_ranks([[256, 64, 4, 2], Z, Z, Z])
        self.assertFalse(B.chain_breaker(b, n, 2))      # descending: fine


class TestSurvival(unittest.TestCase):
    def test_dead_board(self):
        b, n = B.to_ranks([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]])
        self.assertEqual(B.survival(b, n, 3), 0.0)

    def test_open_board_is_safe(self):
        b, n = B.to_ranks([[2, 0, 0, 0], Z, Z, [0, 0, 0, 4]])
        self.assertEqual(B.survival(b, n, 3), 1.0)

    def test_trap_is_seen(self):
        # 'right' kills you here, 'left' is safe: the classic way games die
        a = ana([[2, 8, 2, 8], [16, 32, 16, 4], [8, 64, 128, 2], [16, 32, 0, 4]])
        self.assertIn(B.RIGHT, a.deadly)
        self.assertNotIn(a.safest(), a.deadly)
        self.assertGreater(a.safety[a.safest()], 0.9)


class TestSearch(unittest.TestCase):
    def test_plays_a_real_game(self):
        """A short self-play: the engine must reach 256 quickly (a random
        player rarely does) - proof the search and evaluation make sense."""
        rng = random.Random(3)
        n = 4
        b = tuple([0] * 16)

        def spawn(b):
            cells = [i for i, x in enumerate(b) if x == 0]
            l = list(b)
            l[rng.choice(cells)] = 2 if rng.random() < 0.1 else 1
            return tuple(l)
        b = spawn(spawn(b))
        for _ in range(300):
            d = B.best_move(b, n, 1)
            if d is None:
                break
            b, _ = B.move(b, n, d)
            b = spawn(b)
        self.assertGreaterEqual(max(b), 8)               # 256+

    def test_best_spawn_respects_the_rules(self):
        b, n = B.to_ranks([[0, 0, 0, 0], Z, [0, 0, 0, 4], [64, 32, 16, 8]])
        i, r = B.best_spawn(b, n, ranks=(1,), cells=[0, 3, 8])
        self.assertIn(i, [0, 3, 8])
        self.assertEqual(r, 1)


# ===========================================================================
#  The coach
# ===========================================================================
def ident(rows):
    """moved map for a board where nothing moved (tests feed boards directly)."""
    n = len(rows)
    return {r * n + c: (r * n + c, False) for r in range(n) for c in range(n)
            if rows[r][c]}


class FitsOnly:
    """A board with just what general_fits looks at (no search: cheap)."""
    def __init__(self, b, n=4):
        self.b, self.n = tuple(b), n
        self.max_rank, self.empties = max(b), b.count(0)
        self.corner = B.max_in_corner(self.b, n)


class TestCoach(unittest.TestCase):
    STUCK = [[256, 4, 64, 8], [16, 32, 8, 2], [2, 4, 2, 0], Z]

    def fresh(self, rows):
        c = B.Coach()
        c.opened = True
        c.habit = 1.0              # a player who keeps the corner
        c.new_game(ana(rows))
        c.current = None           # mid-game: the opening tip is long gone
        c.open_shown = set(B.OPEN_TIPS)   # ...and the general ones said: these
        return c                          # tests are about the board itself

    def test_stuck_waits_one_move_then_names_the_tile(self):
        calm = [[256, 64, 8, 4], [16, 32, 8, 2], [2, 4, 2, 0], Z]
        c = self.fresh(calm)
        tip = c.on_move(B.LEFT, ident(self.STUCK), ana(self.STUCK))
        self.assertTrue(tip is None or tip.key != "tip_stuck")   # no flicker tips
        tip = c.on_move(B.LEFT, ident(self.STUCK), ana(self.STUCK))
        self.assertIsNotNone(tip)
        self.assertEqual(tip.key, "tip_stuck_chain")
        self.assertEqual(tip.params, {"value": 4, "big": 256, "place": "edge_top"})

    def test_messy_board_gets_no_stuck_tip(self):
        # a player's screenshot (19.11): the 64 sits in the middle, boxed in;
        # calling 'the 8 in the right column' stuck was nonsense
        board = [[4, 16, 2, 4], [8, 4, 64, 8], [4, 16, 4, 2], [2, 0, 0, 0]]
        self.assertEqual(ana(board).stuck, set())
        c = self.fresh(board)
        for _ in range(3):
            tip = c.on_move(B.LEFT, ident(board), ana(board))
            self.assertTrue(tip is None or not tip.key.startswith("tip_stuck"))

    def test_blocker_between_equal_pair_is_named_as_such(self):
        board = [[256, 2, 256, 128], [8, 4, 16, 32], [0, 4, 32, 4], [2, 0, 0, 2]]
        c = self.fresh(board)
        c.on_move(B.LEFT, ident(board), ana(board))
        tip = c.on_move(B.LEFT, ident(board), ana(board))
        self.assertEqual(tip.key, "tip_stuck_block")
        self.assertEqual((tip.params["value"], tip.params["big"]), (2, 256))

    def test_corner_goal_only_when_one_move_does_it(self):
        off = [[8, 16, 4, 4], [4, 32, 8, 32], [2, 16, 64, 4], [2, 8, 128, 0]]
        c = self.fresh(off)
        tip = None
        for _ in range(B.OFF_CORNER_MOVES + 1):
            tip = c.on_move(B.UP, ident(off), ana(off)) or tip
        self.assertIsNotNone(tip)
        self.assertEqual(tip.key, "tip_corner_goal")
        self.assertEqual(tip.params, {"value": 128})      # names no move
        self.assertEqual(B.Coach._ways_back(ana(off)), [B.RIGHT])

    def test_trap_tip_points_to_safety_and_expires(self):
        trap = [[2, 8, 2, 8], [16, 32, 16, 4], [8, 64, 128, 2], [16, 32, 0, 4]]
        c = self.fresh([[2, 0, 0, 0], Z, Z, Z])
        a = ana(trap)
        tip = c.on_move(B.UP, ident(trap), a)
        self.assertEqual(tip.key, "tip_trap")
        self.assertEqual(tip.params["dir"], a.safest())
        self.assertIn(B.RIGHT, tip.params["bad"])
        calm = [[2, 0, 0, 0], Z, Z, [0, 0, 0, 4]]
        tip = c.on_move(B.LEFT, ident(calm), ana(calm))
        self.assertIsNone(tip)                       # gone the moment it is stale

    def test_no_praise_for_what_a_cheat_did(self):
        c = self.fresh(self.STUCK)
        c.on_move(B.LEFT, ident(self.STUCK), ana(self.STUCK))
        c.on_move(B.LEFT, ident(self.STUCK), ana(self.STUCK))   # told
        freed = [[256, 0, 64, 8], [16, 32, 8, 2], [2, 4, 2, 0], Z]
        moved = ident(self.STUCK)
        moved[1] = (1, True)
        tip = c.on_move(B.LEFT, moved, ana(freed), cheated=True)
        self.assertTrue(tip is None or tip.key != "tip_good_freed")

    def real_move(self, rows, d, spawn_at):
        """Play a real move: (moved map, board after move + a 2 at spawn_at)."""
        gb = board(rows)
        _, anims, _ = gb.move(d)
        n = gb.size
        moved = {a["from"][0] * n + a["from"][1]:
                 (a["to"][0] * n + a["to"][1], a["merged"]) for a in anims}
        gb.grid[spawn_at[0]][spawn_at[1]] = 2
        return moved, gb.grid

    def test_corner_lost_when_it_clearly_mattered(self):
        # left keeps the 64 in its corner; the player swipes right anyway,
        # and that costs a lot here (0.6 units)
        before = [[2, 4, 8, 0], [4, 8, 16, 2], [8, 16, 32, 0], [64, 32, 8, 0]]
        c = self.fresh(before)
        moved, after = self.real_move(before, "right", (0, 0))
        tip = c.on_move(B.RIGHT, moved, ana(after))
        self.assertIsNotNone(tip)
        self.assertEqual(tip.key, "tip_corner_lost")
        self.assertEqual(tip.params, {"value": 64})       # names no move

    def test_new_top_tile_made_outside_the_corner_is_named_so(self):
        # the two 128s merge to the LEFT: the new 256 never was in a corner,
        # so the tip must not say it "left" one (seen in a review game)
        before = [[4, 4, 128, 128], [0, 2, 4, 2], [0, 2, 2, 16], [0, 0, 0, 2]]
        c = self.fresh(before)
        moved, after = self.real_move(before, "left", (3, 3))
        tip = c.on_move(B.LEFT, moved, ana(after))
        self.assertIsNotNone(tip)
        self.assertEqual(tip.key, "tip_corner_made")
        self.assertEqual(tip.params, {"value": 256})

    def test_general_order_tip_when_big_tiles_spread_out(self):
        spread = [[0, 0, 0, 64], [0, 0, 2, 4], [0, 2, 4, 8], [256, 4, 8, 2]]
        tidy = [[0, 0, 0, 2], [0, 0, 2, 4], [64, 2, 4, 8], [256, 128, 8, 2]]
        self.assertTrue(B.big_tiles_scattered(*B.to_ranks(spread)))
        self.assertFalse(B.big_tiles_scattered(*B.to_ranks(tidy)))
        c = self.fresh(spread)
        tips = [c.on_move(B.LEFT, ident(spread), ana(spread)) for _ in range(B.SCATTER_MOVES)]
        self.assertEqual([t.key if t else None for t in tips][-1], "tip_hint_order")
        self.assertTrue(all(t is None for t in tips[:-1]))      # not a passing moment
        self.assertIsNone(c.on_move(B.LEFT, ident(tidy), ana(tidy)))   # gone once tidy

    def test_way_back_is_the_same_tile_not_a_new_one(self):
        # only two 32s merging could put "a 64" into a corner - the 64 itself
        # cannot get there, so no "you can get your 64 back" (review game)
        rows = [[0, 0, 2, 0], [2, 2, 4, 0], [2, 4, 8, 32], [4, 32, 64, 32]]
        a = ana(rows)
        self.assertTrue(a.keeps_corner(B.UP))
        self.assertFalse(a.brings_max_to_corner(B.UP))
        self.assertEqual(B.Coach._ways_back(a), [])

    def test_two_top_tiles_get_no_corner_talk(self):
        # review round 4, both judged wrong by the referee: with two 128s
        # "the 2 took the 128's corner" means nothing...
        now = [[2, 32, 2, 64], [4, 16, 8, 128], [2, 0, 2, 4], [0, 2, 128, 2]]
        b, n = B.to_ranks(now)
        self.assertIsNone(B.stuck_kind(b, n, 15))
        # ...and leaving the corner to bring the two 128s together was right
        before = [[2, 16, 64, 128], [16, 8, 32, 8], [4, 16, 128, 2], [4, 8, 4, 2]]
        c = self.fresh(before)
        moved, after = self.real_move(before, "down", (0, 3))
        tip = c.on_move(B.DOWN, moved, ana(after))
        self.assertTrue(tip is None or not tip.key.startswith("tip_corner"))

    def test_warning_after_a_burst_of_fast_moves(self):
        # moves too fast to analyse one by one end in a resync; if the board
        # it lands on is a trap, the pause is exactly when to say so
        trap = [[2, 8, 2, 8], [16, 32, 16, 4], [8, 64, 128, 2], [16, 32, 0, 4]]
        c = self.fresh([[2, 0, 0, 0], Z, Z, Z])
        a = ana(trap)
        c.resync(a)
        self.assertIsNotNone(c.current)
        self.assertEqual(c.current.key, "tip_trap")
        self.assertEqual(c.current.params["dir"], a.safest())
        calm = [[2, 0, 0, 0], Z, Z, [0, 0, 0, 4]]
        c.resync(ana(calm))
        self.assertTrue(c.current is None or c.current.key != "tip_trap")
        # and the JS port says exactly the same
        js = ("const B=require(%r);const c=new B.Coach();c.newGame(B.Analysis.ofGrid(%s,true));"
              "const a=B.Analysis.ofGrid(%s,true);c.resync(a);"
              "console.log(JSON.stringify([c.current.key,c.current.params]))"
              % (os.path.join(_HERE, "brain2049.js").replace("\\", "/"),
                 json.dumps([[2, 0, 0, 0], Z, Z, Z]), json.dumps(trap)))
        try:
            out = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                                 timeout=60).stdout.strip()
        except FileNotFoundError:
            self.skipTest("node not installed")
        key, params = json.loads(out)
        self.assertEqual(key, "tip_trap")
        self.assertEqual(params["dir"], a.safest())
        self.assertEqual(params["bad"], a.deadly)

    def test_no_tip_once_the_game_is_over(self):
        start = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 0]]
        dead = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
        c = self.fresh(start)
        self.assertIsNone(c.on_move(B.LEFT, ident(dead), ana(dead)))
        self.assertIsNone(c.current)

    def test_corner_exit_that_hardly_matters_is_not_blamed(self):
        # an early, open board: leaving the corner costs only 0.15 units -
        # in the calibration that is where the referee once found the exit
        # to have been the better move
        before = [[2, 4, 0, 0], [4, 8, 0, 2], [8, 16, 0, 0], [64, 32, 0, 0]]
        c = self.fresh(before)
        moved, after = self.real_move(before, "right", (0, 0))
        tip = c.on_move(B.RIGHT, moved, ana(after))
        self.assertTrue(tip is None or tip.key != "tip_corner_lost")

    def test_forced_corner_loss_is_not_blamed(self):
        # every column and row is packed left: right is the ONLY move
        before = [[2, 4, 0, 0], [4, 8, 0, 0], [8, 16, 0, 0], [64, 32, 0, 0]]
        c = self.fresh(before)
        moved, after = self.real_move(before, "right", (0, 0))
        tip = c.on_move(B.RIGHT, moved, ana(after))
        self.assertTrue(tip is None or tip.key != "tip_corner_lost")

    def test_a_general_tip_opens_every_game_and_each_game_differently(self):
        start = ana([[2, 0, 0, 0], Z, Z, Z])
        c = B.Coach()
        c.new_game(start)
        self.assertEqual(c.current.key, "tip_open")        # the very first: a corner
        c.shown(c.current)                                 # (the screen showed it)
        opens = []
        for _ in range(4):                                 # the corner not kept
            c.counted_moves, c.corner_moves = 40, 8
            c.new_game(start)
            opens.append(c.current.key)
            self.assertTrue(B.general_fits(c.current.key, start))
            c.shown(c.current)
        self.assertEqual(len(set(opens)), 4)               # the round goes on
        for _ in range(len(B.OPEN_TIPS)):                  # the corner kept: never it
            c.counted_moves, c.corner_moves = 40, 36
            c.new_game(start)
            self.assertNotEqual(c.current.key, "tip_open")
            c.shown(c.current)

    def test_a_tip_never_shown_is_not_taken_as_said(self):
        # fast play (20.11): the coach chose 'keep your corner's row full',
        # it never reached the screen, and 'like a snake' (which builds on
        # it) came anyway. Only what the screen showed counts as said
        start = ana([[2, 0, 0, 0], Z, Z, Z])
        c = B.Coach()
        c.new_game(start)                                  # chosen, never shown...
        self.assertEqual(c.taught, set())
        c.new_game(start)
        self.assertEqual(c.current.key, "tip_open")        # ...so it is chosen again
        c.shown(c.current)
        self.assertEqual(c.taught, {"tip_open"})
        c.new_game(start)
        self.assertEqual(c.current.key, "tip_g_merge")     # and now the course goes on
        # a habit tip that reached the screen teaches its general twin
        c.shown(B.Tip("tip_hint_dirs", B.PRIO_HINT, 0, kind="info"))
        self.assertIn("tip_open_dirs", c.taught)
        self.assertIn("tip_open_dirs", c.open_shown)

    def test_general_tips_often_early_never_twice_in_a_game(self):
        calm = [[2, 4, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        full = [[2, 4, 8, 2], [4, 8, 2, 4], [8, 64, 4, 0], [128, 32, 16, 0]]
        c = B.Coach()
        c.new_game(ana(calm))                      # opening tip at move 0
        c.shown(c.current)                         # (a screen that shows every tip)
        at, keys = [0], [c.current.key]
        for m in range(1, 300):
            rows = calm if m < 40 else full        # a board that fills up later
            a = ana(rows)
            tip = c.on_move(B.LEFT, ident(rows), a)
            if tip is not None and tip.born == m:
                c.shown(tip)
            if tip is not None and tip.key in B.OPEN_TIPS and tip.born == m:
                for need in B.PREREQ.get(tip.key, ()):          # after what it builds on
                    self.assertIn(need, keys)
                at.append(m)
                keys.append(tip.key)
                self.assertTrue(B.general_fits(tip.key, a))      # fits the board it is said on
            c.dismiss()                            # as the screen does after a while
        self.assertEqual(len(keys), len(set(keys)))             # never twice in a game
        self.assertEqual(keys[:4], ["tip_open", "tip_g_merge", "tip_open_dirs", "tip_g_look"])
        self.assertGreaterEqual(len([m for m in at if m <= B.EARLY_MOVES]), 4)
        self.assertIn("tip_g_fill", keys)          # said once the board filled up
        self.assertNotIn("tip_g_fill", keys[:4])   # ...and not while it was empty

    def test_habit_tips_at_most_twice_a_game(self):
        rows = [[2, 4, 0, 0], [4, 16, 2, 0], [8, 2, 0, 0], [2, 0, 0, 0]]
        c = self.fresh(rows)
        told = 0
        for m in range(1, 300):
            d = (B.LEFT, B.UP, B.RIGHT, B.DOWN)[m % 4]       # all four, all game
            tip = c.on_move(d, ident(rows), ana(rows))
            if tip is not None and tip.key == "tip_hint_dirs" and tip.born == m:
                told += 1
            c.dismiss()
        self.assertEqual(told, B.HINT_MAX)

    def test_a_general_tip_never_holds_back_a_tip_about_a_move(self):
        calm = [[2, 4, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        c = B.Coach()
        c.new_game(ana(calm))
        general = None
        for m in range(1, 40):
            tip = c.on_move(B.LEFT, ident(calm), ana(calm))
            if tip is not None and tip.key in B.OPEN_TIPS and tip.born == m:
                general = tip
                break
        self.assertIsNotNone(general)
        self.assertIsNone(c.last_any)              # it left GAP alone: the next move,
        self.assertTrue(c._ready("tip_corner_lost"))   # a tip about it may speak

    def test_tips_come_after_the_ones_they_build_on(self):
        # the player (20.11): the game opened with tips that made no sense
        # before the basic ones were said. Over many games and all kinds of
        # boards: the basics first, and a tip only after all it builds on
        rng = random.Random(11)

        def some_board(step):
            top = min(11, 1 + step // 4 + rng.randint(0, 2))
            b = [0] * 16
            for i, cell in enumerate(rng.sample(range(16), rng.randint(2, 15))):
                b[cell] = top if i == 0 else rng.randint(1, max(1, top - 1))
            return FitsOnly(b)
        c = B.Coach()
        heard = set()
        for game in range(12):
            keeps = game % 4 == 3                        # some games the corner held
            c.counted_moves, c.corner_moves = 40, (36 if keeps else 8)
            c.new_game(some_board(0))
            said = []
            if c.current is not None:
                c.shown(c.current)
                said.append(c.current.key)
            for step in range(1, 60):
                k = c._next_general(some_board(step))
                if k is not None:
                    c.shown(B.Tip(k, B.PRIO_OPEN, step, kind="info"))
                    said.append(k)
            if game == 0:
                self.assertEqual(said[:4], ["tip_open", "tip_g_merge", "tip_open_dirs", "tip_g_look"])
            for k in said:
                for need in B.PREREQ.get(k, ()):
                    self.assertTrue(need in heard or (need == "tip_open" and c.habit >= B.OPEN_KEEP),
                                    (game, k, need))
                heard.add(k)
        self.assertEqual(heard, set(B.OPEN_TIPS))       # and the whole course gets said

    def test_same_words_as_a_habit_tip_count_once(self):
        # "pick one direction and avoid it" is a general tip and also the
        # tip for a player who uses all four: either one teaches it...
        rows = [[2, 4, 0, 0], [4, 16, 2, 0], [8, 2, 0, 0], [2, 0, 0, 0]]
        c = self.fresh(rows)
        c.taught = set()
        tip = None
        for d in [B.LEFT, B.UP, B.RIGHT, B.DOWN] * 3:
            tip = c.on_move(d, ident(rows), ana(rows)) or tip
        self.assertEqual(tip.key, "tip_hint_dirs")
        c.shown(tip)
        self.assertIn("tip_open_dirs", c.taught)     # "the direction you chose to avoid" may follow
        # ...and once the general one was said, the same words do not come
        # back as the other a few moves later
        c = self.fresh(rows)
        c.shown(B.Tip("tip_open_dirs", B.PRIO_OPEN, 0, kind="info"))
        first = None
        for m in range(1, 40):
            tip = c.on_move((B.LEFT, B.UP, B.RIGHT, B.DOWN)[m % 4], ident(rows), ana(rows))
            if tip is not None and tip.key == "tip_hint_dirs" and first is None:
                first = m
            c.dismiss()
        self.assertIsNotNone(first)
        self.assertGreaterEqual(first, B.COOLDOWN["tip_hint_dirs"])

    def test_corner_tips_end_once_it_is_back_in_its_corner(self):
        # 'it left its corner' ends the move the tile is back - in BOTH
        # engines (the browser's lost this line once and kept the tip up,
        # hiding the praise for bringing it back; found 20.11 by parity_check)
        back = [[0, 0, 0, 64], [0, 0, 2, 4], [0, 2, 4, 8], [256, 4, 8, 2]]
        c = B.Coach()
        keys = ["tip_corner_lost", "tip_corner_made"]
        self.assertEqual([c.is_valid(B.Tip(k, 3, 0, {"value": 256}, max_moves=6), ana(back))
                          for k in keys], [False, False])
        js = ("const B=require(%r);const c=new B.Coach();const a=B.Analysis.ofGrid(%s,true);"
              "console.log(JSON.stringify(%s.map(k=>c.isValid(new B.Tip(k,3,0,{value:256},{maxMoves:6}),a))))"
              % (os.path.join(_HERE, "brain2049.js").replace("\\", "/"), json.dumps(back), json.dumps(keys)))
        try:
            out = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                                 timeout=60).stdout.strip()
        except FileNotFoundError:
            self.skipTest("node not installed")
        self.assertEqual(json.loads(out), [False, False])

    def test_a_tip_is_kept_while_still_true(self):
        # what the screen may keep showing for a few seconds of fast play
        c = B.Coach()
        spread = ana([[0, 0, 0, 64], [0, 0, 2, 4], [0, 2, 4, 8], [256, 4, 8, 2]])
        self.assertTrue(c.still_true(B.Tip("tip_hint_order", 2, 0), spread))
        self.assertFalse(c.still_true(B.Tip("tip_trap", 5, 0, {"dir": 0, "bad": [1]}), spread))
        lost = B.Tip("tip_corner_lost", 3, 0, {"value": 256})
        self.assertTrue(c.still_true(lost, spread))        # what happened: a lesson
        goal = B.Tip("tip_corner_goal", 3, 0, {"value": 256})
        self.assertFalse(c.still_true(goal, spread))       # the 256 IS in its corner

    def test_beginner_directions_tip(self):
        # all four directions in turn, each at least twice in the last 12
        rows = [[2, 4, 0, 0], [4, 16, 2, 0], [8, 2, 0, 0], [2, 0, 0, 0]]
        c = self.fresh(rows)
        tip = None
        for d in [B.LEFT, B.UP, B.RIGHT, B.DOWN] * 3:
            tip = c.on_move(d, ident(rows), ana(rows)) or tip
        self.assertIsNotNone(tip)
        self.assertEqual(tip.key, "tip_hint_dirs")
        # a player who sticks to three directions never hears it
        c = self.fresh(rows)
        tips = [c.on_move(d, ident(rows), ana(rows)) for d in [B.LEFT, B.DOWN, B.RIGHT] * 4]
        self.assertTrue(all(t is None or t.key != "tip_hint_dirs" for t in tips))
        # nor one whose top tile held its corner all along (the tip would
        # promise what already is)
        held = [[16, 4, 0, 0], [4, 2, 2, 0], [8, 2, 0, 0], [2, 0, 0, 0]]
        c = self.fresh(held)
        tips = [c.on_move(d, ident(held), ana(held)) for d in [B.LEFT, B.UP, B.RIGHT, B.DOWN] * 3]
        self.assertTrue(all(t is None or t.key != "tip_hint_dirs" for t in tips))

    def test_a_burst_of_moves_is_followed_tile_by_tile(self):
        # three moves too fast to analyse one by one: the coach gets them as
        # one step - tiles followed through all three (compose_moves)
        m1 = {0: (1, False), 5: (5, False)}
        m2 = {1: (2, False), 5: (6, True)}
        m3 = {2: (3, False), 6: (6, False)}
        both = B.compose_moves(B.compose_moves(m1, m2), m3)
        self.assertEqual(both[0], (3, False))
        self.assertEqual(both[5], (6, True))
        # and the counters advance by the whole burst
        rows = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [8, 4, 2, 128]]
        c = self.fresh(rows)
        c.on_move(B.LEFT, ident(rows), ana(rows), steps=5, dirs=[B.LEFT, B.UP] * 2 + [B.LEFT])
        self.assertEqual(c.move_no, 5)
        self.assertEqual(c.off_corner, 0)
        self.assertEqual(len(c.recent_dirs), 5)


# ===========================================================================
#  Evil difficulty (unchanged behavior)
# ===========================================================================
class TestEvilSpawn(unittest.TestCase):
    def test_evil_cell_picks_worst_for_player(self):
        rows = [[4, 8, 16, 32], [2, 0, 0, 0], Z, Z]
        for _ in range(25):
            b = board(rows)
            self.assertEqual(b._evil_cell([(1, 1), (3, 3)], 2), (3, 3))

    def test_evil_spawn_single_empty(self):
        b = board([[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 0, 4],
                   [2, 4, 8, 16]])
        self.assertEqual(b.spawn(force_value=2, evil=True), (2, 2, 2))

    def test_evil_spawn_respects_prefer_edge(self):
        rows = [[4, 0, 0, 8], [16, 0, 32, 64], [128, 256, 0, 2], [2, 4, 8, 16]]
        for _ in range(10):
            b = board(rows)
            r, c, v = b.spawn(force_value=2, prefer_edge=True, evil=True)
            self.assertIn((r, c), [(0, 1), (0, 2)])

    def test_explicit_spawn(self):
        b = board([[0, 0, 0, 0], Z, Z, Z])
        self.assertEqual(b.spawn(force_value=4, at=(2, 3)), (2, 3, 4))


# ===========================================================================
#  Config: survives junk, never half-written
# ===========================================================================
class TestConfig(unittest.TestCase):
    def setUp(self):
        for p in (g.CONFIG_PATH, g.CONFIG_PATH + ".bak", g.GAME_PATH):
            if os.path.exists(p):
                os.remove(p)

    def test_new_players_get_tips_and_their_game_back(self):
        cfg = g.default_config()
        self.assertTrue(cfg["show_tips"])          # it used to be off: no tips at all
        self.assertTrue(cfg["resume_game"])

    def test_resume_off_starts_a_new_game(self):
        game = g.Game()
        game.board.grid = [[2, 4, 8, 16], [0] * 4, [0] * 4, [0] * 4]
        game.board.score = 1234
        game._save_game(force=True)
        game.cfg["resume_game"] = False
        g.save_config(game.cfg)
        game.shutdown()
        game = g.Game()                            # resume off: a fresh board
        self.assertEqual(game.board.score, 0)
        game.cfg["resume_game"] = True
        game.board.grid = [[2, 4, 8, 16], [0] * 4, [0] * 4, [0] * 4]
        game.board.score = 1234
        game._save_game(force=True)
        g.save_config(game.cfg)
        game.shutdown()
        game = g.Game()                            # resume on: the same game
        self.assertEqual(game.board.score, 1234)
        game.shutdown()

    def test_quit_restores_builtin_modes(self):
        cfg = g.default_config()
        cfg["persist_cheats"] = False
        cfg["active_profile"] = 2
        for p in cfg["profiles"]:
            p["map"] = {}
        out = g.finalize_config_for_quit(cfg)
        self.assertEqual(out["profiles"], g.default_config()["profiles"])
        self.assertEqual(out["active_profile"], 0)

    def test_quit_keeps_cheats_when_persisted(self):
        cfg = g.default_config()
        cfg["persist_cheats"] = True
        cfg["active_profile"] = 3
        custom = {"undo": 122, "force_4": 99}
        cfg["profiles"][1]["map"] = dict(custom)
        out = g.finalize_config_for_quit(cfg)
        self.assertEqual(out["profiles"][1]["map"], custom)

    def test_load_config_reseeds_damaged_v2_profiles(self):
        with open(g.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"config_version": 2, "grid_size": 5, "language": "en",
                       "highscore": 4321, "active_profile": 3,
                       "profiles": [{"map": {}}] * 4}, f)
        cfg = g.load_config()
        self.assertEqual(cfg["profiles"], g.default_config()["profiles"])
        self.assertEqual((cfg["highscores"], cfg["grid_size"], cfg["language"]),
                         ({"4": 0, "5": 4321, "6": 0}, 5, "en"))

    def test_junk_values_are_sanitized(self):
        with open(g.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"config_version": 3, "grid_size": 9, "language": "xx",
                       "difficulty": "nightmare", "highscore": -5,
                       "sound": "yes", "active_profile": 17,
                       "profiles": [{"map": {"undo": "z", "bogus": 5}}]}, f)
        cfg = g.load_config()
        self.assertEqual(cfg["grid_size"], 4)
        self.assertEqual(cfg["language"], "he")
        self.assertEqual(cfg["difficulty"], "normal")
        self.assertEqual(cfg["highscores"], {"4": 0, "5": 0, "6": 0})
        self.assertIs(cfg["sound"], True)
        self.assertEqual(cfg["active_profile"], 0)
        self.assertEqual(cfg["profiles"][0]["map"], {})

    def test_config_saved_with_a_bom_still_loads(self):
        # Notepad and PowerShell 5 write UTF-8 with a BOM
        with open(g.CONFIG_PATH, "w", encoding="utf-8-sig") as f:
            json.dump({"config_version": 3, "highscore": 4242, "language": "en"}, f)
        cfg = g.load_config()
        self.assertEqual(cfg["highscores"]["4"], 4242)
        self.assertEqual(cfg["language"], "en")

    def test_the_one_old_best_moves_to_the_selected_size(self):
        # up to 1.0.0 there was one best for all board sizes
        for size, want in ((4, "4"), (5, "5"), (6, "6"), (9, "4"), (None, "4")):
            old = {"config_version": 3, "highscore": 6308, "language": "en"}
            if size is not None:
                old["grid_size"] = size
            with open(g.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(old, f)
            cfg = g.load_config()
            self.assertEqual(cfg["highscores"], {**{"4": 0, "5": 0, "6": 0}, want: 6308})
            # once moved it is not moved again: not onto another size, and
            # not back after a reset
            cfg["grid_size"] = 6
            cfg["highscores"] = {"4": 0, "5": 12, "6": 0}
            g.save_config(cfg)
            self.assertEqual(g.load_config()["highscores"], {"4": 0, "5": 12, "6": 0})

    def test_junk_bests_are_sanitized(self):
        for junk, want in (({"4": -1, "5": "7", "6": 5, "7": 9}, {"4": 0, "5": 0, "6": 5}),
                           ({"4": True}, {"4": 0, "5": 0, "6": 0}),
                           ([1, 2], {"4": 0, "5": 0, "6": 0})):
            with open(g.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"config_version": 3, "highscores": junk}, f)
            self.assertEqual(g.load_config()["highscores"], want)

    def test_corrupt_file_falls_back_to_backup(self):
        cfg = g.default_config()
        cfg["highscores"]["4"] = 777
        g.save_config(cfg)
        cfg["highscores"]["4"] = 888
        g.save_config(cfg)                    # 777 is now the .bak
        with open(g.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write('{"highscore": ')         # power cut mid-write
        self.assertEqual(g.load_config()["highscores"]["4"], 777)
        self.assertFalse(os.path.exists(g.CONFIG_PATH + ".tmp"))

    def test_version_gt(self):
        self.assertTrue(g.Game._version_gt("1.2.0", "1.1.9"))
        self.assertFalse(g.Game._version_gt("0.18.0", "0.18.0"))
        self.assertFalse(g.Game._version_gt("0.9", "0.10"))

    def test_difficulty_table(self):
        self.assertEqual(set(g.DIFFICULTY_EVIL_P), {"normal", "hard", "evil"})
        self.assertEqual(g.DIFFICULTY_EVIL_P["normal"], 0.0)


# ===========================================================================
#  The real Game object, headless
# ===========================================================================
class _Held:
    def __init__(self, keys):
        self.keys = set(keys)

    def __getitem__(self, k):
        return k in self.keys


class TestGameFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for p in (g.CONFIG_PATH, g.CONFIG_PATH + ".bak", g.GAME_PATH):
            if os.path.exists(p):
                os.remove(p)
        cls.game = g.Game()
        cls.game.cfg["active_profile"] = 3      # Mode 4: C clean, Z undo, X smart

    @classmethod
    def tearDownClass(cls):
        cls.game.shutdown()

    def key(self, k):
        self.game.handle_event(pygame.event.Event(
            pygame.KEYDOWN, {"key": k, "mod": 0, "unicode": "", "scancode": 0}))

    def settle(self):
        gm = self.game
        end = time.time() + 2.0
        while time.time() < end:
            gm.frame(1 / 60)
            if not gm.animating and gm.analyst.idle() and not gm._pending_coach:
                return
            time.sleep(0.003)

    def set_board(self, rows):
        gm = self.game
        gm._finish_now()
        gm.board = board(rows)
        gm.history = []
        gm._armed_clean = None
        gm.won = False
        gm._board_changed("resync")
        self.settle()

    def test_settings_screen_layout_and_rows(self):
        gm = self.game
        saved = gm.cfg["language"], gm.state, getattr(gm, "update_status", None)
        try:
            for lang in ("he", "en"):
                gm.cfg["language"] = lang
                gm.state = "settings"
                gm.update_status, gm.update_available = "update", "9.9.9"
                gm.frame(1 / 60)
                # 'Update now' stays exactly where the clean-machine update
                # test clicks it (tools/vm/guest_update_test.ps1: 280, 659)
                self.assertTrue(gm.s_github.hit((280, 659)))
                # the reset buttons in reading order: 'reset settings' first
                a, b = gm.s_reset_settings.rect, gm.s_reset_score.rect
                self.assertTrue(a.x > b.x if lang == "he" else a.x < b.x)
                # nothing overlaps: the preferences row, the resets, the about card
                self.assertLess(gm.s_prefs.rect.bottom, min(a.top, b.top))
                self.assertLess(max(a.bottom, b.bottom), 582)
                # the whole preferences row opens the preferences
                x, y = gm.s_prefs.rect.x + 30, gm.s_prefs.rect.centery
                vs = gm.view_scale
                gm.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                   {"pos": (x * vs, y * vs), "button": 1}))
                self.assertEqual(gm.state, "preferences")
                gm.state = "settings"
        finally:
            gm.cfg["language"], gm.state, gm.update_status = saved
            gm.frame(1 / 60)

    def test_no_lone_word_on_a_tips_last_line(self):
        # '...נסה לבנות לידו' / '2' on the 6x6 board looked broken
        gm = self.game
        txt = "ה-2 בשורה התחתונה שובר את השרשרת של ה-1024 – נסה לבנות לידו 2"
        for w in range(200, 520, 20):
            lines = gm._wrap(txt, gm.f_tiny, w)
            self.assertEqual(" ".join(lines), txt)            # every word, in order
            if len(lines) > 1:
                self.assertIn(" ", lines[-1], (w, lines))

    def test_each_board_size_has_its_own_best(self):
        gm = self.game
        saved = (copy.deepcopy(gm.cfg), gm.state, gm._confirm)
        try:
            gm.cfg["active_profile"] = 0             # honest mode: bests count
            gm.cfg["highscores"] = {"4": 500, "5": 90, "6": 7000}
            for size, best in ((4, 500), (5, 90), (6, 7000)):
                gm.cfg["grid_size"] = size
                gm.new_game(); self.settle()
                self.assertEqual(gm.best_score(), best)
                gm.board.score = best + 10           # a new best, on this board only
                gm.update_highscore()
                self.assertEqual(gm.best_score(), best + 10)
            self.assertEqual(gm.cfg["highscores"], {"4": 510, "5": 100, "6": 7010})
            gm.cfg["grid_size"] = 5                  # a 4x4-sized score on 5x5
            gm.new_game(); self.settle()
            gm.board.score = 99
            gm.update_highscore()                    # below the 5x5 best: nothing
            self.assertEqual(gm.cfg["highscores"]["5"], 100)
            # reset: the question names the board, and only its best goes
            gm.state = "settings"; gm.frame(1 / 60)
            vs = gm.view_scale
            x, y = gm.s_reset_score.rect.center
            gm.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                               {"pos": (x * vs, y * vs), "button": 1}))
            self.assertIn("5×5", gm._confirm[0])
            gm._do_confirmed_action()
            self.assertEqual(gm.cfg["highscores"], {"4": 510, "5": 0, "6": 7010})
            gm._confirm = ("?", "reset_settings")    # the settings reset keeps them
            gm._do_confirmed_action()
            self.assertEqual(gm.cfg["highscores"], {"4": 510, "5": 0, "6": 7010})
        finally:
            gm.cfg, gm.state, gm._confirm = saved
            gm.toast = None
            gm.new_game(); self.settle()

    def test_the_browser_keeps_the_bests_the_same_way(self):
        # the migration is the risky part: run the page's own code in node
        with open(os.path.join(_HERE, "index.html"), encoding="utf-8") as f:
            h = f.read()
        a = h.index("const isScore"); b = h.index("function sanitize(c){")
        js = h[a:b] + ("console.log(JSON.stringify([{highscore:6308,grid_size:5},{highscore:6308},"
                       "{highscore:-2,grid_size:4},{highscore:'x'},{}].map(bestsFromOne)))")
        try:
            out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60).stdout
        except FileNotFoundError:
            self.skipTest("node not installed")
        z = {"4": 0, "5": 0, "6": 0}
        self.assertEqual(json.loads(out), [{**z, "5": 6308}, {**z, "4": 6308}, z, z, z])

    def test_dialog_buttons_in_reading_order(self):
        # 'yes' first: on the right in Hebrew, on the left in English (the
        # desktop kept the English order in Hebrew; the browser did not)
        gm = self.game
        saved = gm.cfg["language"], gm.state, gm._confirm
        try:
            for lang in ("he", "en"):
                gm.cfg["language"] = lang
                gm.state = "settings"
                gm._confirm = (gm.L("reset_settings_q"), "reset_settings")
                gm.frame(1 / 60)
                yes, no = gm.cfm_yes.rect.x, gm.cfm_no.rect.x
                self.assertTrue(yes > no if lang == "he" else yes < no, lang)
        finally:
            gm.cfg["language"], gm.state, gm._confirm = saved
            gm.frame(1 / 60)

    def test_hebrew_is_shown_right_in_the_english_ui(self):
        # 'עברית' in the language switch came out reversed in the English UI
        saved = g._CURRENT_LANG
        try:
            g._CURRENT_LANG = "en"
            self.assertEqual(g.shape_text("עברית"), g._bidi_display("עברית"))
            self.assertNotEqual(g.shape_text("עברית"), "עברית")
            self.assertEqual(g.shape_text("English"), "English")
        finally:
            g._CURRENT_LANG = saved

    def test_the_coach_hears_only_what_the_screen_showed(self):
        gm = self.game
        saved = gm.cfg.get("show_tips"), gm.coach
        try:
            for on in (False, True):
                gm.cfg["show_tips"] = on
                gm.coach = B.Coach()
                gm._tip_told = None
                gm.new_game()
                self.settle()
                gm.frame(1 / 60)                   # one more frame: drawn (or not)
                self.assertIsNotNone(gm._tip)      # the opening tip is up...
                if on:                             # ...and only a drawn one is said
                    self.assertEqual(gm.coach.taught, {"tip_open"})
                else:
                    self.assertEqual(gm.coach.taught, set())
        finally:
            gm.cfg["show_tips"], gm.coach = saved

    def test_fast_keys_are_never_swallowed(self):
        self.set_board([[2, 0, 0, 2], [0, 4, 0, 4], [0, 0, 8, 0], [2, 0, 0, 0]])
        random.seed(4)      # spawns decide whether all four moves CAN move
        before = self.game._move_no
        for k in (pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_UP):
            self.key(k)                     # all inside one slide
        self.settle()
        self.assertEqual(self.game._move_no - before, 4)

    def test_clean_hides_inside_the_next_move(self):
        self.set_board([[2, 512, 64, 4], [0, 32, 8, 16], [0, 8, 4, 4], [2, 0, 0, 0]])
        self.key(pygame.K_c)
        self.assertIsNotNone(self.game._armed_clean)
        self.assertEqual(self.game.board.grid[0][0], 2)      # not yet
        self.assertIsNone(self.game.toast)                   # no tell
        self.key(pygame.K_RIGHT)
        ghosts = [a for a in self.game.anim_tiles if a.get("ghost")]
        self.assertEqual(len(ghosts), 1)
        self.assertEqual(ghosts[0]["from"], (0, 0))
        self.settle()
        self.assertTrue(self.game.cheat_used_this_game)

    def test_clean_with_nothing_to_clean_is_silent(self):
        self.set_board([[2, 0, 0, 0], Z, Z, [0, 0, 0, 4]])
        self.key(pygame.K_c)
        self.assertIsNone(self.game._armed_clean)
        self.assertIsNone(self.game.toast)

    def test_clean_rescues_a_dead_board_at_once(self):
        self.set_board([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 1024]])
        self.key(pygame.K_c)
        self.assertTrue(self.game.board.can_move())

    def test_undo(self):
        self.set_board([[2, 2, 0, 0], Z, Z, Z])
        self.key(pygame.K_LEFT)
        self.settle()
        self.key(pygame.K_z)
        self.settle()
        self.assertEqual(self.game.board.grid[0][:2], [2, 2])

    def test_smart_spawn_is_chosen_by_the_brain(self):
        self.set_board([Z, Z, [0, 0, 0, 4], [64, 32, 16, 8]])
        orig = pygame.key.get_pressed
        pygame.key.get_pressed = lambda: _Held({pygame.K_x})
        try:
            self.key(pygame.K_LEFT)
        finally:
            pygame.key.get_pressed = orig
        self.assertIsNotNone(self.game.pending_spawn[2])
        self.settle()

    def test_escape_answers_dialogs_safely(self):
        gm = self.game
        esc = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE, "mod": 0,
                                                 "unicode": "", "scancode": 0})
        try:
            gm.state = "settings"
            gm._confirm = ("?", "reset_score")
            best = dict(gm.cfg["highscores"])
            gm.handle_event(esc)
            self.assertIsNone(gm._confirm)              # closed, nothing reset
            self.assertEqual(gm.cfg["highscores"], best)
            gm.cfg["active_profile"] = 0                # honest...
            gm.enter_preferences()
            gm.cfg["active_profile"] = 1                # ...then a cheat mode
            gm.leave_preferences()
            self.assertTrue(gm.confessing)
            gm.handle_event(esc)                        # Esc = "never!"
            self.assertFalse(gm.confessing)
            self.assertEqual(gm.cfg["active_profile"], 0)
            gm.state = "settings"
            gm.handle_event(esc)
            self.assertEqual(gm.state, "game")
        finally:                                        # leave the game as found
            gm.confessing = gm.praising = False
            gm._confirm = None
            gm.state = "game"
            gm.toast = None
            gm.cfg["active_profile"] = 3

    def test_resume_after_restart(self):
        self.set_board([[2, 4, 8, 16], Z, [0, 0, 4, 0], [0, 0, 0, 2]])
        self.game.board.score = 1234
        self.game.cheat_used_this_game = True
        g.save_game_state(self.game._game_state())
        g2 = g.Game.__new__(g.Game)
        st = g.load_game_state()
        self.assertEqual(st["grid"][0], [2, 4, 8, 16])
        self.assertEqual(st["score"], 1234)
        self.assertTrue(st["cheat_used"])           # no best-score laundering


# ===========================================================================
#  Updates (against local file:// "releases" - never GitHub)
# ===========================================================================
class TestUpdates(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="2049_upd_")
        self.game = g.Game.__new__(g.Game)          # no window needed
        self.game.cfg = g.default_config()

    def tearDown(self):
        os.environ.pop("TWENTY49_UPDATE_API", None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def url(self, name):
        return "file:///" + os.path.join(self.dir, name).replace("\\", "/")

    def release(self, tag, exe_bytes=None, setup_bytes=None):
        assets = []
        for name, data in (("2049.exe", exe_bytes), ("2049_Setup.exe", setup_bytes)):
            if data is not None:
                with open(os.path.join(self.dir, name), "wb") as f:
                    f.write(data)
                assets.append({"name": name, "size": len(data),
                               "browser_download_url": self.url(name)})
        with open(os.path.join(self.dir, "api.json"), "w", encoding="utf-8") as f:
            json.dump({"tag_name": tag, "assets": assets}, f)
        os.environ["TWENTY49_UPDATE_API"] = self.url("api.json")

    def check(self, installed=False):
        self.game._is_installed = lambda: installed
        _REAL_UPDATE_CHECK(self.game)
        end = time.time() + 10
        while self.game.update_status == "checking" and time.time() < end:
            time.sleep(0.02)
        return self.game.update_status

    def test_newer_release_portable_gets_the_exe(self):
        exe = b"MZ" + os.urandom(200000)
        self.release("v9.9.0", exe, b"MZ" + os.urandom(150000))
        self.assertEqual(self.check(installed=False), "update")
        self.assertEqual(self.game.update_available, "9.9.0")
        self.assertTrue(self.game.update_download_url.endswith("/2049.exe"))
        self.assertEqual(self.game.update_kind, "exe")
        self.assertEqual(self.game.update_size, len(exe))

    def test_newer_release_installed_gets_the_installer(self):
        self.release("v9.9.0", b"MZ" + os.urandom(200000), b"MZ" + os.urandom(150000))
        self.assertEqual(self.check(installed=True), "update")
        self.assertTrue(self.game.update_download_url.endswith("/2049_Setup.exe"))
        self.assertEqual(self.game.update_kind, "installer")

    def test_same_version_is_latest(self):
        self.release("v" + g.APP_VERSION, b"MZ" + os.urandom(200000))
        self.assertEqual(self.check(), "latest")
        self.release(g.APP_VERSION + ".0", b"MZ" + os.urandom(200000))
        self.assertEqual(self.check(), "latest")          # 0.18.0.0 == 0.18.0

    def test_offline(self):
        os.environ["TWENTY49_UPDATE_API"] = self.url("missing.json")
        self.assertEqual(self.check(), "error")

    def download(self):
        self.game.start_update()
        end = time.time() + 15
        while self.game.update_status == "downloading" and time.time() < end:
            time.sleep(0.02)
        return self.game.update_status

    def test_download_is_verified(self):
        good = b"MZ" + os.urandom(300000)
        self.release("v9.9.0", good)
        self.check()
        self.assertEqual(self.download(), "apply")           # ready to apply
        with open(self.game._update_file, "rb") as f:
            self.assertEqual(f.read(), good)
        self.assertAlmostEqual(self.game.update_progress, 1.0)

    def test_corrupt_download_is_refused(self):
        self.release("v9.9.0", b"<html>not a program</html>" + b"x" * 200000)
        self.check()
        self.assertEqual(self.download(), "failed")

    def test_truncated_download_is_refused(self):
        self.release("v9.9.0", b"MZ" + os.urandom(300000))
        self.check()
        self.game.update_size += 1000                         # less than promised
        self.assertEqual(self.download(), "failed")

    def test_version_compare(self):
        gt = g.Game._version_gt
        self.assertTrue(gt("0.18.1", "0.18.0"))
        self.assertTrue(gt("1.0", "0.99.9"))
        self.assertFalse(gt("1.0", "1.0.0"))
        self.assertFalse(gt("1.0.0", "1.0"))


# ===========================================================================
#  One copy at a time
# ===========================================================================
@unittest.skipUnless(sys.platform == "win32", "Windows mutex")
class TestSingleInstance(unittest.TestCase):
    def test_second_copy_is_refused(self):
        code = (
            "import importlib.util,os;"
            "os.environ['SDL_VIDEODRIVER']='dummy';"
            "s=importlib.util.spec_from_file_location('g',r'%s');"
            "g=importlib.util.module_from_spec(s);s.loader.exec_module(g);"
            "g.SINGLE_INSTANCE_NAME='BeniaBot.2049.TestInstance';"
            "a=g.acquire_single_instance();"
            "h=g._instance_handle;"
            "b=g.acquire_single_instance();"
            "print(a,b)" % _GAME_PY)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             timeout=60).stdout.strip().splitlines()
        self.assertEqual(out[-1], "True False")


class TestVersions(unittest.TestCase):
    """One version everywhere. The web page loads its engine as
    brain2049.js?v=VERSION and the service worker caches by URL: if the two
    disagree, a returning visitor runs the new page with the old engine."""
    def test_versions_agree(self):
        import re
        def read(name):
            with open(os.path.join(_HERE, name), encoding="utf-8") as f:
                return f.read()
        v = g.APP_VERSION
        html, sw, iss = read("index.html"), read("sw.js"), read("installer.iss")
        self.assertIn('const APP_VERSION = "%s";' % v, html)
        self.assertIn('<script src="brain2049.js?v=%s"></script>' % v, html)
        self.assertIn('const CACHE = "2049-v%s";' % v, sw)
        self.assertIn('"brain2049.js?v=%s"' % v, sw)
        self.assertIn('#define MyAppVersion "%s"' % v, iss)
        # no other, unversioned way in
        self.assertEqual(len(re.findall(r'src="brain2049\.js', html)), 1)


class TestCompile(unittest.TestCase):
    def test_py_compile(self):
        import py_compile
        py_compile.compile(_GAME_PY, doraise=True)
        py_compile.compile(os.path.join(_HERE, "brain2049.py"), doraise=True)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
