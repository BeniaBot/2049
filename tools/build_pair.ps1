# Build the release pair used by the update tests:
#   A = this tree (version as in 2049.py)            -> build_v018\A\{2049.exe, 2049_Setup.exe}
#   B = the same tree stamped as a newer version      -> build_v018\B\{...}
# Nothing here is published; it only feeds tools\vm\guest_update_test.ps1.
param([string]$NewVersion = "0.18.1")
$ErrorActionPreference = 'Continue'   # PyInstaller logs to stderr; 5.1 would treat it as errors
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'build_v018'
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"

function Build([string]$src, [string]$dest) {
  New-Item -ItemType Directory -Force $dest | Out-Null
  $work = Join-Path $dest 'work'
  $args = @('-m','PyInstaller','--noconfirm','--onefile','--windowed','--name','2049','--exclude-module','numpy',
            '--icon',"$src\icon.ico",
            '--add-data',"$src\Rubik-Bold.ttf;.",'--add-data',"$src\Rubik-Medium.ttf;.",
            '--add-data',"$src\DejaVuSans.ttf;.",'--add-data',"$src\DejaVuSans-Bold.ttf;.",
            '--add-data',"$src\icon.ico;.",'--add-data',"$src\icon_64.png;.",
            '--add-data',"$src\icon_256.png;.",'--add-data',"$src\avatar.png;.",
            '--distpath',"$src\dist",'--workpath',$work,'--specpath',$work,"$src\2049.py")
  $log = Join-Path $dest 'pyinstaller.log'
  $p = Start-Process python -ArgumentList $args -NoNewWindow -Wait -PassThru -RedirectStandardError $log
  if ($p.ExitCode -ne 0) { throw "PyInstaller failed for $src (see $log)" }
  Push-Location $src
  & $iscc /Q installer.iss
  $rc = $LASTEXITCODE
  Pop-Location
  if ($rc -ne 0) { throw "Inno Setup failed for $src" }
  Copy-Item "$src\dist\2049.exe" $dest -Force
  Copy-Item "$src\Output\2049_Setup.exe" $dest -Force
}

"== A (this tree)"
Build $root (Join-Path $out 'A')

"== B ($NewVersion)"
$bsrc = Join-Path $out 'B_src'
Remove-Item $bsrc -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $bsrc | Out-Null
Get-ChildItem $root -File | Where-Object { $_.Extension -in '.py','.ttf','.ico','.png','.iss','.txt' } |
  Copy-Item -Destination $bsrc
$py = Join-Path $bsrc '2049.py'
(Get-Content $py -Raw -Encoding UTF8) -replace 'APP_VERSION = "[0-9.]+"', "APP_VERSION = `"$NewVersion`"" |
  Set-Content $py -Encoding UTF8 -NoNewline
$iss = Join-Path $bsrc 'installer.iss'
(Get-Content $iss -Raw) -replace '#define MyAppVersion "[0-9.]+"', "#define MyAppVersion `"$NewVersion`"" |
  Set-Content $iss -NoNewline
Build $bsrc (Join-Path $out 'B')

Get-ChildItem (Join-Path $out 'A'), (Join-Path $out 'B') -Filter *.exe |
  Select-Object @{n='file';e={$_.Directory.Name + '\' + $_.Name}}, Length,
                @{n='sha';e={(Get-FileHash $_.FullName).Hash.Substring(0,12)}}
