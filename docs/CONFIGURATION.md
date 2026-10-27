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

## Gemini script generation

Set `GEMINI_API_KEY` in `.env` and restart the studio. `SCRIPT_PROVIDER=auto` prefers Gemini when its key is present; choose `gemini` or `claude` explicitly if needed. `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite`. Use **Generate scripts for all slides** above the editor to draft the whole presentation. Replacing scripts clears their narration audio. Script generation sends slide content to the selected provider. Unlabelled script matching still uses Anthropic.

## Optional Chatterbox Turbo

Start `./chatterbox-turbo.command` in a separate terminal and wait for **Application startup complete**. This uses the isolated `.chatterbox-venv` environment and downloads `ResembleAI/chatterbox-turbo` into `data/models/huggingface` on first run. Select **Chatterbox Turbo** in Narration source and upload 6–20 seconds of clean English speech in your accent. Existing samples longer than five seconds can be reused. Turbo requires an uploaded reference, not an Indic-MIO preset. The studio selects an available local speech server on startup, preferring LuxTTS when available or automatic startup is enabled. Indic-MIO can still be selected.

`CHATTERBOX_TURBO_BASE_URL` defaults to `http://127.0.0.1:8002`. `CHATTERBOX_TURBO_DEVICE` accepts `auto`, `mps`, `cuda`, or `cpu`; restart the model service after changing it. `CHATTERBOX_TURBO_API_KEY` optionally enables a shared Bearer token. Override the launcher port with `CHATTERBOX_TURBO_PORT=8004 ./chatterbox-turbo.command` and update the base URL accordingly.

Turbo uses English voice cloning, caches the current sample conditioning, splits narration into at most 280-character requests, and retains bounded retries for silent output. Accent preservation and speed depend on your hardware and recording; audition one slide first. On a 16 GB Mac, run one speech model at a time to avoid memory pressure. Stop its terminal with Ctrl+C when switching services. Audio caches are separated by model, sample, script, and speaking pace.

## Optional LuxTTS

Select **LuxTTS** under Narration source and click **Generate narration**. The studio starts the model automatically, including first-use setup and downloads; there is no separate LuxTTS command to run. Upload 3–20 seconds of clean English speech in your accent; existing samples work. The first five seconds are transcribed locally with Whisper, and the conditioning is cached until the sample changes. No speech API key is required. First startup downloads LuxTTS and Whisper weights.

The service uses `.lux-venv` and port 8004. `LUX_TTS_DEVICE` accepts `auto` (Apple MPS/CUDA when available), `mps`, `cuda`, or `cpu`. `LUX_TTS_BASE_URL` defaults to `http://127.0.0.1:8004`; `LUX_TTS_API_KEY` optionally enables Bearer authentication. Override the launcher port with `LUX_TTS_PORT=8005 ./lux-tts.command` and update the studio base URL to match. Restart the relevant service after configuration changes.

LuxTTS uses four inference steps, 48 kHz audio, and up to 1,200 characters per request. Speaking pace, scripts, reference recordings and engine configuration participate in caching. Existing silence detection and bounded retries remain active. Accent preservation must be auditioned with your own sample. Run one voice engine at a time on a 16 GB Mac. The pinned upstream code is installed only in the optional environment through `requirements-lux.txt`. CPU mode uses upstream ONNX inference and may download additional files.

### Automatic LuxTTS lifecycle

`LUX_TTS_AUTOSTART=1` is the default. Double-click `start.command` to start the studio, then generate narration with LuxTTS. The job status shows setup/loading progress while the isolated runtime is prepared. Merely opening the website does not download or load models. Identical cached narration does not start the model. Startup may take several minutes on first use. Managed runtime logs are saved in `data/logs/lux.log`.

Stop the studio normally with Ctrl+C to stop the LuxTTS process it owns. An independently started, healthy LuxTTS server is reused and is not stopped by the studio. Automatic startup is limited to loopback HTTP origins (`127.0.0.1` or `localhost`); remote, HTTPS, and custom-path servers must be managed separately. Set `LUX_TTS_AUTOSTART=0` to use the standalone `lux-tts.command` launcher manually. This is a single-launcher local workflow, not a native installer or hosted deployment.
