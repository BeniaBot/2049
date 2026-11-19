# Runs INSIDE a clean test VM on the user's desktop. The in-game update,
# end to end, with real clicks on the real buttons:
#   portable: A (current) finds B (newer) -> "Update now" -> the exe swaps
#             itself and comes back as B
#   installed: setup A, run it -> "Update now" -> B's installer runs silently
#              and relaunches the game as B
# The "release" is a local file:// JSON (TWENTY49_UPDATE_API) - no network.
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
  [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
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
  public static double Scale(IntPtr h) { RECT r; GetClientRect(h, out r); return r.R / 560.0; }
  public static void Click(IntPtr h, int lx, int ly) {
    double s = Scale(h); int x = (int)Math.Round(lx * s), y = (int)Math.Round(ly * s);
    IntPtr lp = (IntPtr)((y << 16) | (x & 0xFFFF));
    PostMessageW(h, 0x200, IntPtr.Zero, lp);            // WM_MOUSEMOVE: SDL takes the position from here
    System.Threading.Thread.Sleep(60);
    PostMessageW(h, 0x201, (IntPtr)1, lp);              // WM_LBUTTONDOWN
    System.Threading.Thread.Sleep(60);
    PostMessageW(h, 0x202, IntPtr.Zero, lp);            // WM_LBUTTONUP
  }
}
'@
[W]::SetProcessDPIAware() | Out-Null
$SETTINGS = @(76, 121); $UPDATE_NOW = @(280, 659)      # logical layout coordinates

function Wait-Window([int]$secs, [IntPtr]$notThis = [IntPtr]::Zero) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  do { $h = [W]::Find(); if ($h -ne [IntPtr]::Zero -and $h -ne $notThis) { return $h }; Start-Sleep -Milliseconds 250 } while ($sw.Elapsed.TotalSeconds -lt $secs)
  return [IntPtr]::Zero
}
function Close-All {
  $h = [W]::Find(); if ($h -ne [IntPtr]::Zero) { [W]::PostMessageW($h, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null }
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ((Get-Process 2049 -ErrorAction SilentlyContinue) -and $sw.Elapsed.TotalSeconds -lt 20) { Start-Sleep -Milliseconds 300 }
  Get-Process 2049 -ErrorAction SilentlyContinue | Stop-Process -Force
}
function Hash($p) { (Get-FileHash $p -Algorithm SHA256).Hash }
# B's version: C:\bench\B\VERSION.txt when the build folder has one
$NEW = '0.18.1'
if (Test-Path 'C:\bench\B\VERSION.txt') { $NEW = (Get-Content 'C:\bench\B\VERSION.txt' -Raw).Trim() }

try {
  $hashB = Hash 'C:\bench\B\2049.exe'
  # one release JSON with both assets - the game picks by how it is installed
  $api = @{ tag_name = ('v' + $NEW); assets = @(
    @{ name = '2049.exe'; size = (Get-Item 'C:\bench\B\2049.exe').Length; browser_download_url = 'file:///C:/bench/B/2049.exe' },
    @{ name = '2049_Setup.exe'; size = (Get-Item 'C:\bench\B\2049_Setup.exe').Length; browser_download_url = 'file:///C:/bench/B/2049_Setup.exe' }) }
  $api | ConvertTo-Json -Depth 4 | Set-Content 'C:\bench\api.json' -Encoding ASCII
  $env:TWENTY49_UPDATE_API = 'file:///C:/bench/api.json'
  $trace = Join-Path $out 'trace.txt'
  $env:TWENTY49_TRACE = $trace                  # every copy that starts logs its version
  function Runs-Version([string]$v) { (Test-Path $trace) -and ((Get-Content $trace -Raw) -match ("version " + [regex]::Escape($v))) }

  # ---------------- portable ----------------
  New-Item -ItemType Directory -Force 'C:\bench\portable' | Out-Null
  Copy-Item 'C:\bench\A\2049.exe' 'C:\bench\portable\2049.exe' -Force
  Start-Process 'C:\bench\portable\2049.exe' -WorkingDirectory 'C:\bench\portable' | Out-Null
  $h = Wait-Window 90
  Check 'portable A opens' ($h -ne [IntPtr]::Zero)
  Start-Sleep -Seconds 2
  # play a little first: the game in progress must survive the update
  # (virtual key, scan code): SDL decides the key by the scan code
  foreach ($k in @(@(0x25,0x4B), @(0x28,0x50), @(0x25,0x4B), @(0x28,0x50), @(0x27,0x4D), @(0x28,0x50))) {
    $lp = 1 -bor ($k[1] -shl 16) -bor (1 -shl 24)
    [W]::PostMessageW($h, 0x100, [IntPtr]$k[0], [IntPtr]$lp) | Out-Null
    Start-Sleep -Milliseconds 40
    [W]::PostMessageW($h, 0x101, [IntPtr]$k[0], [IntPtr]($lp -bor (1 -shl 30) -bor ([int]0x80000000))) | Out-Null
    Start-Sleep -Milliseconds 180
  }
  Start-Sleep -Seconds 2
  [W]::Shot($h, (Join-Path $out 'p1_badge.png'))
  [W]::Click($h, $SETTINGS[0], $SETTINGS[1]); Start-Sleep -Milliseconds 800
  [W]::Shot($h, (Join-Path $out 'p2_settings.png'))
  [W]::Click($h, $UPDATE_NOW[0], $UPDATE_NOW[1])
  $sw = [Diagnostics.Stopwatch]::StartNew()
  Start-Sleep -Milliseconds 300
  [W]::Shot($h, (Join-Path $out 'p3_downloading.png'))
  while ([W]::IsWindow($h) -and $sw.Elapsed.TotalSeconds -lt 90) { Start-Sleep -Milliseconds 250 }
  Check 'old version closed itself' (-not [W]::IsWindow($h)) ("{0:N1}s" -f $sw.Elapsed.TotalSeconds)
  $h2 = Wait-Window 90 $h
  Check 'new version came back by itself' ($h2 -ne [IntPtr]::Zero) ("{0:N1}s after the click" -f $sw.Elapsed.TotalSeconds)
  Check 'the exe on disk is now B' ((Hash 'C:\bench\portable\2049.exe') -eq $hashB)
  Check "the running game is really the new code ($NEW)" (Runs-Version $NEW)
  if ($h2 -ne [IntPtr]::Zero) { Start-Sleep -Milliseconds 1500; [W]::Shot($h2, (Join-Path $out 'p4_updated.png')) }
  Start-Sleep -Seconds 8
  Check 'leftover old exe cleaned up' (-not (Test-Path 'C:\bench\portable\2049.exe.old'))
  Check 'only one game running' (@(Get-Process 2049 -ErrorAction SilentlyContinue).Count -ge 1 -and [W]::Find() -eq $h2)
  Close-All
  $gs = Get-Content (Join-Path $env:APPDATA '2049\2049_game.json') -Raw | ConvertFrom-Json
  Check 'the game in progress survived the update' ($gs.moves -ge 3) ("moves " + $gs.moves + ", score " + $gs.score)

  # ---------------- installed ----------------
  Remove-Item $trace -ErrorAction SilentlyContinue
  $p = Start-Process 'C:\bench\A\2049_Setup.exe' -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/CURRENTUSER','/NORESTART' -PassThru -Wait
  $app = Join-Path $env:LOCALAPPDATA 'Programs\2049\2049.exe'
  Check 'A installed' ($p.ExitCode -eq 0 -and (Test-Path $app)) ("exit " + $p.ExitCode)
  Start-Process $app | Out-Null
  $h = Wait-Window 90
  Check 'installed A opens' ($h -ne [IntPtr]::Zero)
  Start-Sleep -Seconds 4
  [W]::Click($h, $SETTINGS[0], $SETTINGS[1]); Start-Sleep -Milliseconds 800
  [W]::Shot($h, (Join-Path $out 'i1_settings.png'))
  [W]::Click($h, $UPDATE_NOW[0], $UPDATE_NOW[1])
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ([W]::IsWindow($h) -and $sw.Elapsed.TotalSeconds -lt 90) { Start-Sleep -Milliseconds 250 }
  Check 'installed A closed for the installer' (-not [W]::IsWindow($h)) ("{0:N1}s" -f $sw.Elapsed.TotalSeconds)
  $h2 = Wait-Window 150 $h
  Check 'installer relaunched the game' ($h2 -ne [IntPtr]::Zero) ("{0:N1}s after the click" -f $sw.Elapsed.TotalSeconds)
  Check 'installed exe is now B' ((Hash $app) -eq $hashB)
  Check "the relaunched game is really the new code ($NEW)" (Runs-Version $NEW)
  if ($h2 -ne [IntPtr]::Zero) { Start-Sleep -Milliseconds 1500; [W]::Shot($h2, (Join-Path $out 'i2_updated.png')) }
  $slog = Join-Path $env:TEMP '2049-update\setup.log'
  if (Test-Path $slog) { Copy-Item $slog (Join-Path $out 'update_setup.log') }
  $ver = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
          Where-Object { $_.DisplayName -like '2049*' }).DisplayVersion
  Check "Windows lists version $NEW" ($ver -eq $NEW) ("" + $ver)
  Close-All
  $p = Start-Process (Join-Path $env:LOCALAPPDATA 'Programs\2049\unins000.exe') -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES' -PassThru -Wait
  Check 'uninstall' ($p.ExitCode -eq 0)
} catch { Note ("ERROR " + $_.Exception.Message) }
Note 'DONE'
