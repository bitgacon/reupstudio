@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto missing
if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-core.txt
if errorlevel 1 goto failed
echo Core installed. Install FFmpeg separately; see README.md.
echo Optional AI runtimes and models install only from Settings ^> Libraries.
pause
exit /b 0
:missing
echo Install Python 3.11 x64 with the Python launcher first; see README.md.
pause
exit /b 2
:failed
echo Core installation failed. Review the error above; no AI models were installed.
pause
exit /b 1
