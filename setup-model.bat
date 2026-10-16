@echo off
title Tallyroll - download the Gemma model
cd /d "%~dp0"
echo.
echo   This downloads the Gemma model that reads your bills.
echo   It only needs to be done once, and needs the internet.
echo   After that, Tallyroll works completely offline.
echo.
where ollama >nul 2>nul
if errorlevel 1 (
  echo   Ollama is not installed yet.
  echo   1. Go to  https://ollama.com/download
  echo   2. Download and run the Windows installer.
  echo   3. Close this window and double-click setup-model.bat again.
  echo.
  pause
  exit /b 1
)
echo   Which model do you want?
echo.
echo     1  gemma3:4b    Small and quick. About 3 GB. Best for most laptops.
echo     2  gemma4:e4b   Newer and sharper on messy bills. Bigger download.
echo.
set "CHOICE=1"
set /p CHOICE=  Type 1 or 2 and press Enter [1]: 
set "MODEL=gemma3:4b"
if "%CHOICE%"=="2" set "MODEL=gemma4:e4b"
echo.
echo   Downloading %MODEL% ... this can take a while. Leave this window open.
echo.
ollama pull %MODEL%
if errorlevel 1 (
  echo.
  echo   The download did not finish. Check your internet and run this file again.
  pause
  exit /b 1
)
if not exist data mkdir data
> data\settings.json echo {"model": "%MODEL%"}
echo.
echo   Done. %MODEL% is ready.
echo   Now double-click start.bat to open Tallyroll.
echo.
pause
