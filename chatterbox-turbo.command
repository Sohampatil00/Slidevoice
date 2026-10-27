#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .chatterbox-venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 .chatterbox-venv
  else
    "${PYTHON:-python3.12}" -m venv .chatterbox-venv
  fi
fi
if ! .chatterbox-venv/bin/python -c 'from chatterbox.tts_turbo import ChatterboxTurboTTS; import fastapi, uvicorn, soundfile, dotenv' >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python .chatterbox-venv/bin/python -r requirements-turbo.txt
  else
    .chatterbox-venv/bin/python -m pip install -r requirements-turbo.txt
  fi
fi
echo "Loading Chatterbox Turbo on port ${CHATTERBOX_TURBO_PORT:-8002}. First launch downloads model weights."
echo "Wait for 'Application startup complete'. Keep this terminal open; Ctrl+C unloads the model."
exec .chatterbox-venv/bin/python -m uvicorn app.turbo_server:app --host 127.0.0.1 --port "${CHATTERBOX_TURBO_PORT:-8002}"
