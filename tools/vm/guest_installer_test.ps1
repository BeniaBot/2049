# Runs INSIDE a clean test VM on the user's desktop: install 2049_Setup.exe
# for the current user, run the installed game, try to install again while
# it runs (AppMutex must stop setup), uninstall (user data must stay).
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
Add-Type @'
using System; using System.Text; using System.Runtime.InteropServices;
public static class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  public static IntPtr Find() { IntPtr f = IntPtr.Zero;
    EnumWindows((h, l) => { var c = new StringBuilder(64); GetClassNameW(h, c, 64); var t = new StringBuilder(64); GetWindowTextW(h, t, 64);
      if (c.ToString() == "pygame" && t.ToString() == "2049" && IsWindowVisible(h)) { f = h; return false; } return true; }, IntPtr.Zero);
    return f; }
}
'@
function Wait-Window([int]$secs) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  do { $h = [W]::Find(); if ($h -ne [IntPtr]::Zero) { return $h }; Start-Sleep -Milliseconds 250 } while ($sw.Elapsed.TotalSeconds -lt $secs)
  return [IntPtr]::Zero
}
try {
  $setup = 'C:\bench\2049_Setup.exe'
  $p = Start-Process $setup -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/CURRENTUSER','/NORESTART',('/LOG="' + (Join-Path $out 'setup1.log') + '"') -PassThru -Wait
  Check 'silent per-user install succeeds' ($p.ExitCode -eq 0) ("exit " + $p.ExitCode)
  $app = Join-Path $env:LOCALAPPDATA 'Programs\2049\2049.exe'
  Check 'installed under %LOCALAPPDATA%\Programs\2049' (Test-Path $app)
  $lnk = Get-ChildItem (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs') -Recurse -Filter '2049*.lnk' -ErrorAction SilentlyContinue
  Check 'Start menu shortcut' ($null -ne $lnk)

  $sw = [Diagnostics.Stopwatch]::StartNew()
  Start-Process $app | Out-Null
  $h = Wait-Window 120
  Check 'installed game opens' ($h -ne [IntPtr]::Zero) ("{0:N1}s" -f $sw.Elapsed.TotalSeconds)

  # setup again while the game runs: AppMutex must hold it back
  $p = Start-Process $setup -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/CURRENTUSER','/NORESTART',('/LOG="' + (Join-Path $out 'setup2.log') + '"') -PassThru -Wait
  $logtxt = Get-Content (Join-Path $out 'setup2.log') -Raw -ErrorAction SilentlyContinue
  Check 'setup refuses while the game runs' ($p.ExitCode -ne 0) ("exit " + $p.ExitCode)
  # the log has the localized "2049 is running" message and Setup's answer
  Check 'because it saw the game running (AppMutex)' ($logtxt -match 'Defaulting to Cancel' -and $logtxt -match 'EAbort') ''

  [W]::PostMessageW($h, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  Start-Sleep -Seconds 4
  $data = Join-Path $env:APPDATA '2049\2049_config.json'
  Check 'game wrote its config' (Test-Path $data)

  $unins = Join-Path $env:LOCALAPPDATA 'Programs\2049\unins000.exe'
  $p = Start-Process $unins -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -PassThru -Wait
  Start-Sleep -Seconds 3
  Check 'uninstall succeeds' ($p.ExitCode -eq 0) ("exit " + $p.ExitCode)
  Check 'program files removed' (-not (Test-Path $app))
  Check 'best score and settings kept' (Test-Path $data)
} catch { Note ("ERROR " + $_.Exception.Message) }
Note 'DONE'
