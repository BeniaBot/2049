# Runs INSIDE a clean test VM on the user's desktop: real play in the real
# exe with key messages - a long run of moves, the coach on screen, Mode 4
# assists (undo, clean, smart tile), fast key bursts - checked through the
# game's own saved state and screenshots.
$ErrorActionPreference = 'Stop'
$out = 'C:\bench\out'
New-Item -ItemType Directory -Force $out | Out-Null
$log = Join-Path $out 'results.txt'
Set-Content $log -Value "" -Encoding UTF8
function Note([string]$s) { Add-Content $log -Value $s -Encoding UTF8 }
function Check([string]$name, [bool]$ok, [string]$info = '') {
  $tag = if ($ok) { 'PASS ' } else { 'FAIL ' }
  $extra = if ($info) { "  [$info]" } else { '' }
  Note ($tag + $name + $extra)
}
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System; using System.Text; using System.Drawing; using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public static class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static IntPtr Find() { IntPtr f = IntPtr.Zero;
    EnumWindows((h, l) => { var c = new StringBuilder(64); GetClassNameW(h, c, 64); var t = new StringBuilder(64); GetWindowTextW(h, t, 64);
      if (c.ToString() == "pygame" && t.ToString() == "2049" && IsWindowVisible(h)) { f = h; return false; } return true; }, IntPtr.Zero);
    return f; }
  public static void Shot(IntPtr h, string path) { RECT r; GetClientRect(h, out r);
    using (var bmp = new Bitmap(Math.Max(1, r.R), Math.Max(1, r.B))) {
      using (var g = Graphics.FromImage(bmp)) { IntPtr dc = g.GetHdc(); PrintWindow(h, dc, 3); g.ReleaseHdc(dc); }
      bmp.Save(path, ImageFormat.Png); } }
  // vk, scan code, extended
  public static void Down(IntPtr h, int vk, int sc, bool ext) { PostMessageW(h, 0x100, (IntPtr)vk, (IntPtr)(1 | (sc << 16) | (ext ? 1 << 24 : 0))); }
  public static void Up(IntPtr h, int vk, int sc, bool ext) { PostMessageW(h, 0x101, (IntPtr)vk, (IntPtr)(1 | (sc << 16) | (ext ? 1 << 24 : 0) | (1 << 30) | (1 << 31))); }
}
'@
[W]::SetProcessDPIAware() | Out-Null
# (PowerShell names ignore case: $K would BE the $k parameter below)
$KEYS = @{ left = @(0x25,0x4B,$true); up = @(0x26,0x48,$true); right = @(0x27,0x4D,$true); down = @(0x28,0x50,$true);
        z = @(0x5A,0x2C,$false); c = @(0x43,0x2E,$false); x = @(0x58,0x2D,$false) }
function Tap($h, $k, [int]$gap = 120) { $v = $KEYS[$k]; [W]::Down($h, $v[0], $v[1], $v[2]); Start-Sleep -Milliseconds 25; [W]::Up($h, $v[0], $v[1], $v[2]); Start-Sleep -Milliseconds $gap }
function Wait-Window([int]$secs) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  do { $h = [W]::Find(); if ($h -ne [IntPtr]::Zero) { return $h }; Start-Sleep -Milliseconds 250 } while ($sw.Elapsed.TotalSeconds -lt $secs)
  return [IntPtr]::Zero
}
function Close-Game($h) {
  [W]::PostMessageW($h, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ((Get-Process 2049 -ErrorAction SilentlyContinue) -and $sw.Elapsed.TotalSeconds -lt 20) { Start-Sleep -Milliseconds 250 }
}
$data = Join-Path $env:APPDATA '2049'
$gameFile = Join-Path $data '2049_game.json'
function Saved { Get-Content $gameFile -Raw -Encoding UTF8 | ConvertFrom-Json }

try {
  # Mode 4 kept on purpose (as if confessed), tips on
  New-Item -ItemType Directory -Force $data | Out-Null
  $cfg = @{ config_version = 3; grid_size = 4; language = 'he'; active_profile = 3; highscore = 0; sound = $true;
            infinite = $true; show_tips = $true; persist_cheats = $true; count_cheats_in_best = $false; difficulty = 'normal';
            profiles = @(@{map = @{}}, @{map = @{force_4 = 1073742049}}, @{map = @{clean_stuck = 1073742049; undo = 1073742048}},
                         @{map = @{force_4 = 1073742049; clean_stuck = 99; undo = 122; spawn_corner = 1073742050; smart_spawn = 120}}) }
  $cfg | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $data '2049_config.json') -Encoding UTF8

  Start-Process 'C:\bench\2049.exe' | Out-Null
  $h = Wait-Window 90
  Check 'game opens' ($h -ne [IntPtr]::Zero)
  Start-Sleep -Seconds 2

  # 1) a long honest run, human pace: corner habit (down/left, right if stuck)
  $seq = 'down','left','down','left','down','right','down','left'
  for ($i = 0; $i -lt 60; $i++) { Tap $h $seq[$i % $seq.Count] 140 }
  Start-Sleep -Seconds 1
  [W]::Shot($h, (Join-Path $out '1_after_60_moves.png'))
  Close-Game $h
  $s1 = Saved
  Check 'a long run of real key presses moved the board' ($s1.moves -ge 40) ("moves " + $s1.moves + ", score " + $s1.score)
  Check 'honest play is not marked as cheating' (-not $s1.cheat_used)

  # 2) fast bursts: 12 keys 30 ms apart - none may be lost
  Start-Process 'C:\bench\2049.exe' | Out-Null; $h = Wait-Window 60; Start-Sleep -Seconds 2
  $before = (Saved).moves
  # left/right in turn: on a board in mid-game both are open almost always (a key on a
  # blocked direction is ignored by the rules - with left/down/right/down that made 12 -> 9
  # on a fair board; checked headless: every key reached the game, every open one moved)
  foreach ($k in 'left','right','left','right','left','right','left','right','left','right','left','right') { Tap $h $k 30 }
  Start-Sleep -Seconds 1
  Close-Game $h
  $s2 = Saved
  Check 'fast key bursts are not swallowed' (($s2.moves - $before) -ge 11) ("12 fast keys -> " + ($s2.moves - $before) + " moves")

  # 3) assists: undo (Z), smart tile (hold X), clean (C)
  Start-Process 'C:\bench\2049.exe' | Out-Null; $h = Wait-Window 60; Start-Sleep -Seconds 2
  Tap $h 'left' 300; Tap $h 'z' 400
  [W]::Down($h, 0x58, 0x2D, $false); Start-Sleep -Milliseconds 60
  Tap $h 'down' 200
  [W]::Up($h, 0x58, 0x2D, $false); Start-Sleep -Milliseconds 300
  Tap $h 'c' 300; Tap $h 'right' 600
  [W]::Shot($h, (Join-Path $out '3_after_assists.png'))
  Close-Game $h
  $s3 = Saved
  Check 'assists mark the game as assisted (no best-score laundering)' ($s3.cheat_used -eq $true)
  Check 'game survives assist use' ($s3.moves -ge $s2.moves) ("moves " + $s3.moves)
  $cfgAfter = Get-Content (Join-Path $data '2049_config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  Check 'kept assists stay kept (persist on)' ($cfgAfter.active_profile -eq 3)
} catch { Note ("ERROR " + $_.Exception.Message) }
Note 'DONE'
