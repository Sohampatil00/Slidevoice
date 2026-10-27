# Desktop implementation plan

Initial targets: macOS Apple Silicon and Windows x64. Keep the existing browser workflow and saved projects intact. The desktop app runs locally, starts LuxTTS on demand, and requires no system Python, Git, or Terminal commands. Internet access is needed for first-use runtime/model downloads. PDF/images work immediately; PowerPoint support detects a separately installed LibreOffice.

## Milestones

1. **Portable foundation**
   - Platform-specific application data, configuration, cache, logs, and writable runtime directories.
   - Cross-platform LuxTTS bootstrap using bundled uv and managed Python 3.12.
   - Bundle pinned LuxTTS/LinaCodec source wheels so end users do not need Git.
   - Preserve the source-checkout launchers and existing data paths.
2. **Native desktop application**
   - Native WebView window: WKWebView on macOS and Edge WebView2 on Windows.
   - Isolated local backend, startup status, single-instance behavior, and owned-process cleanup.
   - Persistent user data outside the app installation; package no keys, models, or user recordings.
3. **Build artifacts**
   - PyInstaller application bundles, macOS DMG, Windows setup EXE and portable ZIP.
   - Native CI build/test jobs on each target platform; no cross-compilation claims.
   - Dependency/license inventory and reproducible pinned runtime inputs.
4. **Verification and release**
   - Unit/integration tests for bootstrap, platform paths, lifecycle, and packaged resource discovery.
   - Local packaged macOS backend and native-window smoke tests, including LuxTTS startup and narration.
   - Windows native tests and packaged backend smoke checks in Windows CI.
   - Signed public releases require Apple/Windows signing credentials and a chosen project license. Development builds remain explicitly unsigned. Do not publish private files or source changes automatically.

## Acceptance criteria

- Double-clicking the application opens SlideVoice without a terminal.
- A clean installation can create/edit a project, import PDF/images, generate narration with on-demand LuxTTS, and export video.
- Existing source-checkout projects are not moved or deleted; desktop projects use the OS application-data directory.
- Closing the app stops its own backend/model processes while leaving independently started services alone.
- First-use failures show a useful message and a persistent log location.
- Windows execution is not claimed verified until its native CI checks run.

## Progress

- [x] Existing application and packaging constraints inspected.
- [x] Portable foundation implemented and tested.
- [x] Native desktop shell implemented and tested on macOS.
- [x] macOS development artifact built locally; native window, sample project, and shutdown verified.
- [x] Windows installer workflow prepared; Windows dependency resolution checked from macOS.
- [x] macOS clean runtime installation and model synthesis verified; bundled FFmpeg rendered a three-slide MP4.
- [x] Windows 0.1.1 artifact built and installer lifecycle executed on native Windows CI.
- [ ] Public release license, signing, and publishing approved.


## Guided Windows setup (0.1.2)

The default installer task prepares WebView2, managed Python, LuxTTS dependencies, narration and transcription models, and a private LibreOffice renderer. Initial setup needs internet and several GB of disk space. The installer offers retry after a failed download; Settings > Prepare / repair components runs the same setup without reinstalling the app. Verified cached downloads and installed runtime packages are reused. Gemini remains optional and requires the user's own API key and internet for script generation.

Native CI runs full model preparation, then reloads the models with Hugging Face offline mode and converts a generated PPTX to PDF. Installer lifecycle tests select the dependency task and verify completion, reusing CI’s prepared component cache while keeping projects and configuration isolated. Models, runtime and rendering cache remain in per-user application storage alongside the data-preservation policy.
