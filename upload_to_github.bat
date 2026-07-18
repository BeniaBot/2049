@echo off
chcp 65001 >nul
REM ============================================================
REM  Upload 2049 to your GitHub repository (one-click)
REM ============================================================
REM  Repo: https://github.com/BeniaBot/2049
REM  BEFORE running: create the repo on github.com (empty).
REM ============================================================

set REPO_URL=https://github.com/BeniaBot/2049.git

echo Initializing git repository...
git init
git branch -M main
git add .
git commit -m "2049 - enhanced 2048 with hidden assists"
git remote remove origin 2>nul
git remote add origin %REPO_URL%

echo.
echo Pushing to %REPO_URL% ...
git push -u origin main

echo.
echo ============================================================
echo  Done. Refresh your repo page to see the files.
echo ============================================================
pause
