#!/usr/bin/env bash
# Start the outreach dashboard on macOS (or Linux). Run: ./start.sh
set -e
cd "$(dirname "$0")"

PY=""
for cmd in python3.13 python3.12 python3.11 python3; do
  if command -v "$cmd" >/dev/null 2>&1 && "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$cmd"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or newer is needed. See 'Step 1' in README.md."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "First run: setting things up (this takes a minute)..."
  "$PY" -m venv .venv
fi
# Install or update packages when requirements.txt has changed.
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
  touch .venv/.installed
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Add your keys to it later (see README.md)."
fi

exec .venv/bin/python -m app
