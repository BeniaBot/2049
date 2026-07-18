@echo off
REM ============================================================
REM  Build 2049 into a single standalone offline .exe (Windows)
REM ============================================================
REM  One-time: install Python 3.9+ from python.org (tick "Add to PATH")
REM  Then just double-click this file. The exe appears in  dist\
REM ============================================================

echo Installing dependencies (if needed)...
python -m pip install --upgrade pygame python-bidi numpy pyinstaller

echo.
echo Building 2049.exe ...
pyinstaller --onefile --windowed --name "2049" ^
  --icon "icon.ico" ^
  --add-data "DejaVuSans.ttf;." ^
  --add-data "DejaVuSans-Bold.ttf;." ^
  --add-data "icon.ico;." ^
  --add-data "icon_64.png;." ^
  --add-data "icon_256.png;." ^
  --add-data "avatar.png;." ^
  2049.py

echo.
echo ============================================================
echo  DONE!  Your standalone game is here:
echo         dist\2049.exe
echo.
echo  The custom 2049 icon shows on the exe and in the taskbar.
echo  Fully offline, needs nothing else installed.
echo  Settings + high score are saved under
echo         %%APPDATA%%\2049\
echo  so they survive even if you move or delete the exe.
echo ============================================================
pause
