# -*- coding: utf-8 -*-
"""Real-window check on Windows (no keyboard stealing: keys are posted to
the game window, screenshots via PrintWindow):

  * window size follows display scaling and fits the work area
  * real key messages move the board
  * a second launch exits at once and raises the first window
  * Sticky/Filter Keys shortcut hotkeys are off while the game runs and
    restored exactly when it exits

    python tools/real_window.py OUT_DIR [path\\to\\2049.exe | 2049.py]
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

os.environ.setdefault("SDL_VIDEODRIVER", "windows")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    user32.SetProcessDPIAware()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = sys.argv[1]
TARGET = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "2049.py")
os.makedirs(OUT, exist_ok=True)


def launch():
    if TARGET.endswith(".py"):
        return subprocess.Popen([sys.executable, TARGET], cwd=ROOT)
    return subprocess.Popen([TARGET], cwd=os.path.dirname(TARGET))


def find_window(pid=None, timeout=20):
    end = time.time() + timeout
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    while time.time() < end:
        found = []

        def cb(hwnd, _):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            title = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, title, 64)
            if cls.value in ("pygame", "SDL_app") and title.value == "2049" \
                    and user32.IsWindowVisible(hwnd):
                p = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
                if pid is None or p.value == pid:
                    found.append(hwnd)
            return True
        user32.EnumWindows(proto(cb), 0)
        if found:
            return found[0]
        time.sleep(0.2)
    return None


def client_size(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right, r.bottom


def capture(hwnd, path):
    import pygame
    w, h = client_size(hwnd)
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 3)          # client area | full content

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]
    bih = BIH()
    bih.biSize = ctypes.sizeof(BIH)
    bih.biWidth, bih.biHeight, bih.biPlanes, bih.biBitCount = w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    surf = pygame.image.frombuffer(buf.raw, (w, h), "BGRA")
    pygame.image.save(surf, path)


VK = {"left": (0x25, 0x4B), "up": (0x26, 0x48), "right": (0x27, 0x4D),
      "down": (0x28, 0x50)}


def post_key(hwnd, name):
    vk, sc = VK[name]
    lp = 1 | (sc << 16) | (1 << 24)            # extended key
    user32.PostMessageW(hwnd, 0x0100, vk, lp)                      # KEYDOWN
    time.sleep(0.03)
    user32.PostMessageW(hwnd, 0x0101, vk, lp | (1 << 30) | (1 << 31))  # KEYUP


class SK(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint)]


def sticky_flags():
    s = SK()
    s.cbSize = ctypes.sizeof(SK)
    user32.SystemParametersInfoW(0x003A, s.cbSize, ctypes.byref(s), 0)
    return s.dwFlags


results = []


def check(name, ok, info=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (("  [" + info + "]") if info else ""))


before = sticky_flags()
p1 = launch()
hwnd = find_window(p1.pid)
check("window appears", hwnd is not None)
if hwnd is None:
    p1.kill()
    sys.exit(1)
time.sleep(1.5)
w, h = client_size(hwnd)
dpi = user32.GetDpiForWindow(hwnd)
r = wintypes.RECT()
user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
check("window scaled with the display", abs(w / 560 - min(dpi / 96, w / 560)) < 0.02
      and w >= 560 * min(dpi / 96, (r.bottom - r.top) / 830) - 2,
      "client %dx%d at %d dpi, work area %dx%d" % (w, h, dpi, r.right - r.left,
                                                   r.bottom - r.top))
wr = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(wr))
check("whole window inside the work area", wr.top >= r.top - 1 and wr.bottom <= r.bottom + 1,
      "window y %d..%d" % (wr.top, wr.bottom))
during = sticky_flags()
check("sticky-keys shortcut off while the game has focus",
      (before & 1) or not (during & 0x4),
      "flags before %#x, during %#x" % (before, during))
capture(hwnd, os.path.join(OUT, "real_start.png"))
for k in ("left", "down", "left", "down", "right", "down"):
    post_key(hwnd, k)
    time.sleep(0.12)
time.sleep(0.8)
capture(hwnd, os.path.join(OUT, "real_after_moves.png"))

# a second copy must not open a second window
user32.ShowWindow(hwnd, 6)                     # minimize the first
time.sleep(0.5)
t0 = time.time()
p2 = launch()
try:
    rc = p2.wait(timeout=20)
except subprocess.TimeoutExpired:
    rc = None
    p2.kill()
check("second launch exits by itself", rc == 0, "rc=%r after %.1fs" % (rc, time.time() - t0))
time.sleep(0.8)
check("only one game window", find_window(None, 1) == hwnd)
check("first window restored from minimized", not user32.IsIconic(hwnd))
fg = user32.GetForegroundWindow()
check("first window brought to front", fg == hwnd, "fg=%r hwnd=%r" % (fg, hwnd))
capture(hwnd, os.path.join(OUT, "real_after_second_launch.png"))

user32.PostMessageW(hwnd, 0x0010, 0, 0)        # WM_CLOSE
try:
    p1.wait(timeout=15)
except subprocess.TimeoutExpired:
    p1.kill()
after = sticky_flags()
check("sticky-keys settings restored exactly on exit", after == before,
      "before %#x after %#x" % (before, after))
print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
