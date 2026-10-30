@echo off
setlocal
cd /d "%~dp0"
py -3 -m aldervale --version >nul 2>nul
if not errorlevel 1 goto :foundpy
python -m aldervale --version >nul 2>nul
if not errorlevel 1 goto :foundpython
echo ALDERVALE needs Python 3.10 or newer on PATH or the py launcher.
echo Install it from https://www.python.org/downloads/ and try again.
pause
exit /b 1

:foundpy
set "RUNCMD=py -3"
goto :run

:foundpython
set "RUNCMD=python"

:run
if "%~1"=="--version" (
    %RUNCMD% -m aldervale --version
    exit /b 0
)
title Aldervale 3D - close this window to stop the server
%RUNCMD% -m aldervale --serve --open-play
if errorlevel 1 pause
exit /b 0
