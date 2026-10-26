@echo off
REM Start the outreach dashboard on Windows. Double-click this file, or run start.bat
cd /d "%~dp0"

set PY=
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set PY=py -3
if not defined PY (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set PY=python
)
if not defined PY (
  echo Python 3.11 or newer is needed. See "Step 1" in README.md.
  pause
  exit /b 1
)

if not exist .venv (
  echo First run: setting things up ^(this takes a minute^)...
  %PY% -m venv .venv
  if errorlevel 1 ( pause & exit /b 1 )
)
REM Re-install packages when requirements.txt has changed
fc /b requirements.txt .venv\installed-requirements.txt >nul 2>nul
if errorlevel 1 (
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
  if errorlevel 1 ( pause & exit /b 1 )
  copy /y requirements.txt .venv\installed-requirements.txt >nul
)
if not exist .env (
  copy .env.example .env >nul
  echo Created .env. Add your keys to it later ^(see README.md^).
)

.venv\Scripts\python -m app
pause
