#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .indic-venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 .indic-venv
  else
    PYTHON="${PYTHON:-python3}"
    "$PYTHON" -c 'import sys; assert sys.version_info >= (3, 12), "Install Python 3.12 or newer, or install uv."'
    "$PYTHON" -m venv .indic-venv
  fi
fi
if ! .indic-venv/bin/python -c 'import torch, torchaudio, miocodec, transformers' >/dev/null 2>&1; then
  echo "Installing the optional Indic-MIO runtime. This downloads large packages."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python .indic-venv/bin/python -r requirements-indic.txt
  else
    .indic-venv/bin/python -m pip install -r requirements-indic.txt
  fi
fi
echo "Loading Indic-MIO. First launch downloads several GB of model weights."
echo "Wait for 'Application startup complete', then generate narration in SlideVoice."
echo "Keep this terminal open. Press Ctrl+C to unload the models."
exec .indic-venv/bin/python -m uvicorn app.indic_server:app --host 127.0.0.1 --port "${INDIC_MIO_PORT:-8001}"
