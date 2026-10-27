"""Start the optional LuxTTS worker on demand and own its normal shutdown."""

import os
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from . import core, processes, providers
from .core import WorkflowError


def lux_autostart_enabled():
    return os.getenv("LUX_TTS_AUTOSTART", "1").strip().lower() not in {"0", "false", "no", "off"}


def local_lux_address():
    parsed = urlsplit(providers.speech_base_url("lux_tts"))
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.path not in {"", "/"}
    ):
        return None
    return parsed.hostname, parsed.port or 80


def lux_can_autostart():
    try:
        return lux_autostart_enabled() and local_lux_address() is not None
    except (ValueError, WorkflowError):
        return False


class LuxRuntime:
    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._stopping = threading.Event()

    def ensure_ready(self, progress=lambda message: None, timeout=900):
        if not lux_autostart_enabled():
            return  # Explicit manual mode retains the existing provider behavior.
        with self._lock:
            if self._stopping.is_set():
                raise WorkflowError("The studio is shutting down. Restart it before generating narration.")
            try:
                address = local_lux_address()
            except ValueError as error:
                raise WorkflowError("LUX_TTS_BASE_URL must contain a valid server port.") from error
            if providers.speech_status("lux_tts"):
                return  # A separately started server is reused, never owned or stopped.
            if not address:
                raise WorkflowError(
                    "The configured LuxTTS server is unavailable. Automatic startup supports a local HTTP server only."
                )
            if self._process is None or self._process.poll() is not None:
                try:
                    with socket.create_connection(address, timeout=0.5):
                        raise WorkflowError(
                            "The LuxTTS port is occupied but its service is not ready. Wait for it to load, or check LUX_TTS_BASE_URL."
                        )
                except OSError:
                    pass
                progress("Preparing LuxTTS automatically. First use installs its runtime and model weights…")
                log_path = core.DATA / "logs" / "lux.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                environment = os.environ.copy()
                environment["LUX_TTS_PORT"] = str(address[1])
                environment["HF_HOME"] = os.getenv("HF_HOME", str(core.DATA / "models" / "huggingface"))
                environment["SLIDEVOICE_DATA_DIR"] = str(core.DATA)
                try:
                    with log_path.open("ab") as log:
                        self._process = subprocess.Popen(
                            [sys.executable, "--lux-bootstrap"]
                            if getattr(sys, "frozen", False)
                            else [sys.executable, "-m", "app.lux_bootstrap"],
                            cwd=core.ROOT,
                            env=environment,
                            stdin=subprocess.DEVNULL,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            **processes.background_options(),
                        )
                except OSError as error:
                    raise WorkflowError(
                        "LuxTTS could not start. Check the optional runtime installation."
                    ) from error
            progress("Loading LuxTTS. The first launch may take several minutes; your slides are saved…")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not self._stopping.is_set():
                if self._process.poll() is not None:
                    raise WorkflowError(
                        "LuxTTS could not finish starting. Check data/logs/lux.log, then retry. "
                        "First setup requires Python 3.12 or uv and internet access."
                    )
                if providers.speech_status("lux_tts"):
                    return
                self._stopping.wait(0.5)
            self._stop_owned_process()
            raise WorkflowError(
                "LuxTTS startup was stopped or timed out. Check data/logs/lux.log and retry. Completed slides are saved."
            )

    def _stop_owned_process(self):
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        processes.stop_process_tree(process)

    def stop(self):
        self._stopping.set()  # Interrupt startup before acquiring the startup lock.
        with self._lock:
            self._stop_owned_process()
