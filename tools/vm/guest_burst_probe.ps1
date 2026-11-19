# Runs INSIDE a clean test VM: do fast key bursts reach the game? The same
# probe on two builds (C:\bench\A = previous release, C:\bench\B = candidate)
# so a difference between them is the build's, not the machine's.
# For each build and each gap: fresh data, 30 calm moves, close, reopen,
# 12 keys left/right in turn, close - moves counted from the saved game.
$ErrorActionPreference = 'Stop'
$out = 'C:\bench\out'
New-Item -ItemType Directory -Force $out | Out-Null
$log = Join-Path $out 'results.txt'
Set-Content $log -Value "" -Encoding UTF8
function Note([string]$s) { Add-Content $log -Value $s -Encoding UTF8 }
Add-Type -TypeDefinition @'
using System; using System.Text; using System.Runtime.InteropServices;
public static class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  public static IntPtr Find() { IntPtr f = IntPtr.Zero;
    EnumWindows((h, l) => { var c = new StringBuilder(64); GetClassNameW(h, c, 64); var t = new StringBuilder(64); GetWindowTextW(h, t, 64);
      if (c.ToString() == "pygame" && t.ToString() == "2049" && IsWindowVisible(h)) { f = h; return false; } return true; }, IntPtr.Zero);
    return f; }
  public static void Down(IntPtr h, int vk, int sc) { PostMessageW(h, 0x100, (IntPtr)vk, (IntPtr)(1 | (sc << 16) | (1 << 24))); }
  public static void Up(IntPtr h, int vk, int sc) { PostMessageW(h, 0x101, (IntPtr)vk, (IntPtr)(1 | (sc << 16) | (1 << 24) | (1 << 30) | (1 << 31))); }
}
'@
$KEYS = @{ left = @(0x25,0x4B); up = @(0x26,0x48); right = @(0x27,0x4D); down = @(0x28,0x50) }
function Tap($h, $k, [int]$gap) { $v = $KEYS[$k]; [W]::Down($h, $v[0], $v[1]); Start-Sleep -Milliseconds 25; [W]::Up($h, $v[0], $v[1]); Start-Sleep -Milliseconds $gap }
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
  foreach ($build in 'A', 'B') {
    $exe = "C:\bench\$build\2049.exe"
    foreach ($gap in 30, 30, 30, 120) {
      Remove-Item $data -Recurse -Force -ErrorAction SilentlyContinue
      Start-Process $exe | Out-Null; $h = Wait-Window 60; Start-Sleep -Seconds 2
      $seq = 'down','left','down','right'
      for ($i = 0; $i -lt 30; $i++) { Tap $h $seq[$i % 4] 140 }
      Start-Sleep -Seconds 1; Close-Game $h
      $m0 = (Saved).moves
      $tr = Join-Path $out ("trace_{0}_{1}.txt" -f $build, (Get-Random))
      $env:TWENTY49_TRACE = $tr; $env:TWENTY49_TRACE_INPUT = "1"
      Start-Process $exe | Out-Null; $h = Wait-Window 60; Start-Sleep -Seconds 2
      $fg = ([W]::GetForegroundWindow() -eq $h)
      foreach ($k in 'left','right','left','right','left','right','left','right','left','right','left','right') { Tap $h $k $gap }
      Start-Sleep -Milliseconds 1500; Close-Game $h
      Remove-Item Env:TWENTY49_TRACE, Env:TWENTY49_TRACE_INPUT -ErrorAction SilentlyContinue
      $lines = @(Get-Content $tr -ErrorAction SilentlyContinue)
      $kd = @($lines | Where-Object { $_ -match "keydown (left|right)" }).Count
      $mv = @($lines | Where-Object { $_ -match "move (left|right) moved" }).Count
      $bl = @($lines | Where-Object { $_ -match "move (left|right) blocked" }).Count
      $ig = @($lines | Where-Object { $_ -match "ignored" }).Count
      $sl = @($lines | Where-Object { $_ -match "slow frame" }).Count
      Note ("   trace: {0} keys arrived, {1} moved, {2} blocked by the rules, {3} ignored, {4} slow frames" -f $kd, $mv, $bl, $ig, $sl)
      $s = Saved
      Note ("{0} gap {1,3}ms: 12 keys -> {2,2} moves   (board had {3} moves before; window in front: {4})" -f $build, $gap, ($s.moves - $m0), $m0, $fg)
      ($s.grid | ForEach-Object { '      ' + (($_ | ForEach-Object { "{0,5}" -f $_ }) -join '') }) | ForEach-Object { Note $_ }
    }
  }
} catch { Note ("ERROR " + $_.Exception.Message) }
Note 'DONE'
