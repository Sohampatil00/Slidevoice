"""Native desktop window with an owned loopback backend and persistent storage."""

import html
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from filelock import FileLock, Timeout

from .platform_paths import bundled_resources, configure_desktop_environment
from .processes import background_options, stop_process_tree


def start_backend(paths):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = uuid.uuid4().hex
    environment = os.environ.copy()
    environment["SLIDEVOICE_INSTANCE_ID"] = token
    resources = bundled_resources()
    if resources:
        environment["FFMPEG_PATH"] = str(
            resources / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        )
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).resolve().parents[1] / "desktop" / "entry.py"))
    command.extend(["--backend", "--port", str(port)])
    log_path = paths["data"] / "logs" / "desktop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            **background_options(),
        )
    return process, f"http://127.0.0.1:{port}", token


def wait_backend(process, url, token, timeout=45):
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=1, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "SlideVoice could not start. See data/logs/desktop.log in the app data folder."
                )
            try:
                if client.get(url + "/api/desktop/identity").json().get("instance") == token:
                    return
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.15)
    raise RuntimeError("SlideVoice startup timed out. See the desktop log in the app data folder.")


def verify_desktop_backend(url):
    """Check user-visible features in the packaged artifact on each native CI runner."""
    with httpx.Client(base_url=url, timeout=10, trust_env=False) as client:
        page = client.get("/")
        page.raise_for_status()
        settings = client.get("/api/desktop/settings")
        settings.raise_for_status()
        script = client.get("/static/desktop.js")
        script.raise_for_status()
        icon = client.get("/static/branding/slidevoice.png")
        icon.raise_for_status()
        presentation = client.get("/static/presentation.js")
        presentation.raise_for_status()
    if (
        "present-slides" not in page.text
        or "branding/slidevoice.png" not in page.text
        or "chatterbox" in page.text.lower()
        or "claude" in script.text.lower()
        or settings.json().get("script_provider") != "gemini"
        or "anthropic_configured" in settings.json()
        or not icon.content.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise RuntimeError("The packaged desktop interface or branding is stale or incomplete.")


class DesktopControls:
    """Expose only window fullscreen control to the local desktop UI."""

    def __init__(self):
        self._window = None
        self._fullscreen = False

    def toggle_fullscreen(self):
        if self._window is None:
            return False
        self._window.toggle_fullscreen()
        self._fullscreen = not self._fullscreen
        return self._fullscreen


def main(smoke=False):
    paths = configure_desktop_environment()
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("org.slidevoice.desktop")
    lock = FileLock(paths["application"] / "desktop.lock")
    try:
        lock.acquire(timeout=0)
    except Timeout:
        if smoke:
            raise RuntimeError("SlideVoice is already running") from None
        import webview

        webview.create_window(
            "SlideVoice",
            html="<h2>SlideVoice is already running.</h2><p>Switch to its existing window.</p>",
            width=480,
            height=200,
        )
        webview.start()
        return 0
    process = None
    try:
        process, url, token = start_backend(paths)
        if smoke:
            wait_backend(process, url, token)
            verify_desktop_backend(url)
            print(
                "Packaged backend ready; identity, branding, settings and presentation mode verified.",
                flush=True,
            )
            return 0
        import webview

        webview.settings["ALLOW_DOWNLOADS"] = True
        # Open one initial URL. Navigating away from an unfinished HTML splash
        # can leave WKWebView's content view detached on the first launch.
        try:
            wait_backend(process, url, token)
            initial = {"url": url}
        except Exception as error:
            initial = {"html": "<h2>Unable to start SlideVoice</h2><p>" + html.escape(str(error)) + "</p>"}
        controls = DesktopControls()
        window = webview.create_window(
            "SlideVoice", width=1280, height=850, min_size=(900, 650), js_api=controls, **initial
        )
        controls._window = window
        # Cocoa's Quit command can terminate the interpreter without unwinding
        # finally blocks. The synchronous closing event also runs on Cmd+Q.
        window.events.closing += lambda: stop_process_tree(process)

        webview.start(
            gui="cocoa" if sys.platform == "darwin" else "edgechromium",
            private_mode=False,
            storage_path=str(paths["cache"] / "webview"),
            icon=str(Path(__file__).parent / "static/branding/slidevoice.ico")
            if sys.platform == "win32"
            else str(Path(__file__).parent / "static/branding/slidevoice.png"),
        )
        return 0
    finally:
        stop_process_tree(process)
        lock.release()
