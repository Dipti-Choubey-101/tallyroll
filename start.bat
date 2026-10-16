@echo off
title Tallyroll
cd /d "%~dp0"
echo.
echo   Starting Tallyroll...
echo.

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo   Python is not installed yet.
  echo.
  echo   1. Go to  https://www.python.org/downloads/
  echo   2. Click the big yellow Download button and run the installer.
  echo   3. IMPORTANT: on the first screen, tick "Add python.exe to PATH".
  echo   4. When it finishes, double-click start.bat again.
  echo.
  pause
  exit /b 1
)

rem Optional: Pillow straightens and shrinks phone photos. Fine if this step is skipped.
%PY% -c "import PIL" >nul 2>nul || %PY% -m pip install --quiet --disable-pip-version-check pillow >nul 2>nul

where ollama >nul 2>nul
if errorlevel 1 (
  echo   Note: Ollama is not installed yet, so Tallyroll can only run in demo mode.
  echo   Install it from https://ollama.com/download then run setup-model.bat
  echo.
)

%PY% server.py
echo.
echo   Tallyroll has stopped.
pause
