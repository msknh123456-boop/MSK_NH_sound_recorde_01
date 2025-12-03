@echo off
setlocal EnableExtensions
chcp 65001>nul
cd /d "%~dp0"

set "PYCMD="
where py >nul 2>nul && (set "PYCMD=py -3")
if not defined PYCMD ( where python >nul 2>nul && (set "PYCMD=python") )
if not defined PYCMD ( echo [ERROR] Python not found & pause & exit /b 1 )

%PYCMD% -V || (echo [ERROR] Python failed & pause & exit /b 1)

if not exist ".venv" %PYCMD% -m venv .venv
call .venv\Scripts\activate.bat || (echo [ERROR] venv activate failed & pause & exit /b 1)

python -m pip install --upgrade pip
python -m pip install sounddevice numpy soundfile

python -V
python recorder_app.py
echo ==== 終了コード: %ERRORLEVEL% ====
pause
endlocal
