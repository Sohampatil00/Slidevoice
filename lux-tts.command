#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .lux-venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 .lux-venv
  else
    "${PYTHON:-python3.12}" -m venv .lux-venv
  fi
fi
if ! .lux-venv/bin/python -c 'from zipvoice.luxvoice import LuxTTS; import fastapi, uvicorn, soundfile, dotenv' >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python .lux-venv/bin/python -r requirements-lux.txt
  else
    .lux-venv/bin/python -m pip install -r requirements-lux.txt
  fi
fi
echo "Loading LuxTTS on port ${LUX_TTS_PORT:-8004}. First launch downloads model weights."
echo "Wait for 'Application startup complete'. Keep this terminal open; Ctrl+C unloads the model."
exec .lux-venv/bin/python -m uvicorn app.lux_server:app --host 127.0.0.1 --port "${LUX_TTS_PORT:-8004}"
