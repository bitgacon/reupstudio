@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONUTF8=1"
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "REUP_PYTHON=runtime\python.exe"
if not exist "%REUP_PYTHON%" set "REUP_PYTHON=.venv\Scripts\python.exe"
if not exist "%REUP_PYTHON%" set "REUP_PYTHON=..\MoneyPrinterTurbo\.venv\Scripts\python.exe"
if not exist "%REUP_PYTHON%" set "REUP_PYTHON=..\release\MPT\MoneyPrinterTurbo\runtime\python.exe"
if not exist "%REUP_PYTHON%" (
 echo Missing Python runtime. See HUONG_DAN.md.
 pause
 exit /b 2
)
"%REUP_PYTHON%" -s run.py %*
if errorlevel 1 pause
