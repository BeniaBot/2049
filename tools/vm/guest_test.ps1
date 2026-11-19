# Runs INSIDE a clean test VM, on the logged-on user's desktop (scheduled task,
# interactive). Exercises the real 2049.exe the way a user would and writes
# C:\bench\out\results.txt plus screenshots. Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$exe = 'C:\bench\2049.exe'
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
using System;
using System.Text;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public static class G {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool SystemParametersInfoW(uint a, uint b, ref RECT r, uint c);
  [DllImport("user32.dll", EntryPoint="SystemParametersInfoW")] public static extern bool SpiSticky(uint a, uint b, ref STICKY s, uint c);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct STICKY { public uint cb, flags; }
  public static IntPtr Find() {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => {
      var c = new StringBuilder(64); GetClassNameW(h, c, 64);
      var t = new StringBuilder(64); GetWindowTextW(h, t, 64);
      if ((c.ToString() == "pygame" || c.ToString() == "SDL_app") && t.ToString() == "2049" && IsWindowVisible(h)) { found = h; return false; }
      return true; }, IntPtr.Zero);
    return found;
  }
  public static int Count() {
    int n = 0;
    EnumWindows((h, l) => {
      var c = new StringBuilder(64); GetClassNameW(h, c, 64);
      var t = new StringBuilder(64); GetWindowTextW(h, t, 64);
      if ((c.ToString() == "pygame" || c.ToString() == "SDL_app") && t.ToString() == "2049" && IsWindowVisible(h)) n++;
      return true; }, IntPtr.Zero);
    return n;
  }
  public static void Shot(IntPtr h, string path) {
    RECT r; GetClientRect(h, out r);
    using (var bmp = new Bitmap(Math.Max(1, r.R), Math.Max(1, r.B))) {
      using (var g = Graphics.FromImage(bmp)) { IntPtr dc = g.GetHdc(); PrintWindow(h, dc, 3); g.ReleaseHdc(dc); }
      bmp.Save(path, ImageFormat.Png);
    }
  }
  public static void Key(IntPtr h, int vk, int sc, bool ext) {
    int lp = 1 | (sc << 16) | (ext ? (1 << 24) : 0);
    PostMessageW(h, 0x100, (IntPtr)vk, (IntPtr)lp);
    System.Threading.Thread.Sleep(30);
    PostMessageW(h, 0x101, (IntPtr)vk, (IntPtr)(lp | (1 << 30) | (1 << 31)));
  }
  public static uint Sticky() { var s = new STICKY(); s.cb = 8; SpiSticky(0x3A, 8, ref s, 0); return s.flags; }
}
'@
[G]::SetProcessDPIAware() | Out-Null

function Wait-Window([int]$secs) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  do { $h = [G]::Find(); if ($h -ne [IntPtr]::Zero) { return $h }; Start-Sleep -Milliseconds 250 } while ($sw.Elapsed.TotalSeconds -lt $secs)
  return [IntPtr]::Zero
}
# seconds until the game has actually painted (the cream background shows)
function Wait-Painted($h, [int]$secs) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $tmp = Join-Path $out '_probe.png'
  do {
    [G]::Shot($h, $tmp)
    $bmp = [System.Drawing.Bitmap]::FromFile($tmp)
    $px = $bmp.GetPixel([int]($bmp.Width / 2), 20); $bmp.Dispose()
    if ($px.R -gt 200 -and $px.G -gt 200) { Remove-Item $tmp; return $sw.Elapsed.TotalSeconds }
    Start-Sleep -Milliseconds 250
  } while ($sw.Elapsed.TotalSeconds -lt $secs)
  return -1
}
function Close-Game($h) {
  [G]::PostMessageW($h, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ((Get-Process 2049 -ErrorAction SilentlyContinue) -and $sw.Elapsed.TotalSeconds -lt 20) { Start-Sleep -Milliseconds 250 }
  return -not (Get-Process 2049 -ErrorAction SilentlyContinue)
}

try {
  $os = Get-CimInstance Win32_OperatingSystem
  Note ("OS: " + $os.Caption + " " + $os.Version + " | user: " + $env:USERNAME)
  $data = Join-Path $env:APPDATA '2049'
  Check 'clean machine: no 2049 data yet' (-not (Test-Path $data))
  $before = [G]::Sticky()

  $sw = [Diagnostics.Stopwatch]::StartNew()
  Start-Process $exe | Out-Null
  $h = Wait-Window 120
  Check 'first launch opens the window' ($h -ne [IntPtr]::Zero) ("{0:N1}s" -f $sw.Elapsed.TotalSeconds)
  if ($h -eq [IntPtr]::Zero) { throw 'no window' }
  $p = Wait-Painted $h 30
  Check 'first launch paints the game' ($p -ge 0) ("window to game on screen {0:N1}s; launch to game {1:N1}s" -f $p, $sw.Elapsed.TotalSeconds)
  Start-Sleep -Seconds 1
  $r = New-Object G+RECT; [G]::GetClientRect($h, [ref]$r) | Out-Null
  $wa = New-Object G+RECT; [G]::SystemParametersInfoW(0x30, 0, [ref]$wa, 0) | Out-Null
  $wr = New-Object G+RECT; [G]::GetWindowRect($h, [ref]$wr) | Out-Null
  $dpi = [G]::GetDpiForWindow($h)
  Check 'window fits the work area' ($wr.T -ge $wa.T -and $wr.B -le $wa.B + 1) ("client {0}x{1} @ {2} dpi; window y {3}..{4}; work area {5}x{6}" -f $r.R, $r.B, $dpi, $wr.T, $wr.B, ($wa.R - $wa.L), ($wa.B - $wa.T))
  $during = [G]::Sticky()
  Check 'sticky-keys shortcut off while focused' ((($before -band 1) -ne 0) -or (($during -band 4) -eq 0)) ("{0:x} -> {1:x}" -f $before, $during)
  [G]::Shot($h, (Join-Path $out '1_start.png'))

  foreach ($k in @(@(0x25,0x4B), @(0x28,0x50), @(0x25,0x4B), @(0x28,0x50), @(0x27,0x4D), @(0x28,0x50), @(0x25,0x4B), @(0x28,0x50))) {
    [G]::Key($h, $k[0], $k[1], $true); Start-Sleep -Milliseconds 150
  }
  Start-Sleep -Seconds 1
  [G]::Shot($h, (Join-Path $out '2_after_moves.png'))

  # second copy
  [G]::ShowWindow($h, 6) | Out-Null; Start-Sleep -Milliseconds 600
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $p2 = Start-Process $exe -PassThru
  $exited = $p2.WaitForExit(30000)
  Check 'second launch exits by itself' $exited ("{0:N1}s" -f $sw.Elapsed.TotalSeconds)
  Start-Sleep -Seconds 1
  Check 'still exactly one game window' ([G]::Count() -eq 1)
  Check 'first window restored' (-not [G]::IsIconic($h))
  Check 'first window in front' ([G]::GetForegroundWindow() -eq $h)

  # close -> files written
  Check 'closes cleanly' (Close-Game $h)
  Check 'sticky-keys settings restored on exit' ([G]::Sticky() -eq $before) ("{0:x} -> {1:x}" -f $before, [G]::Sticky())
  $cfg = Join-Path $data '2049_config.json'; $gm = Join-Path $data '2049_game.json'
  Check 'config saved in %APPDATA%\2049' (Test-Path $cfg)
  Check 'current game saved' (Test-Path $gm)
  $saved = (Get-Content $gm -Raw -Encoding UTF8 | ConvertFrom-Json)
  $savedGrid = ($saved.grid | ForEach-Object { $_ -join ',' }) -join ';'
  Note ("saved grid: " + $savedGrid + " score " + $saved.score)

  # relaunch -> same board
  $sw = [Diagnostics.Stopwatch]::StartNew()
  Start-Process $exe | Out-Null
  $h = Wait-Window 60
  Check 'relaunch opens the window' ($h -ne [IntPtr]::Zero)
  $p = Wait-Painted $h 30
  Check 'relaunch paints the game' ($p -ge 0) ("launch to game on screen {0:N1}s" -f $sw.Elapsed.TotalSeconds)
  Start-Sleep -Seconds 1
  [G]::Shot($h, (Join-Path $out '3_resumed.png'))
  Close-Game $h | Out-Null
  $again = (Get-Content $gm -Raw -Encoding UTF8 | ConvertFrom-Json)
  $againGrid = ($again.grid | ForEach-Object { $_ -join ',' }) -join ';'
  Check 'game resumed exactly' ($againGrid -eq $savedGrid -and $again.score -eq $saved.score) $againGrid

  # a broken config must not crash the game or lose the best score
  $c = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
  Set-Content $cfg -Value '{"highscore": ' -Encoding UTF8
  Start-Process $exe | Out-Null
  $h = Wait-Window 60
  Check 'starts with a corrupt config' ($h -ne [IntPtr]::Zero)
  if ($h -ne [IntPtr]::Zero) {
    Wait-Painted $h 30 | Out-Null; Start-Sleep -Seconds 1
    [G]::Shot($h, (Join-Path $out '4_after_corrupt_config.png')); Close-Game $h | Out-Null
  }
  $c2 = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
  Check 'config recovered from its backup' ($null -ne $c2.language) ("highscore {0} -> {1}" -f $c.highscore, $c2.highscore)
} catch {
  Note ("ERROR " + $_.Exception.Message)
}
Note 'DONE'
