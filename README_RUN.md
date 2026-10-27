# How to run SlideVoice on your Mac

For local voice cloning, SlideVoice needs **two services running at the same time**. Uploaded recordings and macOS preview speech only need the studio:

| Service                | What it does                                           | Command               | Address               |
| ---------------------- | ------------------------------------------------------ | --------------------- | --------------------- |
| SlideVoice studio      | Upload slides, edit scripts, sync audio, export videos | `./start.command`     | http://127.0.0.1:8765 |
| Indic-MIO voice server | Generate narration using your voice sample             | `./indic-mio.command` | http://127.0.0.1:8001 |

**Starting the studio alone does not start Indic-MIO. Keep both Terminal windows open.**

## Before you start

- Clone the repository first: `git clone https://github.com/Sohampatil00/Slidevoice.git`. Replace `/path/to/Slidevoice` below with the location of your cloned folder.
- The launchers require `uv` or Python 3.12 or newer. They create their Python environments and install packages if needed.
- Connect to the internet for dependency installation and model downloads. Allow several GB of free disk space for the voice runtime and model files.
- You do **not** need an Indic-MIO speech API key for the bundled local server.
- Gemini or Claude script generation is optional and needs its provider API key. You can paste scripts manually instead.

## 1. Start the main app

Open **Terminal**, paste these commands, and press Return:

```bash
cd "/path/to/Slidevoice"
./start.command
```

Wait for both of these messages:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8765
```

Keep this Terminal open. It runs the app; it is not stuck waiting for you to type another command.

## 2. Start Indic-MIO in a second Terminal tab

Press **Command + T** in Terminal to open a second tab, then run:

```bash
cd "/path/to/Slidevoice"
./indic-mio.command
```

The voice server loads **Indic-MIO** and **MioCodec**. On the first run, or if cached model weights are missing, it needs to download those files again. Loading can take time, depending on your connection and computer.

**Do not generate narration yet.** Wait for:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8001
```

Keep this second Terminal tab open too. Messages about installing packages or loading models are not the same as successful startup. If it prints `Application startup failed` or exits back to the command prompt, the voice server is not running.

## 3. Open the studio

Open this address in your browser:

**[http://127.0.0.1:8765](http://127.0.0.1:8765)**

The address ending in `8001` is the voice backend, not the presentation editor. A “Not Found” message at its root address does not by itself mean the model is broken; use its health-check address below.

In SlideVoice, open **Connections & setup**. **Indic-MIO server** should show **Ready** after the model finishes loading.

## 4. Make your first video

1. Click **New presentation** and upload a PPTX, PDF, or slide images. PDF is a good fallback if PPTX rendering is unavailable or changes fonts. PPTX import requires LibreOffice.
2. Click **Import full script** to paste the entire English narration and distribute it across the slides. With no API key, put `Slide 1`, `Slide 2`, etc. on separate lines before each section. With a configured Claude key, choose **Match slide content with Claude** for an unlabelled script. Review and edit the assignments, then click **Apply scripts to all slides**. You can also paste and save each slide's script individually.
3. Under **Narration source**, choose **Indic-MIO · local voice cloning**.
4. Under **Voice reference**, choose **My own voice sample**.
5. Confirm that you own the recording or have permission to clone and use the voice.
6. Upload **3–20 seconds** of clear English speech in your natural Indian accent. Use one speaker, no background music. This sample is the voice reference, not the full presentation narration.
7. Click **Generate this slide’s audio** to test one slide. Listen and check the pronunciation and voice similarity.
8. When satisfied, click **Generate narration** to process the deck. Every slide needs a saved script, unless you are keeping an uploaded narration recording for it.
9. Choose **1080p** or **720p** and the pause between slides. Once every slide has audio, click **Create video**.
10. When rendering finishes, click **Download MP4**. You can also download **Slide timestamps**.

The app measures each audio clip and sets its slide duration automatically. You do not need to calculate timestamps or align slides in a separate video editor.

Voice similarity and accent depend on the reference recording and model output. Audition before generating a whole presentation. Static slide images do not preserve PowerPoint animations or embedded videos.

### Example prompt for a complete narration script

Use this with a script-writing tool after supplying your presentation. Adjust the desired length to suit your audience:

```text
Write a spoken narration script for every slide in this presentation, in the exact slide order. Use clear, conversational English suitable for an Indian audience. Aim for about 90–120 seconds per slide.

Format each section with only "Slide 1", "Slide 2", etc. on its own line, followed by the narration. Include every slide exactly once. Do not add slide titles beside the numbered headings, introductory commentary, stage directions, or a summary outside the slide sections. Return plain text.
```

## Optional: generate scripts inside the app

The main launcher creates `.env` from `.env.example` if `.env` does not already exist. Open your existing `.env` in a text editor and set:

```dotenv
GEMINI_API_KEY=your_actual_api_key
SCRIPT_PROVIDER=gemini
```

Do not overwrite an existing `.env` just to add this key. Do not put your key in screenshots, source control, or chat messages.

Stop and restart **the studio** after editing `.env`. You can then use **Write with Gemini** or **Generate scripts for all slides**. You can also use Claude by configuring its key and selecting it with `SCRIPT_PROVIDER`. API generation sends slide content to the selected provider and may incur charges; local Indic-MIO narration does not need a speech API subscription.

## If you see “Indic-MIO is not reachable or timed out”

1. Check the **second Terminal tab**, where `indic-mio.command` runs.
2. If it is not running, start it using Step 2.
3. If it is downloading or loading models, wait for **Application startup complete** before retrying narration.
4. If model files are missing or incomplete, keep the internet connected and use the normal startup command. Do not force offline mode while model files are missing.
5. If startup fails, copy the final error from that Terminal. The browser's “not reachable” message alone does not identify the underlying problem.

To check the voice server from a **third Terminal tab**, run:

```bash
curl --max-time 5 http://127.0.0.1:8001/health
```

After successful startup, expect a JSON response containing:

```json
{"status":"ok","model":"SPRINGLab/Indic-Mio"}
```

To check the studio:

```bash
curl --max-time 5 http://127.0.0.1:8765/api/health
```

`"indic_mio": true` means the studio can reach the voice server. `"claude": false` means Claude API generation is not configured; you can still paste scripts manually.

### Other common problems

| Problem | What to do |
| --- | --- |
| `Permission denied` when running a launcher | In the project folder, run `chmod +x start.command indic-mio.command`, then retry. |
| Python version error | The system Python may be too old. Use `uv`, or run the launcher with an installed Python 3.12+ executable, for example `PYTHON=python3.12 ./start.command`. |
| `Address already in use` | A service may already be running. Check its health endpoint before starting a duplicate. Stop the existing service with Ctrl+C in its Terminal when needed. |
| MPS/device-related inference error | Set `INDIC_MIO_DEVICE=cpu` in `.env`, then restart the voice server. CPU inference can be slower. |
| PPTX conversion error | Export the presentation to PDF in PowerPoint and upload the PDF instead. |
| `Create video` is disabled | Finish generating or uploading audio for every slide first. |
| Editing a script removes its narration | This is intentional: regenerate or re-upload that slide's audio, then render again. |
| Browser works but narration fails | The studio and voice server are separate; a working editor does not prove the model server is ready. |
| Some `/v1/tts` requests return `422` | Known model-generation failures are retried automatically with shorter chunks. If the job still fails, the studio identifies the slide and explains the error. Shorten its sentences or use another clean 3–20 second voice sample, then retry. Completed slides are kept. |

## Stop and restart

- To stop the studio, press **Control + C** in its Terminal tab.
- To stop Indic-MIO and release its model memory, press **Control + C** in the voice-server tab.
- To use the app again after a restart, repeat Steps 1 and 2, then open the studio in your browser.
- Closing the browser does not stop the servers. Closing their Terminal tabs can stop them.

Projects, uploaded recordings, and generated media are saved under `data/` in the project folder. Model files are cached under `data/models/huggingface/`. **Do not delete the whole `data/` folder to troubleshoot a model download**, because it also contains your presentations and voice recordings.

For architecture, configuration, privacy details, and development tests, see [README.md](README.md).

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
