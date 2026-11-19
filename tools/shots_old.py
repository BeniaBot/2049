# Render the desktop screens headless to PNG (for visual review).
import os, sys, tempfile, pygame
from diag_common import load_game
out = sys.argv[1]
g = load_game(sys.argv[2] if len(sys.argv) > 2 else None)
g.save_config = lambda cfg: None
g.CONFIG_PATH = os.path.join(tempfile.mkdtemp(), "x.json")
g.Game._start_update_check = lambda self: setattr(self, "update_status", "error")
game = g.Game()
def snap(name):
    if game.state == "game": game.draw_game()
    elif game.state == "settings": game.draw_settings()
    else: game.draw_preferences()
    small = pygame.transform.smoothscale(game._render_surf, (game.W, game.H))
    pygame.image.save(small, os.path.join(out, name + ".png"))
for lang in ("he", "en"):
    game.cfg["language"] = lang
    game.state = "game"; game.board.grid = [[2,4,8,16],[32,64,128,256],[512,1024,2048,4096],[8192,16384,0,2]]
    game.cfg["show_tips"] = True; game._tip_now = [game.L("tip_stuck"), 3]
    snap(f"game_{lang}")
    game.state = "settings"; snap(f"settings_{lang}")
    game.enter_preferences(); snap(f"prefs_{lang}")
    game.cfg["active_profile"] = 3; snap(f"prefs4_{lang}")
    game.cfg["active_profile"] = 0
