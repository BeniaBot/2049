@echo off
REM ============================================================
REM  Build the 2049 Windows INSTALLER (2049_Setup.exe)
REM ============================================================
REM  Requirements (one-time):
REM    1. Build the game first:  double-click build_exe.bat
REM       (this creates dist\2049.exe)
REM    2. Install Inno Setup (free): https://jrsoftware.org/isdl.php
REM
REM  Then double-click THIS file. The installer appears in:
REM       Output\2049_Setup.exe
REM ============================================================

echo Checking that the game exe exists...
if not exist "dist\2049.exe" (
    echo.
    echo  ERROR: dist\2049.exe not found.
    echo  Please run build_exe.bat first to build the game.
    echo.
    pause
    exit /b 1
)

echo Looking for the Inno Setup compiler (ISCC.exe)...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo.
    echo  ERROR: Inno Setup not found.
    echo  Install it from https://jrsoftware.org/isdl.php  then run this again.
    echo.
    pause
    exit /b 1
)

echo Building installer...
"%ISCC%" installer.iss

echo.
echo ============================================================
echo  DONE!  Your installer is here:
echo         Output\2049_Setup.exe
echo.
echo  It installs the same 2049.exe, adds a desktop shortcut and
echo  a Start-menu entry, and can be uninstalled from Windows
echo  Settings like any normal program.
echo ============================================================
pause
