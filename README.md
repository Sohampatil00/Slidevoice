# SlideVoice

[![CI](https://github.com/Sohampatil00/Slidevoice/actions/workflows/ci.yml/badge.svg)](https://github.com/Sohampatil00/Slidevoice/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Status: local MVP](https://img.shields.io/badge/status-local%20MVP-orange)

A local-first studio that turns presentations into narrated videos. English scripts, your own voice through **Indic-MIO**, and automatic slide timing. No timeline editor or speech API subscription required.

**Start here:** [Step-by-step run instructions](README_RUN.md) explain how to start both Terminal services, generate your first video, and troubleshoot the “Indic-MIO is not reachable” error.

## What you can do

- Import PDF, PowerPoint, or slide images into a browser-based studio.
- Write narration per slide, import a complete script, or draft scripts with optional Claude integration.
- Clone an authorised voice locally with Indic-MIO, upload existing recordings, or try macOS preview speech.
- Audition individual slides, adjust speaking pace, and reuse cached narration.
- Export 1080p or 720p MP4 videos with slide durations measured from the actual audio.
- Download slide timestamps and scripts as `timings.json`.

**Project status:** version 0.1.0, a single-user local MVP. macOS has convenience launchers and native preview speech. Other platforms can use the manual Python setup with uploaded audio or Indic-MIO; platform and GPU compatibility depend on the installed media/model tools. There is no hosted service, account system, or collaboration feature.

## Quick start

Install Git and either **Python 3.12+** or **uv**, then clone the repository:

```sh
git clone https://github.com/Sohampatil00/Slidevoice.git
cd Slidevoice
./start.command
```

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)**. Click **Try a 3-slide example**, select **Free Mac preview**, generate narration, then create a video. The preview requires an installed macOS voice; it uses a system voice. For your own voice, start `./indic-mio.command` in a second Terminal and follow the voice setup below.

| Requirement | When you need it |
| --- | --- |
| Python 3.12+ or uv | Studio and optional model-server environments |
| Internet access | Initial dependency/model downloads and optional Claude API requests |
| LibreOffice | PPTX rendering; PDF and image imports do not need it |
| Several GB of free storage | Optional local speech packages and model weights; projects need additional space |
| Anthropic API key | Optional script drafting and unlabelled script matching |
| Clean 3–20 second voice recording | Local voice cloning; use a voice you own or are authorised to use |

No Node.js build step is required to run the studio. FFmpeg is available through `imageio-ffmpeg`. Local speech generation needs no paid speech API subscription. Claude requests may incur API charges.

## Documentation

- [Step-by-step usage and troubleshooting](README_RUN.md)
- [Configuration reference and manual setup](docs/CONFIGURATION.md)
- [Architecture, data storage, and local API](docs/ARCHITECTURE.md)
- [Contributing and validation](CONTRIBUTING.md)
- [Security and vulnerability reporting](SECURITY.md)
- [Changelog](CHANGELOG.md)

Continue below for [voice cloning](#your-own-indian-english-voice), [Claude scripts](#claude-scripts), [script import](#import-one-full-narration-script), [presentation formats](#presentation-import), [export](#audio-timing-and-export), and [privacy](#privacy-and-operation).

## Run on your Mac

Double-click `start.command`, or run it from Terminal:

```sh
cd /path/to/slidevoice
./start.command
```

Open **http://127.0.0.1:8765**. The launcher creates a Python environment on first run and downloads dependencies. It needs `uv` or Python 3.12+. Press Ctrl+C in the terminal to stop. A different port can be selected with `PORT=8766 ./start.command`.

For a quick no-model demo, click **Try a 3-slide example**, choose **Free Mac preview**, then **Generate narration** and **Create video**. This uses macOS's Indian-English **Aman** voice, not your voice clone. If this voice isn't installed, choose an installed Indian-English voice with `MACOS_PREVIEW_VOICE` in `.env`. List voices with `say -v '?'`. On other operating systems, use Indic-MIO or upload recordings.

## Your own Indian-English voice

1. Run `./indic-mio.command` in a second terminal. It installs optional dependencies into `.indic-venv` and starts the bundled model server on `127.0.0.1:8001`. First startup downloads several GB of public model weights into `data/models/huggingface`; allow time and disk space for this. Keep the terminal open while generating narration.
2. Wait for **Application startup complete**. The server loads `SPRINGLab/Indic-Mio` and MioCodec. It uses CUDA or Apple MPS for the speech language model when available, otherwise CPU. The codec defaults to CPU for compatibility. CPU inference can be slow; there is no promised real-time speed.
3. In the studio, select **Indic-MIO · local voice cloning**, confirm voice permission, and upload **3–20 seconds** of clean English speech in your natural accent. One speaker, no music. The upload is saved locally and normalised to WAV; generation sends it to the configured model server.
4. Use **Generate this slide's audio** to audition one slide before generating the deck. No speech API key is needed for the bundled server.

If inference fails on MPS, set `INDIC_MIO_DEVICE=cpu` in `.env` and restart the model server. Both launchers load the same `.env`; copy `.env.example` if it doesn't exist. Optional model packages are separate from the small studio environment, so importing/editing/exporting does not require PyTorch. Stop the model terminal with Ctrl+C to release its memory.

### Existing MioTTS-Inference server

Set `INDIC_MIO_BASE_URL` to its origin (default `http://127.0.0.1:8001`) and ensure its LLM backend actually serves `SPRINGLab/Indic-Mio`. SlideVoice uses the documented `GET /health`, `GET /v1/presets` and `POST /v1/tts` JSON/base64 protocol. It explicitly requests `INDIC_MIO_MODEL` in the synthesis payload. A generic OpenAI text-completion endpoint alone is **not** a speech server; MioCodec is required to turn speech tokens into audio.

For an NVIDIA server, the model author's recommended path is a vLLM backend plus [MioTTS-Inference](https://github.com/Aratako/MioTTS-Inference). Example, in that upstream repository after its installation:

```sh
vllm serve SPRINGLab/Indic-Mio --gpu-memory-utilization 0.5
# In another terminal in the upstream repository:
python run_server.py --host 127.0.0.1 --port 8001 \
  --llm-base-url http://127.0.0.1:8000/v1 --llm-model SPRINGLab/Indic-Mio
```

Use an SSH tunnel for a remote server so the studio can keep its loopback URL, or configure a trusted HTTPS server. Unencrypted non-loopback HTTP, embedded credentials, and query-string tokens are rejected. `INDIC_MIO_API_KEY` optionally supplies a Bearer header for a protected server. The studio never auto-deploys a server, rents a GPU, or sends a sample to Hugging Face's hosted inference API. Model-weight downloads are separate from synthesis; scripts/reference recordings are not part of those downloads.

You can alternatively choose a voice preset already installed on your upstream server using **Load server presets** or `INDIC_MIO_PRESET_ID`. The bundled server has no stock presets: it uses your reference recording. Upstream's included presets have their own usage restrictions; do not assume they are cleared for commercial work.

The voice recording determines the accent. Selecting English doesn't itself guarantee an Indian accent or perfect similarity. Check technical terms, names, and numbers. Only synthesize voices you own or are authorised to use.

## Claude scripts

Set `ANTHROPIC_API_KEY` in `.env` and restart. Click **Draft missing scripts** to fill blank scripts without overwriting your existing ones, or **Write with Claude** for the selected slide. Claude receives slide images, extracted text, speaker notes, and deck titles. Each completed script is saved immediately if a later request fails. You can always paste scripts from Claude manually instead.

`ANTHROPIC_MODEL` defaults to `claude-sonnet-5-5`. Claude usage may incur API charges; local Indic-MIO does not require a speech subscription. The UI confirms before sending content for generation. Opening the app only checks the configured model server's health; it does not send slides, scripts, or reference audio. No model is automatically downloaded just by opening the studio.

## Import one full narration script

After importing your presentation, click **Import full script** above the slide editor. Paste the entire narration, preview the assignments, edit any section, then click **Apply scripts to all slides**. Nothing is replaced until you apply the preview.

- **Slide headings (local):** put `Slide 1`, `Slide 2`, and so on on separate lines before each section. Include every slide in order. Markdown headings such as `## Slide 1` and bracketed headings such as `[Slide 2]` also work. No API key is needed.
- **Match slide content with Claude:** for an unlabelled script, configure `ANTHROPIC_API_KEY` and restart. Clicking **Match with Claude and preview** sends your full script, slide images, extracted text, and speaker notes to Anthropic; API charges may apply. Claude selects sentence/paragraph boundaries in slide order. The app copies the original wording instead of asking Claude to rewrite it. Labelled scripts are always split locally.

Review the matches before saving. Slides with no matched narration are flagged and must be filled in before applying. Imports support up to 120,000 characters total and 12,000 per slide. Changed scripts clear their narration and invalidate the previous video; unchanged scripts keep their audio. If the presentation changes after previewing, preview again before applying.

## Presentation import

- **PDF**: built-in rendering with PyMuPDF. Export to PDF from PowerPoint if you want the closest font/layout fidelity.
- **PPTX**: requires LibreOffice (`brew install --cask libreoffice` on macOS), or a configured `SOFFICE_PATH`. Text and speaker notes are extracted; LibreOffice renders the slides.
- **PNG/JPG/WebP**: select several images in slide order. Files are kept in upload order; name them `001`, `002`, etc. and select them in order.
- Maximum: 100 slides and 80 MB of total uploaded source files per operation. Expanded PPTX archives are limited to 300 MB.
- Static slide rendering does **not** preserve animations, transitions, embedded videos, or all custom fonts. A mismatch between PPTX source and rendered slide counts is rejected rather than silently attaching notes to the wrong slide.

## Audio, timing and export

Every slide has its own script and audio clip. The app measures actual decoded audio samples, not an estimate based on word count. Video segments run at 30 fps; slide durations round up to the next frame and include your chosen pause. Output is H.264/AAC MP4 at 1080p or 720p, with letterboxing rather than cropping. The `timings.json` download records slide starts, ends, actual narration durations, and scripts.

- Upload an existing recording for any slide if you don't want speech generation. The file is decoded locally and normalised to 48 kHz mono WAV.
- Repeating narration generation reuses identical script/voice/speed/model combinations. Uploaded recordings are preserved by the bulk generation action.
- Long scripts are split at sentence/word boundaries into at most 280-character requests to respect upstream's default 300-character limit. Every chunk uses the same voice reference. Normalised chunks are joined with 120 ms breathing gaps, then the selected speaking pace is applied with FFmpeg's pitch-preserving tempo filter. Timings are measured after these operations. Reference content changes invalidate the speech cache.
- Recoverable Indic-MIO generation errors (token limits, invalid speech tokens, or empty model audio) trigger bounded retries with smaller chunks. The original wording and order are retained. Invalid references and other request validation errors are reported without retrying; failures identify the slide and keep completed slides saved.
- Editing a script clears its audio and marks the previous video obsolete. After changing a script, regenerate or re-upload that slide's audio and render again.
- To change an uploaded recording into generated narration, use **Generate this slide's audio**.
- Changing voice, speed, or speech model takes effect when you click **Generate narration**, not retroactively. Listen to the regenerated audio before rendering.
- Jobs run in the background, with persistent progress and per-project edit locks. Refreshing the browser doesn't cancel processing. Restarting the server does interrupt jobs; completed slides are retained and you can retry.

## Privacy and operation

The app and bundled model server bind to loopback only. Files, voice samples, and downloaded model weights live in `data/`; keys live only in `.env` or server environment variables. These and both virtual environments are git-ignored. Local Indic-MIO keeps scripts and reference audio on your machine. A separately configured remote model server receives scripts and your selected voice sample, and Claude receives slide content for script generation. Provider policies govern remotely processed content. Voice samples are personal data: only upload recordings you own or are authorised to clone. Sample files are excluded from source control but are **not encrypted at rest**. Deleting a project folder removes its saved sample; the model process may retain up to four speaker embeddings in memory until shutdown.

This is a **single-user local MVP**, not a multi-user hosted service. Do not expose it with a public tunnel or bind to `0.0.0.0`. Run one Uvicorn worker: job locks are in-process. There is no login, durable queue, cancellation, or collaboration yet. To remove a project and its source/audio/video, stop the server and delete that project's folder under `data/`. Source uploads and unused older audio can consume disk space; review and clean up projects periodically.

FFmpeg is provided by the `imageio-ffmpeg` package; no separate installation is required. Override it with `FFMPEG_PATH` if needed. Set `SLIDEVOICE_DATA_DIR` to store projects elsewhere.

## Development and tests

```sh
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
node --check app/static/app.js
```

Tests use temporary project folders and mocked AI providers; no paid requests or model downloads. They cover the documented Indic-MIO protocol, reference-upload permissions, duration validation, chunking, cache invalidation, malformed model responses, and the bundled server API with an injected test engine. Media integration tests really render PDFs, decode audio, and create MP4s with FFmpeg. LibreOffice-specific tests skip if it is unavailable. Real neural inference is a separate smoke test requiring the optional model runtime and weights.

## Structure

- `app/main.py`: local API, background jobs, file access and request validation.
- `app/core.py`: persistent projects, locks, cache invalidation.
- `app/media.py`: PDF/PPTX/image import, audio normalisation, frame-exact timelines and video assembly.
- `app/script_import.py`: script splitting, boundary validation, and preview/apply support.
- `app/providers.py`: Claude and Indic-MIO adapters plus local macOS preview speech.
- `app/indic_server.py`: optional local Transformers + MioCodec runtime, compatible with the MioTTS `/v1/tts` protocol.
- `app/static/`: responsive, dependency-free browser studio.
- `tests/`: workflow, validation, caching, and real media integration tests.

Provider references: [Indic-MIO model card](https://huggingface.co/SPRINGLab/Indic-Mio), [MioTTS-Inference API](https://github.com/Aratako/MioTTS-Inference), [MioCodec](https://github.com/Aratako/MioCodec), [Claude Messages API](https://platform.claude.com/docs/en/api/http/messages). The optional MioCodec code dependency is pinned to a specific upstream revision in `requirements-indic.txt`. Indic-MIO weights use Apache-2.0 and MioCodec code uses MIT; respect the licences of all downloaded dependencies and any external voice preset.

## Support and contributions

For setup problems, start with the [run guide](README_RUN.md). Report reproducible bugs or propose improvements through [GitHub Issues](https://github.com/Sohampatil00/Slidevoice/issues). Include your operating system, Python version, reproduction steps, and redacted error output. Do not upload private decks, voice recordings, or API keys. See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

## Licensing and acknowledgements

No licence for SlideVoice's own source code has been selected yet. Public availability alone does not grant a general licence to use, modify, or redistribute it; contact the repository owner for permission beyond the rights provided by GitHub's terms. Third-party dependencies, model weights, codecs, and voice presets remain subject to their own licences. In particular, review PyMuPDF's AGPL/commercial terms before distributing an application that uses it. The model and codec licences described above do not apply to all of SlideVoice's dependencies.

Built with FastAPI, PyMuPDF, python-pptx, Pillow, FFmpeg, Indic-MIO, MioCodec, and optional Claude integration. See the requirements files for direct dependencies and the provider references above for upstream projects.
