"""
2049  -  Enhanced 2048, classic look, Hebrew by default, real slide animation.
Fully offline. Compile to a single .exe with PyInstaller (see build_exe.bat).

Every hidden assist looks exactly like an ordinary move - no visible tell.
Assists are triggered by user-mapped hidden keys, configured in Settings.
"""

import pygame
import random
import json
import os
import sys
import copy
import math

APP_NAME    = "2049"
APP_VERSION = "0.14.0"
GITHUB_REPO = "BeniaBot/2049"   # owner/repo for auto-update checks

# Optional RTL shaping for Hebrew. Falls back gracefully if unavailable.
try:
    from bidi.algorithm import get_display as _bidi_display
    _HAS_BIDI = True
except Exception:
    _HAS_BIDI = False
    def _bidi_display(s):
        return s

# ----------------------------------------------------------------------------
# Paths (works as script and as PyInstaller-frozen exe)
# ----------------------------------------------------------------------------
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def make_dpi_aware():
    """On Windows, opt out of DPI virtualization so the window isn't
    stretched/blurred by the OS on high-DPI displays."""
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def user_data_dir():
    """Per-user writable folder for saving config/highscore, so it survives
    even if files next to the exe are deleted."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or \
               os.path.join(os.path.expanduser("~"), ".local", "share")
    d = os.path.join(base, "2049")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = app_dir()  # fallback: next to the exe
    return d

def resource_path(rel):
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, rel)

CONFIG_PATH = os.path.join(user_data_dir(), "2049_config.json")

# Migrate an old config that lived next to the exe (from earlier versions).
_OLD_CONFIGS = [
    os.path.join(app_dir(), "2048plus_config.json"),
    os.path.join(app_dir(), "2049_config.json"),
]
_OLD_CONFIG = _OLD_CONFIGS[0]
try:
    if os.path.exists(_OLD_CONFIG) and not os.path.exists(CONFIG_PATH):
        import shutil
        shutil.copy2(_OLD_CONFIG, CONFIG_PATH)
except Exception:
    pass

# ----------------------------------------------------------------------------
# Classic 2048 palette
# ----------------------------------------------------------------------------
BG          = (250, 248, 239)   # cream background
BOARD_BG    = (187, 173, 160)   # board frame
EMPTY_CELL  = (205, 193, 180)   # empty cell
TEXT_DARK   = (119, 110, 101)
TEXT_LIGHT  = (249, 246, 242)
BTN_BG      = (143, 122, 102)
BTN_TEXT    = (249, 246, 242)
SCORE_BG    = (187, 173, 160)
ACCENT      = (237, 124, 66)    # warm orange highlight (matches 32-tile)
CARD_BG     = (238, 228, 214)   # soft card background for settings rows

TILE_COLORS = {
    2:(238,228,218), 4:(237,224,200), 8:(242,177,121), 16:(245,149,99),
    32:(246,124,95), 64:(246,94,59), 128:(237,207,114), 256:(237,204,97),
    512:(237,200,80), 1024:(237,197,63), 2048:(237,194,46),
    4096:(60,58,50), 8192:(60,58,50),
}
def tile_color(v):
    return TILE_COLORS.get(v, (60, 58, 50))
def tile_text_color(v):
    return TEXT_DARK if v in (2, 4) else TEXT_LIGHT

# ----------------------------------------------------------------------------
# Localization
# ----------------------------------------------------------------------------
STRINGS = {
    "he": {
        "score":"\u05e0\u05d9\u05e7\u05d5\u05d3", "best":"\u05e9\u05d9\u05d0",
        "new_game":"\u05de\u05e9\u05d7\u05e7 \u05d7\u05d3\u05e9",
        "settings":"\u05d4\u05d2\u05d3\u05e8\u05d5\u05ea", "menu":"\u05ea\u05e4\u05e8\u05d9\u05d8",
        "play":"\u05e9\u05d7\u05e7", "quit":"\u05d9\u05e6\u05d9\u05d0\u05d4", "back":"\u05d7\u05d6\u05e8\u05d4",
        "subtitle":"\u05d4\u05de\u05d4\u05d3\u05d5\u05e8\u05d4 \u05d4\u05de\u05e9\u05d5\u05db\u05dc\u05dc\u05ea",
        "you_win":"\u05d4\u05d2\u05e2\u05ea \u05dc-2048!",
        "keep_going":"\u05d4\u05de\u05e9\u05da  \u2022  \u05de\u05e9\u05d7\u05e7 \u05d7\u05d3\u05e9",
        "game_over":"\u05d4\u05de\u05e9\u05d7\u05e7 \u05e0\u05d2\u05de\u05e8",
        "press_new":"\u05dc\u05d7\u05e5 Enter \u05dc\u05de\u05e9\u05d7\u05e7 \u05d7\u05d3\u05e9",
        "tips":"\u05d8\u05d9\u05e4: \u05d4\u05e9\u05ea\u05de\u05e9 \u05d1-\u2190 \u2191 \u2192 \u2193 \u05dc\u05de\u05e9\u05d7\u05e7!",
        "grid_size":"\u05d2\u05d5\u05d3\u05dc \u05dc\u05d5\u05d7", "language":"\u05e9\u05e4\u05d4",
        "game_mode":"\u05de\u05e6\u05d1 \u05de\u05e9\u05d7\u05e7",
        "assist_keys":"\u05de\u05e7\u05e9\u05d9 \u05e2\u05d6\u05e8\u05d4 \u05e0\u05e1\u05ea\u05e8\u05d9\u05dd",
        "click_cycle":"\u05dc\u05d7\u05e5 \u05e2\u05dc \u05ea\u05d9\u05d1\u05ea \u05de\u05e7\u05e9 \u05db\u05d3\u05d9 \u05dc\u05d4\u05d7\u05dc\u05d9\u05e3",
        "press_key":"\u05dc\u05d7\u05e5 \u05de\u05e7\u05e9...",
        "click_to_set":"\u05dc\u05d7\u05e5 \u05e2\u05dc \u05ea\u05d9\u05d1\u05d4 \u05d5\u05d0\u05d6 \u05e2\u05dc \u05de\u05e7\u05e9 \u05d1\u05de\u05e7\u05dc\u05d3\u05ea. Backspace \u05dc\u05e0\u05d9\u05e7\u05d5\u05d9.",
        "hold":"\u05d4\u05d7\u05d6\u05e7", "tap":"\u05dc\u05d7\u05d9\u05e6\u05d4", "none":"\u05dc\u05dc\u05d0",
        "hebrew":"\u05e2\u05d1\u05e8\u05d9\u05ea", "english":"English",
        "mode_infinite":"\u05de\u05e6\u05d1 \u05d0\u05d9\u05e0\u05e1\u05d5\u05e4\u05d9",
        "mode_target":"\u05de\u05e6\u05d1 \u05e9\u05d1\u05d9\u05e8\u05ea \u05e9\u05d9\u05d0",
        "sound_on":"\u05e7\u05d5\u05dc \u05d3\u05dc\u05d5\u05e7", "sound_off":"\u05e7\u05d5\u05dc \u05db\u05d1\u05d5\u05d9",
        "sound":"\u05e6\u05dc\u05d9\u05dc\u05d9\u05dd", "on":"\u05d3\u05dc\u05d5\u05e7", "off":"\u05db\u05d1\u05d5\u05d9",
        "win_mode":"\u05de\u05e6\u05d1 \u05e0\u05d9\u05e6\u05d7\u05d5\u05df",
        "show_tips":"\u05d4\u05e6\u05d2 \u05e2\u05e6\u05d5\u05ea",
        "reset_settings":"\u05d0\u05e4\u05e1 \u05d4\u05d2\u05d3\u05e8\u05d5\u05ea",
        "reset_score":"\u05d0\u05e4\u05e1 \u05e9\u05d9\u05d0",
        "reset_settings_q":"\u05dc\u05d0\u05e4\u05e1 \u05d0\u05ea \u05db\u05dc \u05d4\u05d4\u05d2\u05d3\u05e8\u05d5\u05ea \u05dc\u05d1\u05e8\u05d9\u05e8\u05ea \u05d4\u05de\u05d7\u05d3\u05dc?",
        "reset_score_q":"\u05dc\u05d0\u05e4\u05e1 \u05d0\u05ea \u05d4\u05e9\u05d9\u05d0 \u05d4\u05d0\u05d9\u05e9\u05d9?",
        "yes":"\u05db\u05df",
        "no":"\u05dc\u05d0",
        "done_reset":"\u05d0\u05d5\u05e4\u05e1 \u05d1\u05d4\u05e6\u05dc\u05d7\u05d4",
        "tips_list":[
            "\u05e9\u05de\u05d5\u05e8 \u05d0\u05ea \u05d4\u05d0\u05e8\u05d9\u05d7 \u05d4\u05d2\u05d1\u05d5\u05d4 \u05d1\u05e4\u05d9\u05e0\u05d4 \u05d5\u05d0\u05dc \u05ea\u05d6\u05d9\u05d6 \u05d0\u05d5\u05ea\u05d5",
            "\u05e0\u05e1\u05d4 \u05dc\u05e9\u05de\u05d5\u05e8 \u05e9\u05d5\u05e8\u05d4 \u05d0\u05d7\u05ea \u05de\u05dc\u05d0\u05d4 \u05d5\u05de\u05e1\u05d5\u05d3\u05e8\u05ea",
            "\u05d1\u05e0\u05d4 \u05e9\u05e8\u05e9\u05e8\u05ea \u05de\u05e1\u05e4\u05e8\u05d9\u05dd \u05d9\u05d5\u05e8\u05d3\u05ea \u05dc\u05d0\u05d5\u05e8\u05da \u05e9\u05d5\u05e8\u05d4",
            "\u05d4\u05d6\u05d6 \u05d1\u05e2\u05d9\u05e7\u05e8 \u05dc\u05e9\u05e0\u05d9 \u05db\u05d9\u05d5\u05d5\u05e0\u05d9\u05dd \u05e7\u05d1\u05d5\u05e2\u05d9\u05dd",
            "\u05d0\u05dc \u05ea\u05de\u05dc\u05d0 \u05d0\u05ea \u05d4\u05dc\u05d5\u05d7 \u2013 \u05d4\u05e9\u05d0\u05e8 \u05de\u05e7\u05d5\u05dd \u05dc\u05ea\u05de\u05e8\u05d5\u05df",
        ],
        "tip_stuck":"\u05d9\u05e9 \u05d0\u05e8\u05d9\u05d7 \u05e0\u05de\u05d5\u05da \u05ea\u05e7\u05d5\u05e2 \u2013 \u05e0\u05e1\u05d4 \u05dc\u05e9\u05d7\u05e8\u05e8 \u05d0\u05d5\u05ea\u05d5",
        "tip_full":"\u05d4\u05dc\u05d5\u05d7 \u05de\u05ea\u05de\u05dc\u05d0! \u05de\u05d6\u05d2 \u05d0\u05e8\u05d9\u05d7\u05d9\u05dd \u05d1\u05d3\u05d7\u05d9\u05e4\u05d5\u05ea",
        "tip_corner":"\u05e9\u05de\u05d5\u05e8 \u05d0\u05ea \u05d4\u05d0\u05e8\u05d9\u05d7 \u05d4\u05d2\u05d1\u05d5\u05d4 \u05d1\u05e4\u05d9\u05e0\u05d4",
        "tip_lost_corner":"\u05d4\u05d0\u05e8\u05d9\u05d7 \u05d4\u05d2\u05d1\u05d5\u05d4 \u05d9\u05e6\u05d0 \u05de\u05d4\u05e4\u05d9\u05e0\u05d4 \u2013 \u05d4\u05d7\u05d6\u05e8 \u05d0\u05d5\u05ea\u05d5!",
        "tip_good_corner":"\u05d9\u05d5\u05e4\u05d9! \u05d4\u05d7\u05d6\u05e8\u05ea \u05d0\u05ea \u05d4\u05d2\u05d1\u05d5\u05d4 \u05dc\u05e4\u05d9\u05e0\u05d4",
        "tip_good_clear":"\u05d9\u05e4\u05d4 \u05de\u05d0\u05d5\u05d3! \u05e9\u05d7\u05e8\u05e8\u05ea \u05d0\u05ea \u05d4\u05dc\u05d5\u05d7",
        "tip_good_merge":"\u05de\u05e6\u05d5\u05d9\u05df! \u05de\u05d9\u05d6\u05d5\u05d2 \u05d2\u05d3\u05d5\u05dc",
        "tip_good_space":"\u05d9\u05e4\u05d4! \u05e4\u05d9\u05e0\u05d9\u05ea \u05d4\u05e8\u05d1\u05d4 \u05de\u05e7\u05d5\u05dd",
        "infinite":"\u05d0\u05d9\u05e0\u05e1\u05d5\u05e4\u05d9", "target":"\u05e9\u05d1\u05d9\u05e8\u05ea \u05e9\u05d9\u05d0",
        "preferences":"\u05d4\u05e2\u05d3\u05e4\u05d5\u05ea",
        "prefs_hint":"\u05d4\u05d2\u05d3\u05e8\u05d5\u05ea \u05de\u05ea\u05e7\u05d3\u05de\u05d5\u05ea",
        "prefs_title":"\u05de\u05e7\u05dc\u05d8 \u05d4\u05e8\u05de\u05d0\u05d9\u05dd \u05d5\u05d4\u05e0\u05d5\u05db\u05dc\u05d9\u05dd",
        "prefs_sub":"\u05db\u05d0\u05df \u05de\u05ea\u05d0\u05e1\u05e4\u05d9\u05dd \u05db\u05dc \u05d0\u05dc\u05d5 \u05e9\u05dc\u05d0 \u05de\u05e1\u05e4\u05d9\u05e7 \u05d8\u05d5\u05d1\u05d9\u05dd \u05d1\u05d6\u05db\u05d5\u05ea \u05e2\u05e6\u05de\u05dd",
        "persist_cheats":"\u05e9\u05de\u05d5\u05e8 \u05e8\u05de\u05d0\u05d5\u05d9\u05d5\u05ea \u05d1\u05d9\u05df \u05d4\u05e4\u05e2\u05dc\u05d5\u05ea",
        "count_best":"\u05d7\u05e9\u05d1 \u05e8\u05de\u05d0\u05d5\u05d9\u05d5\u05ea \u05d1\u05e9\u05d9\u05d0",
        "credit":"\u05e0\u05d5\u05e6\u05e8 \u05e2\u05dc \u05d9\u05d3\u05d9 Claude \u2022 BeniaBot",
        "about":"\u05d0\u05d5\u05d3\u05d5\u05ea",
        "opened_by":"\u05e4\u05d5\u05ea\u05d7 \u05e2\u05dc \u05d9\u05d3\u05d9",
        "up_to_date":"\u05d4\u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d4 \u05de\u05e2\u05d5\u05d3\u05db\u05e0\u05ea \u05dc\u05d2\u05e8\u05e1\u05d4 \u05d4\u05d0\u05d7\u05e8\u05d5\u05e0\u05d4",
        "update_ready":"\u05d2\u05e8\u05e1\u05d4 \u05d7\u05d3\u05e9\u05d4 \u05d6\u05de\u05d9\u05e0\u05d4 \u05dc\u05d4\u05d5\u05e8\u05d3\u05d4",
        "check_again":"\u05d1\u05d3\u05d5\u05e7 \u05e9\u05d5\u05d1",
        "checking":"\u05d1\u05d5\u05d3\u05e7...",
        "visit_github":"\u05d1\u05e7\u05e8 \u05d1\u05e2\u05de\u05d5\u05d3 \u05d4-GitHub",
        "download_update":"\u05d4\u05d5\u05e8\u05d3 \u05d2\u05e8\u05e1\u05d4 \u05d7\u05d3\u05e9\u05d4",
        "version_lbl":"\u05d2\u05e8\u05e1\u05d4",
        "update_avail":"\u05e2\u05d3\u05db\u05d5\u05df \u05d6\u05de\u05d9\u05df!",
        "about":"\u05d0\u05d5\u05d3\u05d5\u05ea",
        "confess_title":"\u05e8\u05d2\u05e2 \u05d0\u05d7\u05d3...",
        "confess_body":"\u05db\u05d3\u05d9 \u05dc\u05e9\u05de\u05d5\u05e8 \u05d4\u05d2\u05d3\u05e8\u05d5\u05ea \u05e8\u05de\u05d0\u05d5\u05ea, \u05e2\u05dc\u05d9\u05da \u05dc\u05d4\u05d5\u05d3\u05d5\u05ea:",
        "confess_line":"\"\u05d0\u05e0\u05d9 \u05de\u05e8\u05de\u05d4 \u05db\u05d9 \u05d0\u05e0\u05d9 \u05dc\u05d0 \u05de\u05e1\u05e4\u05d9\u05e7 \u05d8\u05d5\u05d1\"",
        "confess_yes":"\u05d0\u05e0\u05d9 \u05de\u05d5\u05d3\u05d4",
        "confess_no":"\u05dc\u05e2\u05d5\u05dc\u05dd \u05dc\u05d0!",
        "confess_rejected":"\u05d0\u05d6 \u05e9\u05d5\u05d1 \u05dc\u05d0\u05d9\u05de\u05d5\u05e0\u05d9\u05dd. \u05d4\u05d4\u05d2\u05d3\u05e8\u05d5\u05ea \u05dc\u05d0 \u05e0\u05e9\u05de\u05e8\u05d5.",
        "praise_title":"\u05db\u05dc \u05d4\u05db\u05d1\u05d5\u05d3!",
        "praise_body":"\u05d1\u05d7\u05e8\u05ea \u05dc\u05d1\u05d8\u05dc \u05d0\u05ea \u05d4\u05e8\u05de\u05d0\u05d5\u05ea \u05d5\u05dc\u05d4\u05ea\u05de\u05d5\u05d3\u05d3 \u05db\u05de\u05d5 \u05d2\u05d1\u05e8!",
        "praise_body2":"\u05d6\u05d4 \u05de\u05e8\u05e9\u05d9\u05dd. \u05d4\u05e9\u05d9\u05e0\u05d5\u05d9 \u05e0\u05e9\u05de\u05e8 \u05d0\u05d5\u05d8\u05d5\u05de\u05d8\u05d9\u05ea.",
        "praise_ok":"\u05ea\u05d5\u05d3\u05d4!",
        "praise_toast":"\u05d9\u05d0\u05d0\u05dc\u05d4, \u05dc\u05e9\u05d7\u05e7 '\u05e2\u05dc \u05d0\u05de\u05ea'\n\u05e8\u05e7 \u05d0\u05dc \u05ea\u05ea\u05d9\u05d9\u05d0\u05e9 \u05de\u05d4\u05e8 \u05de\u05d3\u05d9!",
        "mode_names":["\u05de\u05e6\u05d1 1 - \u05e8\u05d2\u05d9\u05dc",
                      "\u05de\u05e6\u05d1 2 - \u05e9\u05dc\u05d9\u05d8\u05d4 \u05d1-2/4",
                      "\u05de\u05e6\u05d1 3 - \u05de\u05e0\u05e7\u05d4",
                      "\u05de\u05e6\u05d1 4 - \u05e2\u05e8\u05db\u05ea \u05de\u05dc\u05d0\u05d4"],
        "actions":{
            "force_2":"\u05d4\u05d0\u05e8\u05d9\u05d7 \u05d4\u05d1\u05d0 \u05d9\u05d4\u05d9\u05d4 2",
            "force_4":"\u05d4\u05d0\u05e8\u05d9\u05d7 \u05d4\u05d1\u05d0 \u05d9\u05d4\u05d9\u05d4 4",
            "spawn_corner":"\u05d0\u05e8\u05d9\u05d7 \u05d7\u05d3\u05e9 \u05d1\u05e9\u05d5\u05dc\u05d9\u05d9\u05dd",
            "clean_stuck":"\u05e0\u05e7\u05d4 \u05d0\u05e8\u05d9\u05d7 \u05ea\u05e7\u05d5\u05e2",
            "undo":"\u05d1\u05d8\u05dc \u05de\u05d4\u05dc\u05da",
        },
        "action_detail":{
            "force_2":"\u05d4\u05d7\u05d6\u05e7 \u05d1\u05de\u05d4\u05dc\u05da \u2013 \u05d4\u05d0\u05e8\u05d9\u05d7 \u05e9\u05d9\u05d5\u05e4\u05d9\u05e2 \u05d9\u05d4\u05d9\u05d4 2 \u05d5\u05dc\u05d0 4 (\u05e9\u05d5\u05de\u05e8 \u05e2\u05dc \u05dc\u05d5\u05d7 \u05e0\u05e7\u05d9)",
            "force_4":"\u05d4\u05d7\u05d6\u05e7 \u05d1\u05de\u05d4\u05dc\u05da \u2013 \u05d4\u05d0\u05e8\u05d9\u05d7 \u05e9\u05d9\u05d5\u05e4\u05d9\u05e2 \u05d9\u05d4\u05d9\u05d4 4 (\u05e6\u05d5\u05d1\u05e8 \u05e0\u05e7\u05d5\u05d3\u05d5\u05ea \u05de\u05d4\u05e8)",
            "spawn_corner":"\u05d4\u05d7\u05d6\u05e7 \u05d1\u05de\u05d4\u05dc\u05da \u2013 \u05d4\u05d0\u05e8\u05d9\u05d7 \u05d4\u05d7\u05d3\u05e9 \u05d9\u05d5\u05e4\u05d9\u05e2 \u05d1\u05e9\u05d5\u05dc\u05d9\u05d9\u05dd \u05d5\u05dc\u05d0 \u05d1\u05de\u05e8\u05db\u05d6",
            "clean_stuck":"\u05dc\u05d7\u05d9\u05e6\u05d4 \u2013 \u05de\u05e2\u05dc\u05d9\u05dd \u05d0\u05e8\u05d9\u05d7 \u05e0\u05de\u05d5\u05da \u05e9\u05ea\u05e7\u05d5\u05e2 \u05d1\u05d9\u05df \u05d2\u05d1\u05d5\u05d4\u05d9\u05dd",
            "undo":"\u05dc\u05d7\u05d9\u05e6\u05d4 \u2013 \u05de\u05d7\u05d6\u05d9\u05e8 \u05d0\u05ea \u05d4\u05dc\u05d5\u05d7 \u05dc\u05e4\u05e0\u05d9 \u05d4\u05de\u05d4\u05dc\u05da \u05d4\u05d0\u05d7\u05e8\u05d5\u05df",
        },
    },
    "en": {
        "score":"SCORE", "best":"BEST", "new_game":"New Game",
        "settings":"Settings", "menu":"Menu", "play":"Play", "quit":"Quit",
        "back":"Back", "subtitle":"enhanced edition",
        "you_win":"You reached 2048!", "keep_going":"Keep going  \u2022  New game",
        "game_over":"Game over", "press_new":"Press Enter for new game",
        "tips":"Tips: use \u2190 \u2191 \u2192 \u2193 to play!",
        "grid_size":"Grid size", "language":"Language", "game_mode":"Game mode",
        "assist_keys":"Hidden assist keys", "click_cycle":"Click a key box to cycle keys.",
        "press_key":"Press a key...",
        "click_to_set":"Click a box, then press any key. Backspace to clear.",
        "hold":"hold", "tap":"tap", "none":"None",
        "hebrew":"\u05e2\u05d1\u05e8\u05d9\u05ea", "english":"English",
        "mode_infinite":"Infinite mode", "mode_target":"Beat-best mode",
        "sound_on":"Sound on", "sound_off":"Sound off",
        "sound":"Sound", "on":"On", "off":"Off",
        "win_mode":"Win mode", "infinite":"Infinite", "target":"Beat best",
        "show_tips":"Show tips",
        "reset_settings":"Reset settings",
        "reset_score":"Reset best",
        "reset_settings_q":"Reset all settings to default?",
        "reset_score_q":"Reset your personal best?",
        "yes":"Yes",
        "no":"No",
        "done_reset":"Reset done",
        "tips_list":[
            "Keep your highest tile in a corner and don't move it",
            "Try to keep one full, ordered row",
            "Build a descending chain along a row",
            "Mostly swipe in just two fixed directions",
            "Don't fill the board - leave room to maneuver",
        ],
        "tip_stuck":"A low tile is stuck - try to free it",
        "tip_full":"Board is filling up! Merge tiles urgently",
        "tip_corner":"Keep your highest tile in a corner",
        "tip_lost_corner":"Your highest tile left the corner - bring it back!",
        "tip_good_corner":"Nice! You got the highest back to a corner",
        "tip_good_clear":"Great! You freed up the board",
        "tip_good_merge":"Excellent! Big merge",
        "tip_good_space":"Nice! You cleared lots of space",
        "preferences":"Preferences", "prefs_hint":"Advanced settings", "prefs_title":"Refuge of Cheats & Crooks",
        "prefs_sub":"Where everyone who isn't good enough on their own gathers",
        "persist_cheats":"Keep cheats between sessions",
        "count_best":"Count cheats in best",
        "credit":"Made by Claude \u2022 BeniaBot",
        "about":"About",
        "opened_by":"Opened by",
        "up_to_date":"The app is up to date",
        "update_ready":"A new version is available",
        "check_again":"Check again",
        "checking":"Checking...",
        "visit_github":"Visit the GitHub page",
        "download_update":"Download new version",
        "version_lbl":"Version",
        "update_avail":"Update available!",
        "about":"About",
        "confess_title":"One moment...",
        "confess_body":"To save cheat settings, you must admit:",
        "confess_line":"\"I cheat because I'm not good enough\"",
        "confess_yes":"I admit it", "confess_no":"Never!",
        "confess_rejected":"Back to practice then. Settings not saved.",
        "praise_title":"Respect!",
        "praise_body":"You chose to drop the cheats and play like a champ!",
        "praise_body2":"That's impressive. Your change was saved automatically.",
        "praise_ok":"Thanks!",
        "praise_toast":"Go play 'for real'\nJust don't give up too fast!",
        "mode_names":["Mode 1 - Classic","Mode 2 - 2/4 Control",
                      "Mode 3 - Cleaner","Mode 4 - Full Kit"],
        "actions":{
            "force_2":"Next tile will be 2",
            "force_4":"Next tile will be 4",
            "spawn_corner":"New tile at the edge",
            "clean_stuck":"Clear a stuck tile",
            "undo":"Undo a move",
        },
        "action_detail":{
            "force_2":"Hold during a move - new tile spawns as 2, not 4 (keeps board tidy)",
            "force_4":"Hold during a move - new tile spawns as 4 (scores faster)",
            "spawn_corner":"Hold during a move - new tile appears at the edge, not the middle",
            "clean_stuck":"Tap - removes a low tile trapped between higher ones",
            "undo":"Tap - restores the board to before your last move",
        },
    },
}

# Global current-language shaper, set by Game each frame. Buttons use it too.
_CURRENT_LANG = "he"
def shape_text(text):
    if _CURRENT_LANG == "he" and _HAS_BIDI:
        try:
            return _bidi_display(text)
        except Exception:
            return text
    return text

ACTION_KEYS = ["force_2","force_4","spawn_corner","clean_stuck","undo"]
HOLD_ACTIONS = {"force_2","force_4","spawn_corner"}
TAP_ACTIONS  = {"clean_stuck","undo"}

# Keys we never allow binding to (reserved for gameplay/navigation).
RESERVED_KEYS = {pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
                 pygame.K_a, pygame.K_w, pygame.K_s, pygame.K_d,
                 pygame.K_ESCAPE}

def key_display_name(code):
    """Human-readable label for a pygame key code (or None)."""
    if code is None:
        return None
    try:
        name = pygame.key.name(code)
    except Exception:
        return "?"
    # tidy up common names
    pretty = {
        "left shift":"Shift(L)", "right shift":"Shift(R)",
        "left ctrl":"Ctrl(L)", "right ctrl":"Ctrl(R)",
        "left alt":"Alt(L)", "right alt":"Alt(R)",
        "left meta":"Meta(L)", "right meta":"Meta(R)",
        "space":"Space", "return":"Enter", "tab":"Tab",
    }
    return pretty.get(name, name.upper() if len(name)==1 else name.title())

def default_config():
    return {
        "config_version": 2,
        "grid_size":4, "language":"he", "active_profile":0, "highscore":0,
        "sound":True, "infinite":True, "show_tips":False, "persist_cheats":False,
        "count_cheats_in_best":False,
        "profiles":[
            {"map":{}},
            {"map":{"force_4":pygame.K_LSHIFT}},
            {"map":{"clean_stuck":pygame.K_LSHIFT,"undo":pygame.K_LCTRL}},
            {"map":{"force_4":pygame.K_LSHIFT,"clean_stuck":pygame.K_c,
                    "undo":pygame.K_z,"spawn_corner":pygame.K_LALT}},
        ],
    }

CONFIG_VERSION = 2

# Legacy name->code map, to migrate old configs that stored key names.
_LEGACY_KEYNAMES = {
    "Left Shift":pygame.K_LSHIFT, "Right Shift":pygame.K_RSHIFT,
    "Left Ctrl":pygame.K_LCTRL, "Right Ctrl":pygame.K_RCTRL,
    "Left Alt":pygame.K_LALT, "Space":pygame.K_SPACE, "Tab":pygame.K_TAB,
    "Q":pygame.K_q,"E":pygame.K_e,"F":pygame.K_f,"C":pygame.K_c,
    "V":pygame.K_v,"B":pygame.K_b,"Z":pygame.K_z,"X":pygame.K_x,
    "1":pygame.K_1,"2":pygame.K_2,"3":pygame.K_3,"None":None,
}
def _migrate_map(m):
    """Convert any legacy string key names in a profile map to int keycodes."""
    out = {}
    for action, val in m.items():
        if isinstance(val, str):
            code = _LEGACY_KEYNAMES.get(val)
            if code is not None:
                out[action] = code
        elif isinstance(val, int):
            out[action] = val
    return out

def load_config():
    cfg = default_config()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH,"r",encoding="utf-8") as f:
                saved = json.load(f)
            old_version = saved.get("config_version", 1)
            cfg.update(saved)
            cfg["config_version"] = CONFIG_VERSION
            if not cfg.get("profiles"):
                cfg["profiles"] = default_config()["profiles"]
            # migrate any legacy string key-names to int keycodes
            for p in cfg["profiles"]:
                if isinstance(p.get("map"), dict):
                    p["map"] = _migrate_map(p["map"])
            # If the config predates the built-in-modes fix, re-seed the four
            # built-in modes so "Mode 2" etc. come with their cheats again.
            # (User's grid/language/sound/highscore are preserved above.)
            if old_version < 2:
                cfg["profiles"] = default_config()["profiles"]
        except Exception:
            pass
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_PATH,"w",encoding="utf-8") as f:
            json.dump(cfg,f,indent=2,ensure_ascii=False)
    except Exception:
        pass

# ============================================================================
# Board
# ============================================================================
class Board:
    def __init__(self, size):
        self.size = size
        self.grid = [[0]*size for _ in range(size)]
        self.score = 0
    def clone(self):
        b = Board(self.size); b.grid = copy.deepcopy(self.grid); b.score = self.score
        return b
    def empty_cells(self):
        return [(r,c) for r in range(self.size)
                for c in range(self.size) if self.grid[r][c]==0]
    def spawn(self, force_value=None, prefer_edge=False):
        cells = self.empty_cells()
        if not cells: return None
        if prefer_edge:
            edge = [(r,c) for (r,c) in cells
                    if r in (0,self.size-1) or c in (0,self.size-1)]
            if edge: cells = edge
        r,c = random.choice(cells)
        val = force_value if force_value else (4 if random.random()<0.1 else 2)
        self.grid[r][c] = val
        return (r,c,val)

    def _line_moves(self, line):
        entries = [(v,i) for i,v in enumerate(line) if v!=0]
        new_line = [0]*len(line); moves = []; dest = 0; i = 0
        while i < len(entries):
            v, src = entries[i]
            if i+1 < len(entries) and entries[i+1][0]==v:
                src2 = entries[i+1][1]
                new_line[dest] = v*2
                moves.append((dest,[src,src2],True,v*2))
                i += 2
            else:
                new_line[dest] = v
                moves.append((dest,[src],False,v))
                i += 1
            dest += 1
        return new_line, moves

    def move(self, direction):
        n = self.size; changed = False; gain = 0; anims = []; merges = []
        if direction in ("left","right"):
            for r in range(n):
                line = self.grid[r][:]
                oriented = line[:] if direction=="left" else line[::-1]
                new_line, moves = self._line_moves(oriented)
                back = (lambda p: p) if direction=="left" else (lambda p: n-1-p)
                for dest,srcs,merged,val in moves:
                    for s in srcs:
                        anims.append({"from":(r,back(s)),"to":(r,back(dest)),
                                      "value":oriented[s],"merged":merged,"new_value":val})
                    if merged:
                        gain += val; merges.append((r,back(dest),val))
                final = new_line if direction=="left" else new_line[::-1]
                if final != line: changed = True
                self.grid[r] = final
        else:
            for c in range(n):
                line = [self.grid[r][c] for r in range(n)]
                oriented = line[:] if direction=="up" else line[::-1]
                new_line, moves = self._line_moves(oriented)
                back = (lambda p: p) if direction=="up" else (lambda p: n-1-p)
                for dest,srcs,merged,val in moves:
                    for s in srcs:
                        anims.append({"from":(back(s),c),"to":(back(dest),c),
                                      "value":oriented[s],"merged":merged,"new_value":val})
                    if merged:
                        gain += val; merges.append((back(dest),c,val))
                final = new_line if direction=="up" else new_line[::-1]
                if final != line: changed = True
                for r in range(n):
                    self.grid[r][c] = final[r]
        if changed: self.score += gain
        return changed, anims, merges

    def can_move(self):
        if self.empty_cells(): return True
        n = self.size
        for r in range(n):
            for c in range(n):
                v = self.grid[r][c]
                if (c+1<n and self.grid[r][c+1]==v) or (r+1<n and self.grid[r+1][c]==v):
                    return True
        return False
    def max_tile(self):
        return max(max(row) for row in self.grid)

    def _stuck_score(self, r, c):
        """How 'stuck' is the tile at (r,c)? Higher = more stuck; None if not.
        A tile counts as stuck only when it is genuinely trapped:
          - it is a LOW tile (<= a quarter of the board's max, so 2/4 amid big
            tiles) - high tiles are never 'stuck' in a useful sense,
          - it has NO orthogonal neighbor of equal value (can't merge now),
          - it has NO empty orthogonal neighbor (can't slide sideways),
          - it cannot slide to an empty cell along its own row OR column
            (nothing to move toward), AND
          - all its neighbors are strictly larger (it can't absorb them)."""
        n = self.size
        v = self.grid[r][c]
        if v == 0:
            return None
        board_max = self.max_tile() or v
        # only low tiles relative to the board are meaningfully "stuck"
        if v * 4 > board_max:
            return None
        neigh_vals = []
        occupied = 0; total = 0
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
            rr, cc = r+dr, c+dc
            if 0 <= rr < n and 0 <= cc < n:
                total += 1
                nv = self.grid[rr][cc]
                if nv != 0:
                    occupied += 1
                    neigh_vals.append(nv)
                    if nv == v:
                        return None          # can merge -> not stuck
        if occupied < total:
            return None                      # empty neighbor -> can move
        if not neigh_vals or not all(x > v for x in neigh_vals):
            return None
        # can it slide toward any empty cell in its row or column? if so, the
        # tile isn't really trapped - a move in that direction shifts it.
        for cc in range(n):
            if cc != c and self.grid[r][cc] == 0:
                return None                  # empty cell in same row
        for rr in range(n):
            if rr != r and self.grid[rr][c] == 0:
                return None                  # empty cell in same column
        # genuinely trapped. score by how low + how boxed + how central.
        lowness = board_max / v
        surround = min(neigh_vals) / v
        edge = (r == 0 or r == n-1) + (c == 0 or c == n-1)
        centrality = 1.0 + (0 if edge >= 2 else (0.5 if edge == 1 else 1.0))
        return lowness * surround * centrality

    def remove_stuck_low(self):
        n = self.size; best = None
        for r in range(n):
            for c in range(n):
                s = self._stuck_score(r, c)
                if s is not None and (best is None or s > best[0]):
                    best = (s, r, c)
        if best:
            self.grid[best[1]][best[2]] = 0
            return (best[1], best[2])
        return None
    def merge_one_pair(self):
        n = self.size
        for r in range(n):
            for c in range(n):
                v = self.grid[r][c]
                if v==0: continue
                for dr,dc in ((0,1),(1,0)):
                    rr,cc = r+dr,c+dc
                    if rr<n and cc<n and self.grid[rr][cc]==v:
                        self.grid[r][c]=v*2; self.grid[rr][cc]=0
                        self.score += v*2; return (r,c)
        return None
    def upgrade_lowest(self):
        n = self.size; low = None
        for r in range(n):
            for c in range(n):
                v = self.grid[r][c]
                if v!=0 and (low is None or v<low[0]): low = (v,r,c)
        if low:
            self.grid[low[1]][low[2]] = low[0]*2; return (low[1],low[2])
        return None

# ============================================================================
class Button:
    def __init__(self, rect, label, font, base=BTN_BG, text_col=BTN_TEXT):
        self.rect = pygame.Rect(rect); self.label = label; self.font = font
        self.base = base; self.text_col = text_col
    def draw(self, surf):
        # surf is a ScaledScreen proxy: use its scaled primitives
        surf.rect(self.base, self.rect, border_radius=6)
        t = self.font.render(shape_text(self.label), True, self.text_col)
        r = t.get_rect(center=(self.rect.centerx*surf.s, self.rect.centery*surf.s))
        surf.surf.blit(t, r)
    def hit(self, pos):
        return self.rect.collidepoint(pos)

def ease_out(t):
    return 1 - (1-t)**3

class ScaledScreen:
    """Proxy that scales every draw/blit coordinate by a factor, so all UI code
    can be written in logical coordinates while rendering at higher resolution
    for crisp, anti-aliased output. Wraps a larger pygame Surface."""
    def __init__(self, surface, scale):
        self.surf = surface
        self.s = scale
    def _rz(self, rect):
        # scale a rect-like (Rect or 4-tuple) by s
        if isinstance(rect, pygame.Rect):
            return pygame.Rect(rect.x*self.s, rect.y*self.s,
                               rect.w*self.s, rect.h*self.s)
        x, y, w, h = rect
        return (x*self.s, y*self.s, w*self.s, h*self.s)
    def _pz(self, pt):
        return (pt[0]*self.s, pt[1]*self.s)
    def fill(self, color, rect=None):
        if rect is None:
            self.surf.fill(color)
        else:
            self.surf.fill(color, self._rz(rect))
    def blit(self, src, dest, *a, **k):
        # If dest is a Rect produced by src.get_rect(center=(lx,ly)) with the
        # text rendered at SS scale, recover the logical center and place the
        # SS-sized text centered at (lx*s, ly*s). Otherwise treat dest as a
        # logical top-left point and scale it.
        if isinstance(dest, pygame.Rect):
            # logical center = dest.center (rect was built in logical center,
            # but src is SS-sized, so its own w/h are SS). Recover center:
            cx = dest.x + dest.w/2
            cy = dest.y + dest.h/2
            tw, th = src.get_width(), src.get_height()
            self.surf.blit(src, (round(cx*self.s - tw/2),
                                 round(cy*self.s - th/2)), *a, **k)
        else:
            self.surf.blit(src, (round(dest[0]*self.s), round(dest[1]*self.s)),
                           *a, **k)
    def blit_topleft_scaled(self, src, logical_xy):
        self.surf.blit(src, (round(logical_xy[0]*self.s),
                             round(logical_xy[1]*self.s)))
    def get_size(self):
        return (self.surf.get_width()//self.s, self.surf.get_height()//self.s)
    def get_width(self):
        return self.surf.get_width()//self.s
    def get_height(self):
        return self.surf.get_height()//self.s
    # scaled primitive helpers (called by draw_* wrappers)
    def rect(self, color, rect, width=0, border_radius=0):
        pygame.draw.rect(self.surf, color, self._rz(rect), width*self.s,
                         border_radius=border_radius*self.s)
    def circle(self, color, center, radius, width=0):
        pygame.draw.circle(self.surf, color, self._pz(center),
                           radius*self.s, width*self.s)
    def line(self, color, p1, p2, width=1):
        pygame.draw.line(self.surf, color, self._pz(p1), self._pz(p2),
                         max(1, width*self.s))
    def polygon(self, color, points, width=0):
        pts = [self._pz(p) for p in points]
        pygame.draw.polygon(self.surf, color, pts, width*self.s)
    def arc(self, color, rect, a0, a1, width=1):
        pygame.draw.arc(self.surf, color, self._rz(rect), a0, a1,
                        max(1, width*self.s))
    def card(self, color, rect, radius=12, shadow=True):
        """Rounded card with an optional soft drop shadow for depth."""
        r = self._rz(rect)
        if shadow:
            sh = pygame.Surface((r[2]+16*self.s, r[3]+16*self.s), pygame.SRCALPHA)
            pygame.draw.rect(sh, (60, 50, 40, 45),
                             (8*self.s, 10*self.s, r[2], r[3]),
                             border_radius=radius*self.s)
            try:
                # cheap blur: scale down and up
                small = pygame.transform.smoothscale(sh, (max(1,sh.get_width()//4),
                                                          max(1,sh.get_height()//4)))
                sh = pygame.transform.smoothscale(small, sh.get_size())
            except Exception:
                pass
            self.surf.blit(sh, (r[0]-8*self.s, r[1]-10*self.s))
        pygame.draw.rect(self.surf, color, r, border_radius=radius*self.s)

# ============================================================================
class Game:
    def __init__(self):
        make_dpi_aware()
        os.environ["SDL_VIDEO_CENTERED"] = "1"  # must be set before init
        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
        except Exception:
            pass
        pygame.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass
        self.cfg = load_config()
        self.SS = 2                        # supersampling factor
        self.W, self.H = 560, 780          # logical coordinate space (larger)
        # Set the window icon BEFORE creating the window so the taskbar picks
        # it up. Use a PNG (pygame loads PNG reliably; ICO support is patchy).
        try:
            for cand in ("icon_64.png", "icon_256.png", "icon_512.png", "icon.ico"):
                p = resource_path(cand)
                if os.path.exists(p):
                    surf = pygame.image.load(p)
                    pygame.display.set_icon(surf)
                    break
        except Exception:
            pass
        self.window = pygame.display.set_mode((self.W, self.H))
        # Load a high-res icon surface for the About screen.
        self.about_icon = None
        try:
            for cand in ("icon_256.png", "icon_512.png", "icon_64.png"):
                p = resource_path(cand)
                if os.path.exists(p):
                    self.about_icon = pygame.image.load(p).convert_alpha()
                    break
        except Exception:
            self.about_icon = None
        # Load the owner's circular profile avatar (shown next to "opened by").
        self.avatar = None
        try:
            ap = resource_path("avatar.png")
            if os.path.exists(ap):
                self.avatar = pygame.image.load(ap).convert_alpha()
        except Exception:
            self.avatar = None
        # We render into a surface SS times larger, using a scaling draw wrapper,
        # then smooth-downscale to the window for crisp anti-aliased output.
        self._render_surf = pygame.Surface((self.W*self.SS, self.H*self.SS)).convert_alpha()
        self.screen = ScaledScreen(self._render_surf, self.SS)
        pygame.display.set_caption("2049")
        self.clock = pygame.time.Clock()
        self._init_sound()
        self._load_fonts()
        self.state = "game"
        self.board = None
        self.history = []
        self.won = False; self.keep_going = False
        self.anim_tiles = []; self.anim_time = 0.0; self.anim_dur = 0.11
        self.animating = False; self.pending_spawn = None
        self.pop_tiles = {}; self.pending_merges = []
        self.flash = None
        self.capturing_action = None   # preferences: action awaiting a key press
        self.cheat_dirty = False       # unsaved cheat changes in this session
        self.confessing = False        # showing the confession dialog
        self.praising = False          # showing the praise dialog (quit cheating)
        self._profiles_snapshot = None # on-disk profiles when entering prefs
        self.toast = None              # (text, timer) transient message
        self.update_available = None   # newer version string if found online
        self.update_download_url = None  # direct .exe download link if available
        self._tip_now = None           # (text, timer) current on-screen tip
        self._tip_cooldown = 0.0       # seconds until next tip may show
        self._tip_index = 0
        self._prev_corner_ok = None    # was max tile in a corner last move
        self._prev_stuck = None        # was there a stuck tile last move
        self._prev_max = 0             # max tile last move (for merge praise)
        self._prev_empties = None      # empty count last move (for space praise)
        self._confirm = None           # (question, action) pending confirmation
        self.update_status = "checking"
        self._start_update_check()
        self.new_game()

    def _find_font_files(self):
        reg = None; bold = None
        for cand in ("DejaVuSans.ttf", "assets/DejaVuSans.ttf"):
            p = resource_path(cand)
            if os.path.exists(p):
                reg = p; break
        for cand in ("DejaVuSans-Bold.ttf", "assets/DejaVuSans-Bold.ttf"):
            p = resource_path(cand)
            if os.path.exists(p):
                bold = p; break
        return reg, bold

    def _mk(self, sz, bold=False):
        reg, boldf = getattr(self, "_font_files", (None, None))
        path = boldf if (bold and boldf) else reg
        if path:
            try:
                return pygame.font.Font(path, sz)
            except Exception:
                pass
        for name in ("arialhebrew","arial","segoeui","dejavusans"):
            try:
                return pygame.font.SysFont(name, sz, bold=bold)
            except Exception:
                continue
        return pygame.font.SysFont(None, sz, bold=bold)
    def _init_sound(self):
        self.sounds = {}
        self.sound_ok = False
        try:
            import numpy as np
            # Query the actual mixer format after init (set in __init__ pre_init)
            info = pygame.mixer.get_init()
            if not info:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                info = pygame.mixer.get_init()
            sr, fmt, channels = info
            def tone(freqs, ms, vol=0.35):
                n = int(sr*ms/1000.0)
                t = np.linspace(0, ms/1000.0, n, False)
                wave = np.zeros(n)
                for f in (freqs if isinstance(freqs,(list,tuple)) else [freqs]):
                    wave += np.sin(f*2*np.pi*t)
                wave /= max(1, len(freqs) if isinstance(freqs,(list,tuple)) else 1)
                # short attack + smooth decay to avoid clicks
                env = np.ones(n)
                a = max(1, int(n*0.05))
                env[:a] = np.linspace(0, 1, a)
                env *= np.linspace(1, 0, n)**1.2
                wave *= env * vol
                audio = np.int16(wave*32767)
                if channels == 2:
                    audio = np.column_stack([audio, audio])
                return pygame.sndarray.make_sound(np.ascontiguousarray(audio))
            self.sounds["merge"] = tone([523, 659], 90)     # pleasant chord
            self.sounds["spawn"] = tone(392, 55, vol=0.22)  # soft blip
            self.sounds["win"]   = tone([523, 659, 784], 300, vol=0.4)
            # Pitched merge tones: the higher the resulting tile, the higher the
            # note. Chaining merges (4->8->16...) makes a rising musical scale.
            self._merge_tones = {}
            # Map value -> semitone step. 4 is the lowest note; each doubling
            # goes up the C-major scale so consecutive merges sound melodic.
            scale = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88,
                     523.25, 587.33, 659.25, 698.46, 783.99, 880.00, 987.77,
                     1046.50, 1174.66, 1318.51]  # C4 up ~ 2.5 octaves
            v = 4; idx = 0
            while v <= 131072 and idx < len(scale):
                base = scale[idx]
                # add a soft fifth above for warmth
                self._merge_tones[v] = tone([base, base*1.5], 95, vol=0.34)
                v *= 2; idx += 1
            self.sound_ok = True
        except Exception as ex:
            self.sounds = {}
            self.sound_ok = False

    def play_sound(self, name):
        if not self.cfg.get("sound", True):
            return
        s = self.sounds.get(name)
        if s:
            try: s.play()
            except Exception: pass

    def play_merge(self, value):
        """Play the merge tone pitched to the resulting tile value."""
        if not self.cfg.get("sound", True):
            return
        tones = getattr(self, "_merge_tones", {})
        s = tones.get(value) or self.sounds.get("merge")
        if s:
            try: s.play()
            except Exception: pass

    def _load_fonts(self):
        self._font_files = self._find_font_files()
        s = self.SS
        self.f_title=self._mk(48*s,True); self.f_big=self._mk(30*s,True)
        self.f_med=self._mk(24*s,True); self.f_small=self._mk(19*s,True)
        self.f_tiny=self._mk(15*s); self._tile_fonts={}

    def shape(self, text):
        return shape_text(text)

    def _sync_lang(self):
        global _CURRENT_LANG
        _CURRENT_LANG = self.cfg["language"]
    def tile_font(self, cell, digits):
        key=(int(cell),digits)
        if key not in self._tile_fonts:
            base = cell*0.42
            if digits>=4: base = cell*0.30
            elif digits==3: base = cell*0.36
            # render at SS resolution; blit position is in logical space
            self._tile_fonts[key]=self._mk(int(base*self.SS),True)
        return self._tile_fonts[key]

    def L(self, key):
        return STRINGS[self.cfg["language"]][key]
    def is_rtl(self):
        return self.cfg["language"]=="he"
    def profile(self):
        return self.cfg["profiles"][self.cfg["active_profile"] % len(self.cfg["profiles"])]
    def mode_name(self):
        idx = self.cfg["active_profile"] % len(self.cfg["profiles"])
        names = self.L("mode_names")
        return names[idx] if idx < len(names) else f"Mode {idx+1}"
    def key_for_action(self, a):
        v = self.profile()["map"].get(a)
        return v if isinstance(v, int) else None
    def taps_for_key(self, kc):
        return [a for a,code in self.profile()["map"].items()
                if a in TAP_ACTIONS and code==kc and kc is not None]

    def new_game(self):
        self.board = Board(self.cfg["grid_size"])
        s1 = self.board.spawn(); s2 = self.board.spawn()
        self.history = []; self.won = False; self.keep_going = False
        self.anim_tiles = []; self.animating = False; self.pending_spawn = None
        self.pop_tiles = {}
        self.cheat_used_this_game = False   # fresh game, clean slate
        self._prev_corner_ok = None; self._prev_stuck = None
        self._prev_max = 0; self._prev_empties = None
        if s1: self.pop_tiles[(s1[0],s1[1])] = 1.0
        if s2: self.pop_tiles[(s2[0],s2[1])] = 1.0
    def update_highscore(self):
        # A game "counts" for the saved best if it was cheat-free, OR the player
        # explicitly enabled "count cheats in best". Otherwise the best still
        # rises on screen (see draw) but is never written to disk.
        cheating = getattr(self, "cheat_used_this_game", False) or self._active_cheat_on()
        if cheating and not self.cfg.get("count_cheats_in_best", False):
            return
        if self.board.score > self.cfg["highscore"]:
            self.cfg["highscore"] = self.board.score; save_config(self.cfg)

    def held_spawn_params(self):
        pressed = pygame.key.get_pressed()
        fv, pe = None, False
        k2 = self.key_for_action("force_2")
        if k2 and pressed[k2]: fv = 2
        k4 = self.key_for_action("force_4")
        if k4 and pressed[k4]: fv = 4
        ke = self.key_for_action("spawn_corner")
        if ke and pressed[ke]: pe = True
        if fv is not None or pe:
            self.cheat_used_this_game = True   # taint the score
        return fv, pe

    def handle_move(self, direction):
        if self.state!="game" or self.animating: return
        if self.won and not self.keep_going: return
        prev = self.board.clone()
        changed, anims, merges = self.board.move(direction)
        if not changed: return
        self.history.append(prev)
        if len(self.history)>40: self.history.pop(0)
        self.anim_tiles = anims; self.anim_time = 0.0; self.animating = True
        self.pending_merges = merges
        fv, pe = self.held_spawn_params()
        self.pending_spawn = (fv, pe)

    def finish_move(self):
        self.animating = False; self.anim_tiles = []
        merges = self.pending_merges
        merged_any = bool(merges)
        highest_merge = 0
        for entry in merges:
            r, c = entry[0], entry[1]
            self.pop_tiles[(r, c)] = 1.0
            if len(entry) > 2:
                highest_merge = max(highest_merge, entry[2])
        self.pending_merges = []
        if self.pending_spawn is not None:
            fv, pe = self.pending_spawn
            s = self.board.spawn(force_value=fv, prefer_edge=pe)
            if s: self.pop_tiles[(s[0],s[1])] = 1.0
            self.pending_spawn = None
        self.update_highscore()
        if merged_any:
            # pitch rises with the value created -> chained merges = rising scale
            self.play_merge(highest_merge)
        else:
            self.play_sound("spawn")
        if not self.won and self.board.max_tile()>=2048:
            self.won = True
            self.play_sound("win")
            if self.cfg.get("infinite", True):
                self.keep_going = True  # auto-continue in infinite mode
        # fire responsive tips based on what just changed on the board
        self._check_tip_events()

    def _pick_tip(self):
        """Pick the single most relevant tip for the CURRENT board, in priority
        order. Only returns situational tips when they genuinely apply; falls
        back to a general tip chosen to match the board, not a blind rotation."""
        L = self.L
        b = self.board
        n = b.size
        empties = len(b.empty_cells())
        total = n * n
        mx = b.max_tile()
        corners = [b.grid[0][0], b.grid[0][n-1], b.grid[n-1][0], b.grid[n-1][n-1]]

        # Priority 1: board almost full AND no easy merge available -> urgent.
        can_merge = self._any_merge_available()
        if empties <= 2 and not can_merge:
            return L("tip_full")

        # Priority 2: a genuinely stuck low tile exists (uses real detection).
        if any(b._stuck_score(r, c) is not None
               for r in range(n) for c in range(n)):
            return L("tip_stuck")

        # Priority 3: a strong tile has drifted out of the corners.
        if mx >= 64 and mx not in corners:
            return L("tip_corner")

        # Otherwise: a general tip that fits the board's phase.
        tips = L("tips_list")
        if empties >= total * 0.6:
            idx = 3   # early game, lots of space -> "swipe two directions"
        elif mx not in corners:
            idx = 0   # keep highest in a corner
        elif empties <= total * 0.35:
            idx = 1   # getting crowded -> keep one ordered row
        else:
            idx = 2   # build a descending chain
        return tips[idx % len(tips)]

    def _any_merge_available(self):
        """True if some adjacent equal pair exists (a merge is possible)."""
        b = self.board; n = b.size
        for r in range(n):
            for c in range(n):
                v = b.grid[r][c]
                if v == 0:
                    continue
                if c+1 < n and b.grid[r][c+1] == v:
                    return True
                if r+1 < n and b.grid[r+1][c] == v:
                    return True
        return False

    def _update_tips(self, dt):
        """Show tips that fit the board. Urgent situational tips (stuck tile,
        board nearly full) appear promptly when they arise; general strategy
        tips appear only occasionally so they don't nag."""
        if not self.cfg.get("show_tips", False):
            self._tip_now = None
            return
        urgent = self._urgent_tip()   # None unless a real situation applies
        if self._tip_now:
            # if a NEW urgent situation appears, swap to it immediately
            if urgent and self._tip_now[0] != urgent:
                self._tip_now = [urgent, 5.0]
                return
            self._tip_now[1] -= dt
            if self._tip_now[1] <= 0:
                self._tip_now = None
                # urgent tips can recur soon; general tips wait longer
                self._tip_cooldown = 8.0
        else:
            if urgent:
                self._tip_now = [urgent, 5.0]; return
            self._tip_cooldown -= dt
            if self._tip_cooldown <= 0:
                self._tip_now = [self._pick_tip(), 4.5]
                self._tip_cooldown = 8.0

    def _urgent_tip(self):
        """Return an urgent situational tip if one genuinely applies, else None."""
        L = self.L; b = self.board; n = b.size
        empties = len(b.empty_cells())
        if empties <= 2 and not self._any_merge_available():
            return L("tip_full")
        if any(b._stuck_score(r, c) is not None
               for r in range(n) for c in range(n)):
            return L("tip_stuck")
        if not self._max_in_corner() and b.max_tile() >= 64:
            return L("tip_lost_corner")
        return None

    def _max_in_corner(self):
        b = self.board; n = b.size
        mx = b.max_tile()
        corners = [b.grid[0][0], b.grid[0][n-1], b.grid[n-1][0], b.grid[n-1][n-1]]
        return mx in corners

    def _has_stuck(self):
        b = self.board; n = b.size
        return any(b._stuck_score(r, c) is not None
                   for r in range(n) for c in range(n))

    def _show_tip(self, text, secs=4.0):
        if self.cfg.get("show_tips", False):
            self._tip_now = [text, secs]

    def _check_tip_events(self):
        """Called right after a move settles. Fires immediate tips on state
        TRANSITIONS - both warnings (corner lost, tile stuck) and praise
        (corner regained, board freed, big merge). This is what makes tips
        feel responsive and fair instead of delayed/random."""
        if not self.cfg.get("show_tips", False):
            return
        L = self.L; b = self.board
        corner_ok = self._max_in_corner()
        stuck = self._has_stuck()
        mx = b.max_tile()
        empties = len(b.empty_cells())

        # praise: got the highest back into a corner
        if self._prev_corner_ok is False and corner_ok and mx >= 64:
            self._show_tip(L("tip_good_corner")); self._save_tip_state(corner_ok, stuck, mx, empties); return
        # warning: highest just left the corner
        if self._prev_corner_ok is True and not corner_ok and mx >= 64:
            self._show_tip(L("tip_lost_corner")); self._save_tip_state(corner_ok, stuck, mx, empties); return
        # praise: cleared a previously stuck tile
        if self._prev_stuck is True and not stuck:
            self._show_tip(L("tip_good_clear")); self._save_tip_state(corner_ok, stuck, mx, empties); return
        # warning: a tile just became stuck
        if self._prev_stuck is False and stuck:
            self._show_tip(L("tip_stuck")); self._save_tip_state(corner_ok, stuck, mx, empties); return
        # praise: reached a new higher max tile (big merge)
        if self._prev_max and mx > self._prev_max and mx >= 128:
            self._show_tip(L("tip_good_merge")); self._save_tip_state(corner_ok, stuck, mx, empties); return
        # praise: freed a lot of space at once (several merges)
        if self._prev_empties is not None and empties - self._prev_empties >= 3:
            self._show_tip(L("tip_good_space")); self._save_tip_state(corner_ok, stuck, mx, empties); return

        self._save_tip_state(corner_ok, stuck, mx, empties)

    def _save_tip_state(self, corner_ok, stuck, mx, empties):
        self._prev_corner_ok = corner_ok
        self._prev_stuck = stuck
        self._prev_max = mx
        self._prev_empties = empties

    def do_tap_action(self, action):
        if self.animating: return
        prev = self.board.clone(); pos = None
        if action=="undo":
            if self.history:
                self.board = self.history.pop(); self.pop_tiles = {}; self.flash = 12
                self.cheat_used_this_game = True   # undo used -> taint
            return
        elif action=="clean_stuck": pos = self.board.remove_stuck_low()
        if pos:
            self.cheat_used_this_game = True       # only taint if it did something
            self.history.append(prev); self.pop_tiles[pos] = 1.0
            self.update_highscore(); self.flash = 12

    def board_geometry(self):
        n = self.board.size
        margin = 24
        board_px = self.W - 2*margin      # full-width board with equal margins
        by = 168                          # below the two header rows
        gap = 12
        cell = int((board_px - gap*(n+1))/n)
        # recompute board_px so cells+gaps fit exactly (avoids right-edge sliver)
        board_px = cell*n + gap*(n+1)
        bx = (self.W - board_px)//2
        return bx, by, board_px, gap, cell
    def cell_rect(self, r, c):
        bx, by, _, gap, cell = self.board_geometry()
        return int(bx+gap+c*(cell+gap)), int(by+gap+r*(cell+gap)), cell

    def draw_tile(self, value, x, y, cell, scale=1.0):
        base_cell = cell
        if scale != 1.0:
            new = cell*scale; off = (cell-new)/2
            x, y, cell = x+off, y+off, new
        # integer coords = crisp edges (no sub-pixel shimmer)
        ix, iy, ic = round(x), round(y), round(cell)
        self.screen.rect(tile_color(value),
                         (ix, iy, ic, ic), border_radius=6)
        if value:
            f = self.tile_font(base_cell, len(str(value)))
            t = f.render(str(value), True, tile_text_color(value))
            self.screen.blit(t, t.get_rect(center=(ix+ic//2, iy+ic//2)))

    def draw_game(self):
        self._sync_lang(); self.screen.fill(BG); L = self.L
        M = 24  # margin

        # --- Title "! 2048 !" (left) ---
        title = self.f_title.render("2049", True, TEXT_DARK)
        self.screen.blit(title, (M, 28))

        # --- Score + Best boxes (right side, right-aligned to margin) ---
        box_w, box_h, box_gap = 118, 56, 10
        best_x = self.W - M - box_w
        score_x = best_x - box_gap - box_w
        self._score_box(L("score"), self.board.score, score_x, 26)
        # The BEST box shows the higher of the saved best and the current score,
        # so it rises during play like normal - but the saved value only
        # actually updates for clean (cheat-free) games (see update_highscore).
        shown_best = max(self.cfg["highscore"], self.board.score)
        self._score_box(L("best"), shown_best, best_x, 26)

        # --- Second row: settings (left) + 4x4 selector & refresh (right) ---
        sel_y = 100
        # refresh (new game) icon at far right
        self.refresh_box = pygame.Rect(self.W-M-42, sel_y, 42, 42)
        self.screen.rect(BOARD_BG, self.refresh_box, border_radius=8)
        self._refresh_icon(self.refresh_box.center, 12)
        # size selector box + arrows to the left of refresh
        self.sel_box = pygame.Rect(self.refresh_box.x-10-84, sel_y, 84, 42)
        self.screen.rect(BOARD_BG, self.sel_box, border_radius=8)
        st = self.f_small.render(f"{self.board.size}\u00d7{self.board.size}",
                                 True, TEXT_LIGHT)
        self.screen.blit(st, st.get_rect(center=(self.sel_box.centerx+9,
                                                 self.sel_box.centery)))
        self.sel_up = pygame.Rect(self.sel_box.x+6, sel_y+5, 18, 15)
        self.sel_down = pygame.Rect(self.sel_box.x+6, sel_y+22, 18, 15)
        self._tri(self.sel_up, "up")
        self._tri(self.sel_down, "down")

        # settings button (left)
        self.game_buttons = {}
        self.btn_settings = Button((M, sel_y, 104, 42), L("settings"), self.f_small)
        self.btn_settings.draw(self.screen)
        self.game_buttons["settings"] = self.btn_settings

        # --- Board ---
        bx0, by0, board_px, gap, cell = self.board_geometry()
        self.screen.rect(BOARD_BG,
                         (bx0, by0, board_px, board_px), border_radius=10)
        n = self.board.size
        for r in range(n):
            for c in range(n):
                x, y2, _ = self.cell_rect(r, c)
                self.screen.rect(EMPTY_CELL,
                                 (x, y2, cell, cell), border_radius=6)
        if self.animating:
            self._draw_animating(cell)
        else:
            self._draw_static(cell)
        self._update_pops()

        if self.won and not self.keep_going and not self.cfg["infinite"]:
            self._overlay(L("you_win"), L("keep_going"))
        elif not self.board.can_move() and not self.animating:
            self._overlay(L("game_over"), L("press_new"))

        # --- Bottom row: functional icons (left) + tip (right) ---
        self._draw_bottom_bar()

        # --- situational tip banner (below the board) when enabled ---
        if self._tip_now:
            bx0, by0, board_px, gap, cell = self.board_geometry()
            txt = self._tip_now[0]
            tw = self.f_tiny.size(txt)[0]/self.SS
            bw = min(self.W-48, tw+44)
            bx = self.W/2 - bw/2
            by = by0 + board_px + 8
            self.screen.card((250, 232, 205), pygame.Rect(bx, by, bw, 30),
                             radius=10, shadow=True)
            dotx = (bx+bw-16) if self.is_rtl() else (bx+16)
            self.screen.circle(ACCENT, (dotx, by+15), 5)
            tt = self.f_tiny.render(self.shape(txt), True, TEXT_DARK)
            self.screen.blit(tt, (self.W/2-tt.get_width()/2/self.SS, by+7))

        if self.flash:
            self.flash -= 1
            self.screen.circle((143,122,102), (self.W-6,6), 3)
            if self.flash<=0: self.flash = None

    def _tri(self, rect, direction):
        self.screen.rect(EMPTY_CELL, rect, border_radius=3)
        cx, cy = rect.center
        s = 4
        if direction == "up":
            pts = [(cx, cy-s), (cx-s, cy+s), (cx+s, cy+s)]
        else:
            pts = [(cx, cy+s), (cx-s, cy-s), (cx+s, cy-s)]
        self.screen.polygon(TEXT_DARK, pts)

    def _refresh_icon(self, center, r):
        cx, cy = center
        rect = pygame.Rect(cx-r, cy-r, 2*r, 2*r)
        self.screen.arc(TEXT_LIGHT, rect, 0.6, 5.6, 3)
        # arrow head
        ax, ay = cx + r*math.cos(0.6), cy - r*math.sin(0.6)
        self.screen.polygon(TEXT_LIGHT,
                            [(ax+4, ay-2), (ax-3, ay-5), (ax+2, ay+4)])

    def _draw_bottom_bar(self):
        L = self.L
        y = self.H - 34
        # icons at left: sound, infinite/target
        self.icon_sound = pygame.Rect(24, y, 30, 26)
        self.icon_mode = pygame.Rect(62, y, 30, 26)
        self._speaker_icon(self.icon_sound, self.cfg["sound"])
        self._infinity_icon(self.icon_mode, self.cfg["infinite"])
        # update-available badge (only when a newer version is found online)
        self.update_badge = None
        if self.update_available:
            ut = self.f_tiny.render(self.shape(L("update_avail")), True, TEXT_LIGHT)
            uw = ut.get_width()/self.SS
            self.update_badge = pygame.Rect(100, y, uw+16, 26)
            self.screen.rect(ACCENT, self.update_badge, border_radius=6)
            self.screen.blit(ut, (108, y+5))
        # tip text
        tip_txt = L("tips")
        tip = self.f_tiny.render(self.shape(tip_txt), True, BOARD_BG)
        self.screen.blit(tip, (self.W-24-tip.get_width()/self.SS, y+4))

    def _speaker_icon(self, rect, on):
        self.screen.rect(EMPTY_CELL, rect, border_radius=5)
        cx, cy = rect.center
        col = TEXT_DARK if on else BOARD_BG
        # speaker body
        self.screen.polygon(col,
            [(cx-6, cy-3),(cx-2, cy-3),(cx+2, cy-7),(cx+2, cy+7),(cx-2, cy+3),(cx-6, cy+3)])
        if on:
            self.screen.arc(col, pygame.Rect(cx+1, cy-6, 8, 12), -1.0, 1.0, 2)
        else:
            self.screen.line((200,90,80), (cx+4, cy-5), (cx+10, cy+5), 2)

    def _infinity_icon(self, rect, on):
        self.screen.rect(EMPTY_CELL, rect, border_radius=5)
        cx, cy = rect.center
        col = TEXT_DARK if on else BOARD_BG
        if on:
            # infinity symbol: two small circles
            self.screen.circle(col, (cx-4, cy), 4, 2)
            self.screen.circle(col, (cx+4, cy), 4, 2)
        else:
            # target/flag: a small trophy-ish mark
            self.screen.polygon(col,
                [(cx-5, cy-6),(cx+5, cy-6),(cx+3, cy+2),(cx-3, cy+2)], 2)
            self.screen.line(col, (cx, cy+2), (cx, cy+6), 2)

    def _draw_static(self, cell):
        n = self.board.size
        for r in range(n):
            for c in range(n):
                v = self.board.grid[r][c]
                if v==0: continue
                x, y, _ = self.cell_rect(r, c)
                scale = 1.0
                if (r,c) in self.pop_tiles:
                    p = self.pop_tiles[(r,c)]  # 1 -> 0
                    scale = 0.6 + 0.4*(1-p) + 0.12*math.sin((1-p)*math.pi)
                    scale = min(max(scale,0.5),1.12)
                self.draw_tile(v, x, y, cell, scale)

    def _draw_animating(self, cell):
        t = ease_out(min(self.anim_time/self.anim_dur, 1.0))
        for a in self.anim_tiles:
            fr, fc = a["from"]; tr, tc = a["to"]
            fx, fy, _ = self.cell_rect(fr, fc)
            tx, ty, _ = self.cell_rect(tr, tc)
            x = round(fx + (tx-fx)*t); y = round(fy + (ty-fy)*t)
            self.draw_tile(a["value"], x, y, cell, 1.0)

    def _update_pops(self):
        dt = self.clock.get_time()/1000.0; done = []
        for pos in list(self.pop_tiles.keys()):
            self.pop_tiles[pos] -= dt/0.14
            if self.pop_tiles[pos] <= 0: done.append(pos)
        for p in done: del self.pop_tiles[p]

    def _score_box(self, label, value, x, y):
        w, h = 118, 56
        self.screen.rect(SCORE_BG, (x,y,w,h), border_radius=8)
        lab = self.f_tiny.render(self.shape(label), True, (238,228,218))
        self.screen.blit(lab, (x+w/2-lab.get_width()/2/self.SS, y+8))
        val = self.f_med.render(str(value), True, TEXT_LIGHT)
        self.screen.blit(val, (x+w/2-val.get_width()/2/self.SS, y+26))

    def _overlay(self, big, small):
        bx0, by0, board_px, _, _ = self.board_geometry()
        s = pygame.Surface((board_px*self.SS, board_px*self.SS), pygame.SRCALPHA)
        s.fill((250,248,239,205))
        self._render_surf.blit(s, (bx0*self.SS, by0*self.SS))
        t1 = self.f_big.render(self.shape(big), True, TEXT_DARK)
        t2 = self.f_small.render(self.shape(small), True, TEXT_DARK)
        cx = bx0+board_px/2; cy = by0+board_px/2
        self.screen.blit(t1, t1.get_rect(center=(cx, cy-20)))
        self.screen.blit(t2, t2.get_rect(center=(cx, cy+24)))

    def draw_menu(self):
        self._sync_lang(); self.screen.fill(BG); L = self.L
        title = self.f_title.render("2048+", True, TEXT_DARK)
        self.screen.blit(title, title.get_rect(center=(self.W/2,120)))
        sub = self.f_tiny.render(self.shape(L("subtitle")), True, BOARD_BG)
        self.screen.blit(sub, sub.get_rect(center=(self.W/2,165)))
        self.m_play = Button((self.W/2-110,220,220,52), L("play"), self.f_med)
        self.m_settings = Button((self.W/2-110,286,220,52), L("settings"), self.f_med)
        self.m_quit = Button((self.W/2-110,352,220,52), L("quit"), self.f_med)
        for b in (self.m_play,self.m_settings,self.m_quit): b.draw(self.screen)
        info = self.f_small.render(
            self.shape(f"{self.mode_name()}   |   {self.cfg['grid_size']}x{self.cfg['grid_size']}"),
            True, BOARD_BG)
        self.screen.blit(info, info.get_rect(center=(self.W/2,445)))
        best = self.f_small.render(self.shape(f"{L('best')}: {self.cfg['highscore']}"), True, BOARD_BG)
        self.screen.blit(best, best.get_rect(center=(self.W/2,475)))

    def _settings_row(self, y, label, options, selected_val, rtl):
        """Draw one settings card: label on one side, option buttons on other.
        Buttons size to their text (with a minimum) so nothing overflows.
        options = list of (value, text). Returns list of (value, Button)."""
        M = 24
        card_h = 64
        card = pygame.Rect(M, y, self.W-2*M, card_h)
        self.screen.card(CARD_BG, card, radius=14, shadow=True)
        pad = 20
        bh = 42; bgap = 10
        by = y + (card_h-bh)//2

        # measure each button width from its text (logical units)
        widths = []
        for val, text in options:
            tw = self.f_small.size(text)[0]/self.SS
            widths.append(max(70, int(tw + 28)))   # min 70px, +padding
        total = sum(widths) + bgap*(len(options)-1)

        # label goes on the far side; buttons on the near side
        lab = self.f_small.render(self.shape(label), True, TEXT_DARK)
        lw = lab.get_width()/self.SS
        result = []
        if rtl:
            # label on the right, buttons filling from left
            self.screen.blit(lab, (card.right-pad-lw, y+card_h/2-9))
            bx = card.x + pad
            for (val, text), bw in zip(options, widths):
                sel = (selected_val == val)
                b = Button((bx, by, bw, bh), text, self.f_small,
                           base=ACCENT if sel else EMPTY_CELL,
                           text_col=TEXT_LIGHT if sel else TEXT_DARK)
                b.draw(self.screen); result.append((val, b)); bx += bw+bgap
        else:
            # label on the left, buttons filling from right
            self.screen.blit(lab, (card.x+pad, y+card_h/2-9))
            bx = card.right - pad - total
            for (val, text), bw in zip(options, widths):
                sel = (selected_val == val)
                b = Button((bx, by, bw, bh), text, self.f_small,
                           base=ACCENT if sel else EMPTY_CELL,
                           text_col=TEXT_LIGHT if sel else TEXT_DARK)
                b.draw(self.screen); result.append((val, b)); bx += bw+bgap
        return result
        return result

    def draw_settings(self):
        self._sync_lang(); self.screen.fill(BG); L = self.L; rtl = self.is_rtl()
        M = 24
        # --- Header bar ---
        self.screen.rect(BOARD_BG, (0, 0, self.W, 64))
        title = self.f_med.render(self.shape(L("settings")), True, TEXT_LIGHT)
        if rtl:
            self.screen.blit(title, (self.W-M-title.get_width()/self.SS, 20))
            self.s_back = Button((M,16,90,34), L("back"), self.f_small,
                                 base=BTN_BG, text_col=TEXT_LIGHT)
        else:
            self.screen.blit(title, (M,20))
            self.s_back = Button((self.W-M-90,16,90,34), L("back"), self.f_small,
                                 base=BTN_BG, text_col=TEXT_LIGHT)
        self.s_back.draw(self.screen)

        y = 76
        self.s_grid = self._settings_row(
            y, L("grid_size"),
            [(4,"4\u00d74"),(5,"5\u00d75"),(6,"6\u00d76")],
            self.cfg["grid_size"], rtl); y += 70
        self.s_lang = self._settings_row(
            y, L("language"),
            [("he",L("hebrew")),("en",L("english"))],
            self.cfg["language"], rtl); y += 70
        self.s_sound = self._settings_row(
            y, L("sound"),
            [(True,L("on")),(False,L("off"))],
            self.cfg["sound"], rtl); y += 70
        self.s_winmode = self._settings_row(
            y, L("win_mode"),
            [(True,L("infinite")),(False,L("target"))],
            self.cfg["infinite"], rtl); y += 70
        self.s_tips = self._settings_row(
            y, L("show_tips"),
            [(True,L("on")),(False,L("off"))],
            self.cfg.get("show_tips", False), rtl); y += 78

        # --- Reset buttons row (settings + high score) ---
        rbh = 40; rgap = 12
        rbw = (self.W - 48 - rgap) / 2
        self.s_reset_settings = Button((24, y, rbw, rbh), L("reset_settings"),
                                       self.f_tiny, base=EMPTY_CELL, text_col=TEXT_DARK)
        self.s_reset_score = Button((24+rbw+rgap, y, rbw, rbh), L("reset_score"),
                                    self.f_tiny, base=EMPTY_CELL, text_col=TEXT_DARK)
        self.s_reset_settings.draw(self.screen); self.s_reset_score.draw(self.screen)
        y += 56

        # --- "Preferences" button (discreet - actually the cheat config) ---
        pw = self.f_small.size(L("preferences"))[0]/self.SS + 48
        self.s_prefs = Button((self.W/2-pw/2, y, pw, 46), L("preferences"),
                              self.f_small, base=BTN_BG, text_col=TEXT_LIGHT)
        self.s_prefs.draw(self.screen)
        sub = self.f_tiny.render(self.shape(L("prefs_hint")), True, BOARD_BG)
        self.screen.blit(sub, (self.W/2-sub.get_width()/2/self.SS, y+50))
        y += 90

        # --- About card (status + GitHub + author with avatar) ---
        card_y = y
        card_h = 176
        acard = pygame.Rect(24, card_y, self.W-48, card_h)
        self.screen.card((245, 239, 229), acard, radius=18, shadow=True)
        iy = card_y + 16

        # status pill
        st = getattr(self, "update_status", "checking")
        pill = pygame.Rect(40, iy, self.W-80, 40)
        pill_col = (216, 236, 222) if st == "latest" else (
                   (247, 224, 208) if st == "update" else (236, 230, 220))
        self.screen.rect(pill_col, pill, border_radius=10)
        if st == "latest":
            msg, badge, bcol = L("up_to_date"), "\u2713", (60, 170, 110)
        elif st == "update":
            msg, badge, bcol = L("update_ready"), "\u2191", ACCENT
        else:
            msg, badge, bcol = L("checking"), None, None
        mt = self.f_tiny.render(self.shape(msg), True, TEXT_DARK)
        ca = self.f_tiny.render(self.shape(L("check_again")), True, ACCENT)
        if rtl:
            if badge:
                bx0 = pill.right-22
                self.screen.circle(bcol, (bx0, pill.centery), 10)
                bt = self.f_tiny.render(badge, True, TEXT_LIGHT)
                self.screen.blit(bt, bt.get_rect(center=(bx0, pill.centery)))
            self.screen.blit(mt, (pill.right-40-mt.get_width()/self.SS, pill.centery-8))
            self.a_recheck = pygame.Rect(pill.x+12, pill.centery-11,
                                         ca.get_width()/self.SS+8, 22)
            self.screen.blit(ca, (pill.x+14, pill.centery-8))
        else:
            if badge:
                bx0 = pill.x+22
                self.screen.circle(bcol, (bx0, pill.centery), 10)
                bt = self.f_tiny.render(badge, True, TEXT_LIGHT)
                self.screen.blit(bt, bt.get_rect(center=(bx0, pill.centery)))
            self.screen.blit(mt, (pill.x+40, pill.centery-8))
            self.a_recheck = pygame.Rect(pill.right-14-ca.get_width()/self.SS,
                                         pill.centery-11, ca.get_width()/self.SS+8, 22)
            self.screen.blit(ca, (pill.right-14-ca.get_width()/self.SS, pill.centery-8))
        iy += 52

        # GitHub button (full-width inside card). When an update is available,
        # it becomes a "Download new version" button that opens the releases page.
        gbtn = pygame.Rect(40, iy, self.W-80, 42)
        if st == "update":
            self.s_github = Button(gbtn, L("download_update"), self.f_small,
                                   base=ACCENT, text_col=TEXT_LIGHT)
            self._github_target = "release"
        else:
            self.s_github = Button(gbtn, L("visit_github"), self.f_small,
                                   base=BTN_BG, text_col=TEXT_LIGHT)
            self._github_target = "repo"
        self.s_github.draw(self.screen); iy += 54

        # author row: avatar + "opened by BeniaBot"
        by_txt = self.f_tiny.render(self.shape(L("opened_by")), True, BOARD_BG)
        link_txt = self.f_tiny.render("BeniaBot", True, ACCENT)
        av = 26  # avatar diameter (logical)
        gap = 8
        by_w = by_txt.get_width()/self.SS
        link_w = link_txt.get_width()/self.SS
        block_w = av + gap + by_w + 6 + link_w
        sx = self.W/2 - block_w/2
        ry = iy
        # draw avatar circle
        if self.avatar:
            ava = pygame.transform.smoothscale(self.avatar, (av*self.SS, av*self.SS))
            self.screen.surf.blit(ava, (int(sx*self.SS), int((ry-4)*self.SS)))
        else:
            self.screen.circle(BOARD_BG, (sx+av/2, ry+av/2-4), av/2)
        tx = sx + av + gap
        if rtl:
            # link then "opened by" reading right-to-left; keep avatar leftmost
            self.screen.blit(link_txt, (tx, ry))
            self.s_profile = pygame.Rect(tx, ry, link_w, 20)
            self.screen.blit(by_txt, (tx + link_w + 6, ry))
        else:
            self.screen.blit(by_txt, (tx, ry))
            lx0 = tx + by_w + 6
            self.screen.blit(link_txt, (lx0, ry))
            self.s_profile = pygame.Rect(lx0, ry, link_w, 20)

        # --- version at the very bottom ---
        ver = self.f_tiny.render(f"v{APP_VERSION}", True, BOARD_BG)
        self.screen.blit(ver, (self.W/2-ver.get_width()/2/self.SS, self.H-26))

        # transient toast (supports multi-line via \n)
        if self.toast:
            txt, _ = self.toast
            lines = txt.split("\n")
            lws = [self.f_small.size(ln)[0]/self.SS for ln in lines]
            tw = max(lws)
            th = 30*len(lines) + 12
            bx = self.W/2 - (tw+40)/2
            self.screen.rect(BTN_BG, (bx, 72, tw+40, th), border_radius=10)
            for i, ln in enumerate(lines):
                tt = self.f_small.render(self.shape(ln), True, TEXT_LIGHT)
                self.screen.blit(tt, (self.W/2-tt.get_width()/2/self.SS, 80+i*28))

        # confirmation dialog overlay (reset settings / reset score)
        if self._confirm:
            self._draw_confirm()

    def _clip_text(self, text, font, max_w_logical, color):
        """Render text truncated with an ellipsis so it fits max_w_logical
        (logical px). Returns a Surface."""
        if font.size(text)[0]/self.SS <= max_w_logical:
            return font.render(self.shape(text), True, color)
        ell = "\u2026"
        s = text
        while s and font.size(s + ell)[0]/self.SS > max_w_logical:
            s = s[:-1]
        return font.render(self.shape((s + ell) if s else ell), True, color)

    def _pref_checkbox(self, y, label, on, rtl):
        """Draw a compact checkbox row; returns the clickable box Rect."""
        row = pygame.Rect(24, y, self.W-48, 38)
        self.screen.card((243, 236, 225), row, radius=10, shadow=False)
        cb = 22
        pl = self.f_tiny.render(self.shape(label), True, TEXT_DARK)
        if rtl:
            box = pygame.Rect(row.x+12, y+8, cb, cb)
            self.screen.blit(pl, (row.right-14-pl.get_width()/self.SS, y+12))
        else:
            box = pygame.Rect(row.right-12-cb, y+8, cb, cb)
            self.screen.blit(pl, (row.x+14, y+12))
        self.screen.rect(ACCENT if on else EMPTY_CELL, box, border_radius=5)
        if on:
            ck = self.f_tiny.render("\u2713", True, TEXT_LIGHT)
            self.screen.blit(ck, ck.get_rect(center=box.center))
        return box

    # ---- Cheaters' Refuge: the hidden assist configuration ----
    def draw_preferences(self):
        self._sync_lang(); self.screen.fill(BG); L = self.L; rtl = self.is_rtl()
        M = 24
        # header bar with cheeky title
        self.screen.rect(BOARD_BG, (0, 0, self.W, 64))
        title = self.f_med.render(self.shape(L("prefs_title")), True, TEXT_LIGHT)
        if rtl:
            self.screen.blit(title, (self.W-M-title.get_width()/self.SS, 18))
            self.p_back = Button((M,16,90,34), L("back"), self.f_small,
                                 base=BTN_BG, text_col=TEXT_LIGHT)
        else:
            self.screen.blit(title, (M,18))
            self.p_back = Button((self.W-M-90,16,90,34), L("back"), self.f_small,
                                 base=BTN_BG, text_col=TEXT_LIGHT)
        self.p_back.draw(self.screen)
        def lx(w): return (self.W-24-w/self.SS) if rtl else 24

        # cheeky subtitle under the header
        subt = self.f_tiny.render(self.shape(L("prefs_sub")), True, BOARD_BG)
        self.screen.blit(subt, (self.W/2-subt.get_width()/2/self.SS, 74))

        y = 104
        # Game mode (profile) selector — bigger, card-like
        lab = self.f_small.render(self.shape(L("game_mode")), True, TEXT_DARK)
        self.screen.blit(lab, (lx(lab.get_width()), y+8))
        self.p_prev = Button((150,y,42,40), "<", self.f_small)
        self.p_next = Button((self.W-66,y,42,40), ">", self.f_small)
        self.p_prev.draw(self.screen); self.p_next.draw(self.screen)
        namebox = pygame.Rect(198,y,self.W-266,40)
        self.screen.card(EMPTY_CELL, namebox, radius=10, shadow=False)
        nt = self.f_small.render(self.shape(self.mode_name()), True, TEXT_DARK)
        self.screen.blit(nt, nt.get_rect(center=namebox.center))
        y += 58
        # two checkbox rows: keep cheats between sessions / count cheats in best
        self.p_persist = self._pref_checkbox(
            y, L("persist_cheats"), self.cfg.get("persist_cheats", False), rtl)
        y += 44
        self.p_countbest = self._pref_checkbox(
            y, L("count_best"), self.cfg.get("count_cheats_in_best", False), rtl)
        y += 50
        lab = self.f_small.render(self.shape(L("assist_keys")), True, TEXT_DARK)
        self.screen.blit(lab, (lx(lab.get_width()), y)); y += 30

        # spread the assist rows over the remaining vertical space
        self.p_rows = []; acts = self.L("actions"); details = self.L("action_detail")
        remaining = self.H - y - 40
        row_step = max(54, remaining // len(ACTION_KEYS))
        row_h = min(62, row_step - 8)
        for action in ACTION_KEYS:
            row = pygame.Rect(24, y, self.W-48, row_h)
            self.screen.card((243, 236, 225), row, radius=12, shadow=True)
            desc = acts[action]
            detail = details.get(action, "")
            tag = L("hold") if action in HOLD_ACTIONS else L("tap")
            tagcol = ACCENT if action in HOLD_ACTIONS else (110, 155, 110)
            code = self.profile()["map"].get(action)
            listening = (self.capturing_action == action)
            if listening:
                cur_disp = L("press_key")
            else:
                nm = key_display_name(code) if isinstance(code, int) else None
                cur_disp = nm if nm else L("none")
            has_key = isinstance(code, int)
            kbw = 118
            keybox = pygame.Rect(0, y+(row_h-34)//2, kbw, 34)
            # the text column must never run under the key box
            text_pad = 16
            title_y = y + 9
            detail_y = y + 31
            # available width for the text column (between edge and key box)
            avail = self.W - 40 - kbw - 24 - text_pad
            if rtl:
                keybox.x = 34
                text_right = self.W - 40
                # title
                tt = self.f_small.render(self.shape(desc), True, TEXT_DARK)
                self.screen.blit(tt, (text_right-tt.get_width()/self.SS, title_y))
                # tag pill just left of the title
                tg = self.f_tiny.render(self.shape(tag), True, tagcol)
                tgx = text_right - tt.get_width()/self.SS - 10 - tg.get_width()/self.SS
                self.screen.blit(tg, (tgx, title_y+2))
                # detail (clipped to avail width)
                dsurf = self._clip_text(detail, self.f_tiny, avail, BOARD_BG)
                self.screen.blit(dsurf, (text_right-dsurf.get_width()/self.SS, detail_y))
            else:
                keybox.x = self.W-40-kbw
                tt = self.f_small.render(self.shape(desc), True, TEXT_DARK)
                self.screen.blit(tt, (40, title_y))
                tg = self.f_tiny.render(self.shape(tag), True, tagcol)
                self.screen.blit(tg, (40+tt.get_width()/self.SS+10, title_y+2))
                dsurf = self._clip_text(detail, self.f_tiny, avail, BOARD_BG)
                self.screen.blit(dsurf, (40, detail_y))
            box_col = ACCENT if listening else EMPTY_CELL
            self.screen.rect(box_col, keybox, border_radius=8)
            txt_col = (TEXT_LIGHT if listening else
                       (TEXT_DARK if has_key else BOARD_BG))
            kt = self.f_tiny.render(self.shape(cur_disp), True, txt_col)
            self.screen.blit(kt, kt.get_rect(center=keybox.center))
            self.p_rows.append((action, keybox)); y += row_step
        note = self.f_tiny.render(self.shape(L("click_to_set")), True, BOARD_BG)
        self.screen.blit(note, (self.W/2-note.get_width()/2/self.SS, self.H-28))

        # --- Confession dialog overlay ---
        if self.confessing:
            self._draw_confession()
        # --- Praise dialog overlay (chose to stop cheating) ---
        if self.praising:
            self._draw_praise()

    def _draw_confession(self):
        L = self.L
        # dim the screen
        dim = pygame.Surface((self.W*self.SS, self.H*self.SS), pygame.SRCALPHA)
        dim.fill((30, 26, 22, 180))
        self.screen.surf.blit(dim, (0, 0))
        # dialog box
        dw, dh = 400, 240
        dx, dy = (self.W-dw)//2, (self.H-dh)//2
        self.screen.rect(BG, (dx, dy, dw, dh), border_radius=16)
        self.screen.rect(ACCENT, (dx, dy, dw, 6), border_radius=6)
        cx = self.W//2
        t = self.f_med.render(self.shape(L("confess_title")), True, TEXT_DARK)
        self.screen.blit(t, (cx-t.get_width()/2/self.SS, dy+22))
        b = self.f_small.render(self.shape(L("confess_body")), True, TEXT_DARK)
        self.screen.blit(b, (cx-b.get_width()/2/self.SS, dy+64))
        ln = self.f_small.render(self.shape(L("confess_line")), True, ACCENT)
        self.screen.blit(ln, (cx-ln.get_width()/2/self.SS, dy+96))
        # buttons
        yesw = self.f_small.size(L("confess_yes"))[0]/self.SS + 40
        now  = self.f_small.size(L("confess_no"))[0]/self.SS + 40
        gap = 16
        total = yesw + now + gap
        bx = cx - total/2
        by = dy + dh - 64
        self.cf_yes = Button((bx, by, yesw, 46), L("confess_yes"),
                             self.f_small, base=BTN_BG, text_col=TEXT_LIGHT)
        self.cf_no = Button((bx+yesw+gap, by, now, 46), L("confess_no"),
                            self.f_small, base=ACCENT, text_col=TEXT_LIGHT)
        self.cf_yes.draw(self.screen); self.cf_no.draw(self.screen)

    def _draw_praise(self):
        L = self.L
        GREEN = (60, 170, 110)
        dim = pygame.Surface((self.W*self.SS, self.H*self.SS), pygame.SRCALPHA)
        dim.fill((22, 34, 26, 180))
        self.screen.surf.blit(dim, (0, 0))
        dw, dh = 420, 250
        dx, dy = (self.W-dw)//2, (self.H-dh)//2
        self.screen.rect(BG, (dx, dy, dw, dh), border_radius=16)
        self.screen.rect(GREEN, (dx, dy, dw, 6), border_radius=6)
        cx = self.W//2
        # green check circle
        self.screen.circle(GREEN, (cx, dy+46), 22)
        ck = self.f_med.render("\u2713", True, TEXT_LIGHT)
        self.screen.blit(ck, ck.get_rect(center=(cx, dy+46)))
        t = self.f_med.render(self.shape(L("praise_title")), True, GREEN)
        self.screen.blit(t, (cx-t.get_width()/2/self.SS, dy+78))
        b = self.f_small.render(self.shape(L("praise_body")), True, TEXT_DARK)
        self.screen.blit(b, (cx-b.get_width()/2/self.SS, dy+118))
        b2 = self.f_tiny.render(self.shape(L("praise_body2")), True, BOARD_BG)
        self.screen.blit(b2, (cx-b2.get_width()/2/self.SS, dy+146))
        okw = self.f_small.size(L("praise_ok"))[0]/self.SS + 60
        self.pr_ok = Button((cx-okw/2, dy+dh-58, okw, 46), L("praise_ok"),
                            self.f_small, base=GREEN, text_col=TEXT_LIGHT)
        self.pr_ok.draw(self.screen)

    def start_key_capture(self, action):
        """Enter listening mode: the next key pressed becomes this action's key."""
        self.capturing_action = action

    def assign_captured_key(self, keycode):
        """Assign a captured key to the action currently being configured."""
        action = self.capturing_action
        self.capturing_action = None
        if action is None:
            return
        if keycode == pygame.K_ESCAPE:
            return  # cancel, keep existing
        if keycode == pygame.K_BACKSPACE or keycode == pygame.K_DELETE:
            self.profile()["map"].pop(action, None)  # clear binding
            self.cheat_dirty = True; return
        if keycode in RESERVED_KEYS:
            return  # can't bind gameplay keys
        # remove this key from any other action in this profile (no duplicates)
        for a in list(self.profile()["map"].keys()):
            if self.profile()["map"].get(a) == keycode:
                self.profile()["map"].pop(a, None)
        self.profile()["map"][action] = keycode
        # NOTE: not saved to disk yet - requires "confession" on leaving.
        self.cheat_dirty = True

    def handle_event(self, e):
        if e.type==pygame.QUIT: self.running = False; return
        if self.state=="game": self._game_ev(e)
        elif self.state=="settings": self._settings_ev(e)
        elif self.state=="preferences": self._preferences_ev(e)
    def _game_ev(self, e):
        if e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
            if self.game_buttons["settings"].hit(e.pos): self.state="settings"; return
            if getattr(self,"update_badge",None) and self.update_badge.collidepoint(e.pos):
                self.state="settings"; return
            if self.refresh_box.collidepoint(e.pos): self.new_game(); return
            if self.sel_up.collidepoint(e.pos):
                self._change_grid(+1); return
            if self.sel_down.collidepoint(e.pos):
                self._change_grid(-1); return
            if self.sel_box.collidepoint(e.pos):
                self._change_grid(+1); return
            if self.icon_sound.collidepoint(e.pos):
                self.cfg["sound"] = not self.cfg["sound"]; save_config(self.cfg); return
            if self.icon_mode.collidepoint(e.pos):
                self.cfg["infinite"] = not self.cfg["infinite"]
                save_config(self.cfg)
                if self.cfg["infinite"]: self.keep_going = True
                return
        elif e.type==pygame.KEYDOWN:
            taps = self.taps_for_key(e.key)
            if taps:
                for a in taps: self.do_tap_action(a)
                return
            # Game over -> Enter starts a fresh game
            if not self.board.can_move() and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.new_game(); return
            # Win screen (non-infinite) -> Enter keeps going
            if self.won and not self.keep_going and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.keep_going = True
            if e.key in (pygame.K_LEFT,pygame.K_a): self.handle_move("left")
            elif e.key in (pygame.K_RIGHT,pygame.K_d): self.handle_move("right")
            elif e.key in (pygame.K_UP,pygame.K_w): self.handle_move("up")
            elif e.key in (pygame.K_DOWN,pygame.K_s): self.handle_move("down")

    def _change_grid(self, delta):
        sizes = [4,5,6]
        i = sizes.index(self.cfg["grid_size"]) if self.cfg["grid_size"] in sizes else 0
        i = (i + delta) % len(sizes)
        self.cfg["grid_size"] = sizes[i]
        save_config(self.cfg)
        self.new_game()
    def _do_confirmed_action(self):
        which = self._confirm[1] if self._confirm else None
        self._confirm = None
        if which == "reset_settings":
            hs = self.cfg.get("highscore", 0)   # keep the high score
            self.cfg = default_config()
            self.cfg["highscore"] = hs
            save_config(self.cfg); self._sync_lang(); self.new_game()
            self.toast = [self.L("done_reset"), 150]
        elif which == "reset_score":
            self.cfg["highscore"] = 0
            save_config(self.cfg)
            self.toast = [self.L("done_reset"), 150]

    def _draw_confirm(self):
        L = self.L
        q, _ = self._confirm
        dim = pygame.Surface((self.W*self.SS, self.H*self.SS), pygame.SRCALPHA)
        dim.fill((30, 26, 22, 180)); self.screen.surf.blit(dim, (0, 0))
        dw, dh = 400, 180
        dx, dy = (self.W-dw)//2, (self.H-dh)//2
        self.screen.rect(BG, (dx, dy, dw, dh), border_radius=16)
        self.screen.rect(ACCENT, (dx, dy, dw, 6), border_radius=6)
        cx = self.W//2
        qt = self.f_small.render(self.shape(q), True, TEXT_DARK)
        self.screen.blit(qt, (cx-qt.get_width()/2/self.SS, dy+50))
        yesw = self.f_small.size(L("yes"))[0]/self.SS + 50
        now = self.f_small.size(L("no"))[0]/self.SS + 50
        gap = 16; total = yesw+now+gap; bx = cx-total/2; by = dy+dh-58
        self.cfm_yes = Button((bx, by, yesw, 44), L("yes"), self.f_small,
                              base=ACCENT, text_col=TEXT_LIGHT)
        self.cfm_no = Button((bx+yesw+gap, by, now, 44), L("no"), self.f_small,
                             base=BTN_BG, text_col=TEXT_LIGHT)
        self.cfm_yes.draw(self.screen); self.cfm_no.draw(self.screen)

    def _settings_ev(self, e):
        # Confirmation dialog takes over input while shown
        if self._confirm:
            if e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
                if hasattr(self,"cfm_yes") and self.cfm_yes.hit(e.pos):
                    self._do_confirmed_action(); return
                if hasattr(self,"cfm_no") and self.cfm_no.hit(e.pos):
                    self._confirm = None; return
            return
        if e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
            if self.s_back.hit(e.pos): self.state="game"; return
            for sz,b in self.s_grid:
                if b.hit(e.pos):
                    if self.cfg["grid_size"]!=sz:
                        self.cfg["grid_size"]=sz; save_config(self.cfg); self.new_game()
                    return
            for code,b in self.s_lang:
                if b.hit(e.pos):
                    self.cfg["language"]=code; save_config(self.cfg); return
            for val,b in self.s_sound:
                if b.hit(e.pos):
                    self.cfg["sound"]=val; save_config(self.cfg); return
            for val,b in self.s_winmode:
                if b.hit(e.pos):
                    self.cfg["infinite"]=val; save_config(self.cfg)
                    if val: self.keep_going = True
                    return
            for val,b in self.s_tips:
                if b.hit(e.pos):
                    self.cfg["show_tips"]=val; save_config(self.cfg)
                    self._tip_now = None  # reset current tip
                    return
            if hasattr(self,"s_reset_settings") and self.s_reset_settings.hit(e.pos):
                self._confirm = (self.L("reset_settings_q"), "reset_settings"); return
            if hasattr(self,"s_reset_score") and self.s_reset_score.hit(e.pos):
                self._confirm = (self.L("reset_score_q"), "reset_score"); return
            if self.s_prefs.hit(e.pos):
                self.enter_preferences(); return
            if hasattr(self,"a_recheck") and self.a_recheck.collidepoint(e.pos):
                self._start_update_check(); return
            if hasattr(self,"s_github") and self.s_github.hit(e.pos):
                if getattr(self, "_github_target", "repo") == "release":
                    self.open_releases()
                else:
                    self.open_github()
                return
            if hasattr(self,"s_profile") and self.s_profile.collidepoint(e.pos):
                self.open_profile(); return

    def enter_preferences(self):
        """Open the Cheaters' Refuge, snapshotting current cheat state so we can
        tell on exit whether the player ENABLED or DISABLED cheating - by any
        means (editing a key OR switching to a cheat profile)."""
        self._profiles_snapshot = copy.deepcopy(self.cfg["profiles"])
        self._entry_profile = self.cfg["active_profile"]
        self._entry_cheat_on = self._active_cheat_on()
        self.cheat_dirty = False
        self.confessing = False
        self.praising = False
        self.state = "preferences"

    def _active_cheat_on(self):
        """True if the currently active profile has at least one cheat key."""
        m = self.profile().get("map", {})
        return any(isinstance(v, int) for v in m.values())

    def _count_cheat_keys(self, profiles):
        """Total number of assigned cheat keys across all profiles."""
        n = 0
        for p in profiles:
            m = p.get("map", {})
            n += sum(1 for v in m.values() if isinstance(v, int))
        return n

    def leave_preferences(self):
        """On exit: compare whether cheating is ON now vs when we entered.
        - was OFF, now ON  -> enabling cheats -> demand confession.
        - was ON,  now OFF -> disabling cheats -> praise + save.
        - unchanged on/off -> save any profile switch and just leave."""
        now_on = self._active_cheat_on()
        was_on = getattr(self, "_entry_cheat_on", False)
        profile_changed = (self.cfg["active_profile"] != getattr(self, "_entry_profile", self.cfg["active_profile"]))
        if (not was_on) and now_on:
            # cheating turned on (by editing keys or switching to a cheat mode)
            self.confessing = True
        elif was_on and (not now_on):
            # cheating turned off -> reward, save immediately
            save_config(self.cfg)
            self.cheat_dirty = False
            self.praising = True
        else:
            # no change in cheat on/off; persist edits/switches and leave
            if self.cheat_dirty or profile_changed:
                save_config(self.cfg)
                self.cheat_dirty = False
            self.state = "settings"

    def confess_yes(self):
        # They admitted it -> persist the cheat settings.
        save_config(self.cfg)
        self.cheat_dirty = False
        self.confessing = False
        self.state = "settings"

    def confess_no(self):
        # They refused -> discard cheat changes, send them back to practice.
        if self._profiles_snapshot is not None:
            self.cfg["profiles"] = copy.deepcopy(self._profiles_snapshot)
        # also revert the active profile selection to what it was on entry
        if hasattr(self, "_entry_profile"):
            self.cfg["active_profile"] = self._entry_profile
        self.cheat_dirty = False
        self.confessing = False
        self.toast = [self.L("confess_rejected"), 180]
        self.state = "settings"

    def praise_ok(self):
        # Acknowledge the praise and return to settings.
        self.praising = False
        self.toast = [self.L("praise_toast"), 200]
        self.state = "settings"

    def _preferences_ev(self, e):
        # Praise dialog takes over input while shown
        if self.praising:
            if e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
                if hasattr(self,"pr_ok") and self.pr_ok.hit(e.pos):
                    self.praise_ok(); return
            return
        # Confession dialog takes over input while shown
        if self.confessing:
            if e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
                if hasattr(self,"cf_yes") and self.cf_yes.hit(e.pos):
                    self.confess_yes(); return
                if hasattr(self,"cf_no") and self.cf_no.hit(e.pos):
                    self.confess_no(); return
            return
        # If we're waiting for a key, capture the next keypress
        if self.capturing_action is not None:
            if e.type == pygame.KEYDOWN:
                self.assign_captured_key(e.key)
                return
            if e.type == pygame.MOUSEBUTTONDOWN:
                self.capturing_action = None
        if e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
            if self.p_back.hit(e.pos): self.leave_preferences(); return
            if self.p_prev.hit(e.pos):
                self.cfg["active_profile"]=(self.cfg["active_profile"]-1)%len(self.cfg["profiles"])
                self._enforce_mode1_clean(); return
            if self.p_next.hit(e.pos):
                self.cfg["active_profile"]=(self.cfg["active_profile"]+1)%len(self.cfg["profiles"])
                self._enforce_mode1_clean(); return
            if hasattr(self,"p_persist") and self.p_persist.collidepoint(e.pos):
                self.cfg["persist_cheats"] = not self.cfg.get("persist_cheats", False)
                self.cheat_dirty = True
                return
            if hasattr(self,"p_countbest") and self.p_countbest.collidepoint(e.pos):
                self.cfg["count_cheats_in_best"] = not self.cfg.get("count_cheats_in_best", False)
                self.cheat_dirty = True
                return
            for action,box in self.p_rows:
                if box.collidepoint(e.pos):
                    self.start_key_capture(action); return

    def _enforce_mode1_clean(self):
        """Mode 1 is always the honest mode: clear any cheats from profile 0
        whenever it becomes active."""
        if self.cfg["active_profile"] == 0:
            if self.cfg["profiles"][0].get("map"):
                self.cfg["profiles"][0]["map"] = {}
                self.cheat_dirty = True

    def _is_installed(self):
        """Heuristic: is this copy running from an installed location (via the
        installer) rather than as a portable exe? Used to pick the right update
        asset. Installed copies live under Program Files or the per-user
        Programs folder; portable copies usually sit in Downloads/Desktop."""
        try:
            if not getattr(sys, "frozen", False):
                return False  # running from source -> treat as portable
            exe_dir = os.path.dirname(sys.executable).lower()
            markers = []
            for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
                v = os.environ.get(env)
                if v:
                    markers.append(v.lower())
            # LOCALAPPDATA installs go under \Programs\
            if any(exe_dir.startswith(m) for m in markers if m):
                if "programs" in exe_dir or "program files" in exe_dir:
                    return True
            return False
        except Exception:
            return False

    def _is_installed_safe(self):
        return self._is_installed()

    def _start_update_check(self):
        """Check GitHub Releases for a newer version, in a background thread so
        it never blocks the game or breaks offline use."""
        self.update_status = "checking"   # checking | latest | update | error
        def worker():
            try:
                import urllib.request, json as _json
                url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=5) as r:
                    data = _json.loads(r.read().decode("utf-8"))
                tag = (data.get("tag_name") or "").lstrip("vV")
                raw_tag = data.get("tag_name") or ""
                if tag and self._version_gt(tag, APP_VERSION):
                    self.update_available = tag
                    self.update_status = "update"
                    # Pick the best download asset. Prefer the installer
                    # Pick based on HOW this copy is running:
                    # installed copy -> prefer the installer; portable -> the exe.
                    assets = data.get("assets") or []
                    installer = None
                    standalone = None
                    for a in assets:
                        name = (a.get("name") or "").lower()
                        url = a.get("browser_download_url")
                        if not name.endswith(".exe"):
                            continue
                        if "setup" in name or "install" in name:
                            installer = installer or url
                        else:
                            standalone = standalone or url
                    if self._is_installed():
                        dl = installer or standalone
                        fallback_name = "2049_Setup.exe"
                    else:
                        dl = standalone or installer
                        fallback_name = "2049.exe"
                    if not dl and raw_tag:
                        dl = (f"https://github.com/{GITHUB_REPO}/releases/"
                              f"download/{raw_tag}/{fallback_name}")
                    self.update_download_url = dl
                else:
                    self.update_status = "latest"
            except Exception:
                self.update_status = "error"  # offline or no release yet
        try:
            import threading
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self.update_status = "error"

    def open_github(self):
        try:
            import webbrowser
            webbrowser.open(f"https://github.com/{GITHUB_REPO}")
        except Exception:
            pass

    def open_releases(self):
        # Prefer a direct .exe download; fall back to the releases page.
        try:
            import webbrowser
            url = getattr(self, "update_download_url", None)
            if not url:
                url = f"https://github.com/{GITHUB_REPO}/releases/latest"
            webbrowser.open(url)
        except Exception:
            pass

    def open_profile(self):
        try:
            import webbrowser
            owner = GITHUB_REPO.split("/")[0]
            webbrowser.open(f"https://github.com/{owner}")
        except Exception:
            pass

    @staticmethod
    def _version_gt(a, b):
        """Return True if version string a > b (e.g. '1.2.0' > '1.1.9')."""
        def parts(v):
            out = []
            for p in v.split("."):
                try: out.append(int(p))
                except Exception: out.append(0)
            return out
        return parts(a) > parts(b)

    def run(self):
        self.running = True
        while self.running:
            dt = self.clock.tick(60)/1000.0
            for e in pygame.event.get(): self.handle_event(e)
            if self.animating:
                self.anim_time += dt
                if self.anim_time >= self.anim_dur: self.finish_move()
            if self.toast:
                self.toast[1] -= 1
                if self.toast[1] <= 0: self.toast = None
            if self.state == "game" and not self.animating:
                self._update_tips(dt)
            if self.state=="game": self.draw_game()
            elif self.state=="settings": self.draw_settings()
            elif self.state=="preferences": self.draw_preferences()
            # smooth-downscale the hi-res render surface onto the window
            pygame.transform.smoothscale(self._render_surf, (self.W, self.H),
                                         self.window)
            pygame.display.flip()
        # On quit: don't persist unconfessed cheat changes.
        if self.cheat_dirty and self._profiles_snapshot is not None:
            self.cfg["profiles"] = self._profiles_snapshot
        # Unless the player explicitly opted to keep cheats between sessions,
        # wipe all cheat bindings so the game starts clean next time.
        if not self.cfg.get("persist_cheats", False):
            for p in self.cfg["profiles"]:
                p["map"] = {}
            self.cfg["active_profile"] = 0
        save_config(self.cfg); pygame.quit()


if __name__ == "__main__":
    Game().run()
