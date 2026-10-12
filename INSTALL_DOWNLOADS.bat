@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONUTF8=1"
set "PYTHONNOUSERSITE=1"
set "REUP_PYTHON=runtime\python.exe"
if not exist "%REUP_PYTHON%" set "REUP_PYTHON=.venv\Scripts\python.exe"
if not exist "%REUP_PYTHON%" set "REUP_PYTHON=..\MoneyPrinterTurbo\.venv\Scripts\python.exe"
if not exist "%REUP_PYTHON%" set "REUP_PYTHON=..\release\MPT\MoneyPrinterTurbo\runtime\python.exe"
if not exist "%REUP_PYTHON%" (
 echo ERROR: Python runtime not found. See HUONG_DAN.md.
 pause
 exit /b 2
)
echo Python: %REUP_PYTHON%
"%REUP_PYTHON%" -s -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('yt_dlp') else 1)"
if not errorlevel 1 goto verify
where uv >nul 2>nul
if not errorlevel 1 (
 uv pip install --python "%REUP_PYTHON%" "yt-dlp[default]"
 if errorlevel 1 goto failed
 goto verify
)
"%REUP_PYTHON%" -s -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('pip') else 1)"
if errorlevel 1 (
 echo ERROR: Neither uv nor pip is available. Install uv, then run this file again.
 goto failed
)
"%REUP_PYTHON%" -s -m pip install "yt-dlp[default]"
if errorlevel 1 goto failed
:verify
"%REUP_PYTHON%" -s -m yt_dlp --version
if errorlevel 1 goto failed
echo OK: Downloader is ready. Close the old Reup server and reopen MO_REUP_VOICE_STUDIO.bat.
pause
exit /b 0
:failed
echo ERROR: Downloader installation or verification failed. See the message above.
pause
exit /b 1
