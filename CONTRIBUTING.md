# Contributing to SlideVoice

Use [GitHub Issues](https://github.com/Sohampatil00/Slidevoice/issues) for reproducible bugs and feature proposals. Discuss substantial changes before implementation. This is a local MVP; keep setup and everyday presentation workflows simple.

## Development setup

1. Fork and clone the repository, then create a branch for your change.
2. Create a Python 3.12+ virtual environment and install `requirements-dev.txt`.
3. Copy `.env.example` to `.env` if needed. API keys and model downloads are not required for the automated tests.
4. Start the studio with `./start.command`, or use the manual setup in [configuration](docs/CONFIGURATION.md).

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
node --check app/static/app.js
```

Node.js is only needed for the JavaScript syntax check; there is no frontend package installation. If using uv, install with `uv pip install --python .venv/bin/python -r requirements-dev.txt`.

Tests use temporary project directories and mocked providers. Media tests invoke real FFmpeg and PDF rendering. LibreOffice and macOS preview tests skip when their system tools are unavailable. Real model inference is a separate manual check requiring the optional environment, downloaded weights, and an authorised voice sample. Never use paid API calls in automated tests.

## Pull requests

Explain the problem, resulting behaviour, and relevant validation. Update documentation when changing configuration, user-visible workflows, or the local API. Add meaningful regression coverage for bug fixes; avoid tests that simply repeat implementation details.

Keep `.env`, `data/`, model weights, virtual environments, personal presentations, generated videos, and reference recordings out of commits. Redact keys and personal content from logs and screenshots. Report security issues privately using [SECURITY.md](SECURITY.md).

## Licensing

SlideVoice does not yet have a source-code licence. Review the licensing section of the [README](README.md) and resolve any permissions you need with the repository owner before reusing or distributing source code. Do not add third-party assets without recording their origin and usage permissions.
