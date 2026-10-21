# Configuration

Start with `.env.example`. The studio launcher copies it to `.env` on first run if no `.env` exists. Edit the existing file and restart the relevant service to apply changes. Keep keys in `.env` or your process environment; never commit them. Existing environment variables take precedence over `.env` values.

## Application settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Empty | Enables optional Claude script generation and matching |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model identifier sent to Anthropic; choose one available to your account |
| `INDIC_MIO_BASE_URL` | `http://127.0.0.1:8001` | Speech server origin |
| `INDIC_MIO_API_KEY` | Empty | Optional Bearer token for the speech server; the bundled server validates it when set |
| `INDIC_MIO_MODEL` | `SPRINGLab/Indic-Mio` | Speech language model; must match the server |
| `INDIC_MIO_CODEC_MODEL` | `Aratako/MioCodec-25Hz-44.1kHz-v2` | Codec loaded by the bundled speech server |
| `INDIC_MIO_PRESET_ID` | Empty | Optional preset on an existing upstream server; the bundled server has no stock presets |
| `INDIC_MIO_DEVICE` | `auto` | Bundled speech model device: automatic CUDA/MPS/CPU selection, or an explicit device such as `cpu` |
| `INDIC_MIO_CODEC_DEVICE` | `cpu` | Bundled codec device |
| `MACOS_PREVIEW_VOICE` | `Aman` | Installed macOS voice used for preview speech; inspect with `say -v '?'` |
| `SOFFICE_PATH` | Auto-detected | Absolute path to LibreOffice's `soffice` executable |
| `FFMPEG_PATH` | System or package executable | Optional FFmpeg executable override |
| `SLIDEVOICE_DATA_DIR` | `data/` in the repository | Project storage directory; use an absolute path outside the checkout if overriding |
| `HF_HOME` | `data/models/huggingface` under the data directory | Optional Hugging Face cache override for the bundled model server |

The checked-in model identifier is the application's default, not a guarantee of availability on your Anthropic account. Change it if the API rejects the model.

The shell launchers also accept `PORT` (studio, default `8765`), `INDIC_MIO_PORT` (speech server, default `8001`), and `PYTHON` (fallback interpreter when uv is unavailable). Export these or prefix the command; the launchers select ports before Python loads `.env`:

```sh
PORT=8766 ./start.command
INDIC_MIO_PORT=8002 ./indic-mio.command
```

If changing the speech port, set `INDIC_MIO_BASE_URL=http://127.0.0.1:8002` in `.env` and restart the studio. Changing the studio port does not change the speech server port.

## Manual Python setup

The convenience scripts target macOS and Unix shells. A manual setup is also possible; system tools and neural inference need platform-specific validation.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`, use an equivalent file-copy command, and configure `SOFFICE_PATH` when importing PPTX. Native macOS preview speech is unavailable there; upload recordings or configure Indic-MIO.

For optional local cloning, create a separate environment and keep its server running:

```sh
python3.12 -m venv .indic-venv
.indic-venv/bin/python -m pip install -r requirements-indic.txt
.indic-venv/bin/python -m uvicorn app.indic_server:app --host 127.0.0.1 --port 8001
```

This installs large optional packages and downloads model weights on first model startup. Use one worker for each service. Do not expose either service publicly.

## Remote speech servers

SlideVoice expects the MioTTS `/health`, `/v1/presets`, and `/v1/tts` protocol, including base64 audio. A text-completion server alone is insufficient. Use a trusted HTTPS endpoint or an SSH tunnel to a loopback endpoint; unencrypted remote HTTP and URLs containing credentials or query tokens are rejected. Remote servers receive narration text and the selected reference recording. Review provider and preset terms before use.

## Existing environments

After pulling dependency changes, update the studio environment explicitly:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
```

If the environment was created with uv and lacks pip, use `uv pip install --python .venv/bin/python -r requirements-dev.txt`. Update optional model packages separately with `requirements-indic.txt` when needed. The launchers do not resolve every dependency change in an existing environment.

See [the run guide](../README_RUN.md) for health checks and troubleshooting.
