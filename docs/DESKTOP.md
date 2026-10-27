# SlideVoice desktop

Development targets: macOS Apple Silicon (arm64) and Windows 10/11 x64.
The native window uses WKWebView on Mac and Microsoft WebView2 on Windows.

## Use the app

On Mac, open `SlideVoice-macOS-arm64.dmg`, drag SlideVoice to Applications, and open it.
This development build is ad-hoc signed, not Apple notarized. Public distribution needs Developer ID signing and notarization; a downloaded development build can be blocked by Gatekeeper.

On Windows, the native build produces `SlideVoice-Windows-x64-Setup.exe` and a portable ZIP.
The installer creates a Start menu entry and installs Microsoft's WebView2 runtime if absent (internet required). Portable users must already have WebView2 installed.
Windows binaries must be built and tested by the Windows workflow before they are offered to users.
Unsigned Windows binaries may trigger SmartScreen.

Open **Connections & setup** to save an optional Gemini API key.
Keys are stored in the local app configuration and are never returned by the settings API.
The configuration file is plaintext; macOS uses owner-only file permissions and Windows uses the user's app-data directory permissions. OS keychain integration is not implemented.
No key is required to paste scripts or use local narration.

Select LuxTTS, upload a permitted voice sample, and generate narration.
The first generation installs managed Python and pinned model dependencies, then downloads model weights.
Allow several minutes and several GB of disk space. Later launches reuse the cache.
CPU narration on Windows can be slower than Mac MPS or a dedicated GPU; the initial Windows runtime uses CPU PyTorch.
The app automatically starts its model worker and stops owned processes on normal exit.
Independent model servers are reused and left running. Closing during a job stops processing;
completed slides remain saved and interrupted jobs can be retried after reopening.

FFmpeg is bundled. Install LibreOffice separately for PPTX rendering, or import PDF/images.
The app detects LibreOffice in standard Mac and Windows installation locations.
The desktop interface uses LuxTTS for voice cloning and offers a Mac preview voice. Legacy provider adapters remain available to source integrations.

## Persistent storage

| Platform | Projects, recordings, logs, configuration | Models and runtime cache |
| --- | --- | --- |
| macOS | `~/Library/Application Support/SlideVoice/` | `~/Library/Caches/SlideVoice/` |
| Windows | `%LOCALAPPDATA%/SlideVoice/` | `%LOCALAPPDATA%/SlideVoice/Cache/` |

The app does not import a source checkout's `.env`, keys, or projects. Existing source projects remain in that checkout's `data/` directory. Project migration is not implemented.
Reinstalling or uninstalling the application preserves these user directories.
Startup and model logs are in `data/logs/desktop.log` and `data/logs/lux.log` respectively.

## Developer builds

Use Python 3.12 on the target OS. From the repository root:

```sh
python -m venv .desktop-venv
# Mac
.desktop-venv/bin/python -m pip install -r requirements-build.txt
.desktop-venv/bin/python scripts/build_desktop.py
# Windows PowerShell
.desktop-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.desktop-venv\Scripts\python.exe scripts\build_desktop.py
```

The Windows build automatically compiles the installer with Inno Setup 6, found on PATH
or in its standard Program Files location. The same build generates the portable ZIP.
Build-time Git is needed to create wheels from the pinned upstream LuxTTS/LinaCodec commits;
end users receive the wheels and do not need Git or Python installed.
The build resolves the runtime dependencies to an OS-specific lockfile before packaging.
PyInstaller outputs are under `dist/`. Run the packaged executable with `--smoke-test`
to start its backend, verify an instance nonce, and shut it down without opening a window.
`--prepare-lux-runtime` installs and imports the optional runtime without downloading weights.

Local verification: Automated regression tests passed. The macOS native window, a sample project,
native MP4 save dialog, backend shutdown, clean runtime installation, model loading on MPS, and a valid generated
narration clip were checked. The packaged backend also imported audio, rendered a three-slide
720p MP4 with bundled FFmpeg, and served the resulting video. The first short narration took about 23 seconds including voice
conditioning; this is not a throughput benchmark. Windows dependency resolution passed;
Windows execution remains unverified.

Run **Desktop builds** from GitHub Actions after the implementation has been committed and pushed.
The workflow builds on native macOS arm64 and Windows x64 runners and uploads development artifacts.
It tests the packaged backend on both and installs/imports LuxTTS on Windows.
It does not publish a release. No workflow has been dispatched as part of local implementation.

## Release gates

- Execute the Windows build and test the native window, upload/download dialogs, narration and video export on Windows hardware.
- Complete end-to-end clean-install checks, including interrupted downloads, slow connections and restart during narration.
- Choose a license for SlideVoice before presenting it as open source. No root project license is currently present.
- Review upstream licenses for app dependencies, FFmpeg, model weights and transcription models.
  The build bundles available dependency license files and an installed dependency inventory;
  these are an inventory, not a legal clearance of the complete distribution.
- Add Apple Developer ID signing/notarization and Windows Authenticode signing for public installers.
- Add an installer icon, version policy, update mechanism and supported-hardware guidance before a polished public launch.

Architecture: the desktop executable starts a private loopback backend on a random port,
verifies its per-instance nonce, and opens the native WebView. The backend launches the same
executable in bootstrap mode, which uses bundled uv to prepare a separate managed Python
runtime and starts the pinned LuxTTS worker. Credentials, projects, model caches and recordings
are never copied from the build machine into the installer.

## Presentation mode

Select a presentation and click **Present**. Slides fill the app window; use Previous/Next,
Left/Right arrows, Page Up/Page Down, or Home/End to move. **Play narration** (or Space)
plays existing slide audio and advances after each clip with the selected pause. Slides with
no audio work manually. Escape or **Exit presentation** returns to the editor. **Full screen**
uses the native desktop window control in the app and the browser API on the website.
Starting a presentation saves pending script edits; leaving it stops playback.

## Shared branding and Windows parity

Version 0.1.1 uses one SlideVoice icon master in `app/static/branding/slidevoice.png`.
`scripts/build_icons.py` exports the macOS ICNS, Windows multi-size ICO, and favicon.
Both native builds include the same studio, Gemini-only key settings, LuxTTS narration,
presentation mode, and native fullscreen bridge. The Windows executable, installer,
uninstaller, Start menu and desktop shortcuts use the branded icon and a matching app ID.
EXE metadata and the Mac bundle version come from `pyproject.toml`.

The packaged `--smoke-test` verifies the actual bundled icon, settings and presentation assets,
not only server startup. Native Windows CI also installs/imports the LuxTTS CPU runtime.
Windows binaries cannot be built or executed on this Mac; the Windows workflow must finish
before distributing its EXE and ZIP. No Windows artifact is claimed tested locally.

## Windows installer validation

`pwsh -File scripts/test_windows_installer.ps1` installs the generated EXE in a temporary
folder whose name includes spaces. It checks executable metadata and branding, runs the
installed backend smoke test, reinstalls as an upgrade, and uninstalls. A marker in an isolated
user-data directory must survive both upgrade and uninstall. The test restores LOCALAPPDATA
and removes only its own temporary sandbox. Logs are saved under
`.desktop-build/windows-installer-test/` and uploaded by the desktop workflow on failure.

The `codex/windows-installer` branch triggers native desktop CI when pushed. The local
PowerShell parser can check syntax on Mac, but only a successful Windows run verifies the
installer. Publishing a branch to the public repository requires permission to publish its source.
