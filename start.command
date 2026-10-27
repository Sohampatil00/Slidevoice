#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -r requirements.txt
  else
    PYTHON="${PYTHON:-python3}"
    "$PYTHON" -c 'import sys; assert sys.version_info >= (3, 12), "Install Python 3.12 or newer, or install uv."'
    "$PYTHON" -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
  fi
fi
if [ ! -f .env ]; then
  cp .env.example .env
fi
echo "SlideVoice is starting at http://127.0.0.1:8765"
echo "Open that address in your browser. LuxTTS starts automatically when you generate narration."
echo "Press Ctrl+C to stop the studio and any LuxTTS model it started."
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8765}"
