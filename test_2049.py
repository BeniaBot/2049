# -*- coding: utf-8 -*-
"""Unit tests for the v0.17.0 changes in 2049.py (spec sections 1, 3, 4, 5).

Run:  python test_2049.py
The game module is imported headless (SDL dummy drivers); no window opens
and the user's real config in %APPDATA%\\2049 is never touched.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

_HERE = os.path.dirname(os.path.abspath(__file__))
_GAME_PY = os.path.join(_HERE, "2049.py")

spec_ = importlib.util.spec_from_file_location("game2049", _GAME_PY)
g = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(g)


def board(rows):
    """Build a Board directly from a list of rows."""
    b = g.Board(len(rows))
    b.grid = [list(r) for r in rows]
    return b


Z = [0, 0, 0, 0]


class TestMovement(unittest.TestCase):
    # 1. Movement sanity
    def test_left_merge_and_score(self):
        b = board([[2, 2, 4, 0], Z, Z, Z])
        changed, anims, merges = b.move("left")
        self.assertTrue(changed)
        self.assertEqual(b.grid[0], [4, 4, 0, 0])
        self.assertEqual(b.score, 4)          # score gain of the single merge
        self.assertIn((0, 0, 4), merges)

    def test_merge_once_rule(self):
        b = board([[2, 2, 2, 2], Z, Z, Z])
        changed, _, merges = b.move("left")
        self.assertTrue(changed)
        self.assertEqual(b.grid[0], [4, 4, 0, 0])   # NOT [8,0,0,0]
        self.assertEqual(b.score, 8)
        self.assertEqual(sorted(merges), [(0, 0, 4), (0, 1, 4)])


class TestBlockedPairValue(unittest.TestCase):
    # 2. blocked_pair_value
    def test_row_axis(self):
        b = board([[128, 2, 0, 128], Z, Z, Z])
        self.assertEqual(b.blocked_pair_value(0, 1), 128)

    def test_column_axis(self):
        b = board([[0, 0, 64, 0],
                   [0, 0, 0, 0],
                   [0, 0, 2, 0],
                   [0, 0, 64, 0]])
        self.assertEqual(b.blocked_pair_value(2, 2), 64)

    def test_flankers_differ(self):
        b = board([[128, 2, 0, 64], Z, Z, Z])
        self.assertEqual(b.blocked_pair_value(0, 1), 0)

    def test_flanker_equals_v(self):
        b = board([[4, 4, 0, 4], Z, Z, Z])
        self.assertEqual(b.blocked_pair_value(0, 1), 0)


class TestStuckV2(unittest.TestCase):
    # 3. positive: the classic 128-2-128 blocker
    def test_blocker_between_big_pair_is_stuck(self):
        b = board([[128, 2, 0, 128], Z, Z, Z])
        s = b._stuck_score(0, 1)
        self.assertIsNotNone(s)
        self.assertGreater(s, 0)
        # remove_stuck_low must pick exactly that cell
        picked = b.remove_stuck_low()
        self.assertEqual(picked, (0, 1))
        self.assertEqual(b.grid[0][1], 0)

    # 4. negative: rescuable corner tile with soft walls and open space
    def test_soft_corner_is_rescuable(self):
        # 2 in the corner, neighbors 4 and 8 (soft: min < 4*v), open space
        # elsewhere; the stray 4 keeps all four directions already usable so
        # removing the 2 unlocks nothing (fd == 0) -> realistic rescue -> None
        b = board([[2, 4, 0, 0],
                   [8, 0, 0, 0],
                   [0, 0, 4, 0],
                   [0, 0, 0, 0]])
        self.assertIsNone(b._stuck_score(0, 0))

    # 5. hopeless: fully boxed by >= 8 walls, dense board, no air anywhere
    def test_hopeless_boxed_tile(self):
        b = board([[8, 16, 8, 16],
                   [16, 2, 32, 8],
                   [8, 32, 16, 32],
                   [16, 8, 32, 16]])
        s = b._stuck_score(1, 1)
        self.assertIsNotNone(s)
        self.assertGreater(s, 0)
        self.assertEqual(b.remove_stuck_low(), (1, 1))

    # 4b. a lone low tile in the corner of a NEARLY-EMPTY board is never
    # "stuck" - a partner will spawn eventually (regression: the old jam
    # clause flagged it because removing it unlocked a direction)
    def test_lone_corner_tile_on_sparse_board(self):
        b = board([[2, 4, 0, 0],
                   [8, 0, 0, 0],
                   Z, Z])
        self.assertIsNone(b._stuck_score(0, 0))
        self.assertIsNone(b.remove_stuck_low())

    # 4c. jam clause: on a fully locked board (freedom == 0), a boxed tile
    # whose removal re-opens movement IS stuck - even with a smaller
    # neighbor (buried == False), this is the "last direction" rescue
    def test_jam_on_locked_board(self):
        b = board([[2, 4, 8, 16],
                   [4, 8, 16, 32],
                   [8, 16, 32, 64],
                   [16, 32, 64, 128]])
        self.assertEqual(b.freedom(), 0)      # board is locked
        s = b._stuck_score(1, 1)              # the 8: neighbor 4 is smaller
        self.assertIsNotNone(s)
        self.assertGreater(s, 0)

    # 6. all-mergeable board -> nothing is stuck
    def test_all_mergeable_returns_none(self):
        rows = [[2, 2, 4, 4],
                [8, 8, 16, 16],
                [32, 32, 64, 64],
                [128, 128, 256, 256]]
        b = board(rows)
        self.assertIsNone(b.remove_stuck_low())
        self.assertEqual(b.grid, rows)        # untouched


class TestEvilSpawn(unittest.TestCase):
    # 7. _evil_cell determinism: unique quality minimum -> always chosen
    def test_evil_cell_picks_worst_for_player(self):
        rows = [[4, 8, 16, 32],
                [2, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0]]
        # Placing a 2 at (1,1) gifts the player a merge (best reply q=70);
        # placing it at (3,3) is dead weight in the far corner (best q=62).
        # Unique minimum -> the random tie-break has one candidate.
        for _ in range(25):
            b = board(rows)
            self.assertEqual(b._evil_cell([(1, 1), (3, 3)], 2), (3, 3))

    # 8. spawn(evil=True) with one empty cell + prefer_edge respected
    def test_evil_spawn_single_empty(self):
        b = board([[2, 4, 8, 16],
                   [32, 64, 128, 256],
                   [512, 1024, 0, 4],
                   [2, 4, 8, 16]])
        res = b.spawn(force_value=2, evil=True)
        self.assertEqual(res, (2, 2, 2))
        self.assertEqual(b.grid[2][2], 2)

    def test_evil_spawn_respects_prefer_edge(self):
        rows = [[4, 0, 0, 8],
                [16, 0, 32, 64],
                [128, 256, 0, 2],
                [2, 4, 8, 16]]
        # empties: (0,1),(0,2) on the edge; (1,1),(2,2) interior.
        for _ in range(10):
            b = board(rows)
            r, c, v = b.spawn(force_value=2, prefer_edge=True, evil=True)
            self.assertEqual(v, 2)
            self.assertIn((r, c), [(0, 1), (0, 2)],
                          "evil spawn escaped the prefer_edge filter")


class TestInDanger(unittest.TestCase):
    # 9. in_danger
    def test_cornered_board_is_danger(self):
        b = board([[2, 4, 8, 16],
                   [32, 64, 128, 256],
                   [512, 2, 4, 8],
                   [16, 32, 64, 0]])
        # 1 empty; the only changing moves (right/down) just slide into the
        # hole: still 1 empty, 0 pairs afterwards -> no escape.
        self.assertTrue(b.in_danger())

    def test_escape_move_clears_danger(self):
        b = board([[2, 4, 8, 16],
                   [32, 64, 128, 256],
                   [512, 2, 4, 8],
                   [16, 2, 4, 0]])
        # "down" merges the 2s and 4s in cols 1-2 -> 3 empties -> escape.
        self.assertFalse(b.in_danger())

    def test_open_board_never_danger(self):
        b = board([[2, 4, 0, 0], Z, Z, Z])
        self.assertFalse(b.in_danger())


class TestEdgeOrdered(unittest.TestCase):
    # 10. edge_ordered
    def test_ordered_corner_row(self):
        b = board([[256, 128, 64, 2], Z, Z, Z])
        self.assertTrue(b.edge_ordered())

    def test_gap_breaks_order(self):
        b = board([[256, 128, 0, 2], Z, Z, Z])
        self.assertFalse(b.edge_ordered())

    def test_increase_breaks_order(self):
        b = board([[256, 64, 128, 2], Z, Z, Z])
        self.assertFalse(b.edge_ordered())

    def test_max_not_in_corner(self):
        b = board([[0, 0, 0, 0],
                   [8, 256, 4, 2],
                   Z, Z])
        self.assertFalse(b.edge_ordered())


class TestConfig(unittest.TestCase):
    # 11. finalize_config_for_quit
    def test_quit_restores_builtin_modes(self):
        cfg = g.default_config()
        cfg["persist_cheats"] = False
        cfg["active_profile"] = 2
        for p in cfg["profiles"]:
            p["map"] = {}                     # simulate wiped/dirty modes
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
        self.assertEqual(out["active_profile"], 3)

    # 12. load_config migration v2 -> v3 (against a redirected CONFIG_PATH)
    def test_load_config_reseeds_damaged_v2_profiles(self):
        tmpdir = tempfile.mkdtemp(prefix="2049_test_cfg_")
        tmp_path = os.path.join(tmpdir, "2049_config.json")
        damaged = {
            "config_version": 2,
            "grid_size": 5,
            "language": "en",
            "highscore": 4321,
            "active_profile": 3,
            "profiles": [{"map": {}}, {"map": {}}, {"map": {}}, {"map": {}}],
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(damaged, f)
        real_path = g.CONFIG_PATH
        try:
            g.CONFIG_PATH = tmp_path
            cfg = g.load_config()
        finally:
            g.CONFIG_PATH = real_path
            shutil.rmtree(tmpdir, ignore_errors=True)
        self.assertEqual(cfg["config_version"], 3)
        self.assertEqual(cfg["profiles"], g.default_config()["profiles"])
        self.assertEqual(cfg["active_profile"], 0)
        # user's own data survives the repair
        self.assertEqual(cfg["highscore"], 4321)
        self.assertEqual(cfg["grid_size"], 5)
        self.assertEqual(cfg["language"], "en")

    # 13. _version_gt
    def test_version_gt(self):
        self.assertTrue(g.Game._version_gt("1.2.0", "1.1.9"))
        self.assertFalse(g.Game._version_gt("0.17.0", "0.17.0"))
        self.assertFalse(g.Game._version_gt("0.9", "0.10"))

    # 14. difficulty constant
    def test_difficulty_table(self):
        self.assertEqual(set(g.DIFFICULTY_EVIL_P), {"normal", "hard", "evil"})
        self.assertEqual(g.DIFFICULTY_EVIL_P["normal"], 0.0)
        for k, p in g.DIFFICULTY_EVIL_P.items():
            self.assertGreaterEqual(p, 0.0, k)
            self.assertLessEqual(p, 1.0, k)
        self.assertEqual(g.default_config().get("difficulty"), "normal")


class TestCompile(unittest.TestCase):
    def test_py_compile(self):
        import py_compile
        py_compile.compile(_GAME_PY, doraise=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
