@echo off
setlocal
where py >nul 2>nul
if %ERRORLEVEL%==0 ( set "PY=py" ) else ( set "PY=python" )
%PY% -m pip install --quiet pyinstaller
pushd "%~dp0"
%PY% -m PyInstaller --noconfirm --onefile --windowed recorder_app.py
echo.
echo [DONE] dist\recorder_app.exe を配布できます。
popd
pause
endlocal
