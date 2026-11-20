# -*- coding: utf-8 -*-
"""Tests for 2049 (game) and brain2049 (its thinking engine).

Run:  python test_2049.py
The game module is imported headless (SDL dummy drivers); no window opens
and the user's real config in %APPDATA%\\2049 is never touched (every test
that saves points the config and game files at a temp folder).
"""
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


class TestCoach(unittest.TestCase):
    STUCK = [[256, 4, 64, 8], [16, 32, 8, 2], [2, 4, 2, 0], Z]

    def fresh(self, rows):
        c = B.Coach()
        c.opened = True
        c.habit = 1.0              # a player who keeps the corner
        c.new_game(ana(rows))
        c.current = None           # mid-game: the opening tip is long gone
        return c

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

    def test_a_general_tip_opens_every_game(self):
        start = ana([[2, 0, 0, 0], Z, Z, Z])
        c = B.Coach()
        c.new_game(start)
        self.assertEqual(c.current.key, "tip_open")        # the very first: a corner
        seen = set()
        for _ in range(len(B.OPEN_TIPS)):                  # the corner not kept:
            c.counted_moves, c.corner_moves = 40, 8        # all of them, in turn
            c.new_game(start)
            seen.add(c.current.key)
        self.assertEqual(seen, set(B.OPEN_TIPS))
        seen = set()
        for _ in range(len(B.OPEN_TIPS)):                  # the corner kept: the
            c.counted_moves, c.corner_moves = 40, 36       # others, never the corner
            c.new_game(start)
            seen.add(c.current.key)
        self.assertEqual(seen, set(B.OPEN_TIPS) - {"tip_open"})

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
        self.assertEqual((cfg["highscore"], cfg["grid_size"], cfg["language"]),
                         (4321, 5, "en"))

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
        self.assertEqual(cfg["highscore"], 0)
        self.assertIs(cfg["sound"], True)
        self.assertEqual(cfg["active_profile"], 0)
        self.assertEqual(cfg["profiles"][0]["map"], {})

    def test_config_saved_with_a_bom_still_loads(self):
        # Notepad and PowerShell 5 write UTF-8 with a BOM
        with open(g.CONFIG_PATH, "w", encoding="utf-8-sig") as f:
            json.dump({"config_version": 3, "highscore": 4242, "language": "en"}, f)
        cfg = g.load_config()
        self.assertEqual(cfg["highscore"], 4242)
        self.assertEqual(cfg["language"], "en")

    def test_corrupt_file_falls_back_to_backup(self):
        cfg = g.default_config()
        cfg["highscore"] = 777
        g.save_config(cfg)
        cfg["highscore"] = 888
        g.save_config(cfg)                    # 777 is now the .bak
        with open(g.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write('{"highscore": ')         # power cut mid-write
        self.assertEqual(g.load_config()["highscore"], 777)
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
            best = gm.cfg["highscore"]
            gm.handle_event(esc)
            self.assertIsNone(gm._confirm)              # closed, nothing reset
            self.assertEqual(gm.cfg["highscore"], best)
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
