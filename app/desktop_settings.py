"""Desktop-only configuration; API keys are saved locally and never returned."""

import os
import threading
from pathlib import Path

from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import core

router = APIRouter()
_lock = threading.Lock()


class DesktopSettings(BaseModel):
    gemini_key: str | None = Field(default=None, max_length=512)
    model_config = {"extra": "forbid"}


def require_desktop():
    if os.getenv("SLIDEVOICE_DESKTOP") != "1":
        raise HTTPException(status_code=404)


@router.get("/api/desktop/settings")
def read_settings():
    require_desktop()
    return {
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "script_provider": "gemini",
        "data_directory": str(core.DATA),
    }


def save_settings(settings: DesktopSettings, *, extra_updates=None):
    require_desktop()
    updates = {"SCRIPT_PROVIDER": "gemini", **(extra_updates or {})}
    if settings.gemini_key is not None:
        value = settings.gemini_key
        if any(ord(character) < 32 or character in "'\\" for character in value):
            raise HTTPException(status_code=400, detail="The API key contains invalid characters.")
        updates["GEMINI_API_KEY"] = value.strip()
    with _lock:
        values = dict(dotenv_values(core.CONFIG_FILE)) if core.CONFIG_FILE.exists() else {}
        values.update(updates)
        temporary = Path(str(core.CONFIG_FILE) + ".tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8") as output:
            os.chmod(temporary, 0o600)
            for key, value in values.items():
                escaped = str(value or "").replace("\\", "\\\\").replace("'", "\\'")
                output.write(f"{key}='{escaped}'\n")
        temporary.replace(core.CONFIG_FILE)
        os.environ.update(updates)
    return read_settings()


@router.put("/api/desktop/settings")
def update_settings(settings: DesktopSettings):
    return save_settings(settings)


@router.get("/api/desktop/setup")
def setup_status():
    require_desktop()
    from .desktop_setup import read_status

    return read_status()


@router.post("/api/desktop/setup")
def start_setup():
    require_desktop()
    import subprocess
    import sys

    from filelock import FileLock, Timeout

    from .desktop_setup import report
    from .processes import background_options

    # The installer and Settings share a lock and the same persistent status file.
    with _lock:
        lock = FileLock(core.DATA / "setup.lock")
        try:
            with lock.acquire(timeout=0):
                process = getattr(start_setup, "process", None)
                if process is not None and process.poll() is None:
                    return setup_status()
                report("running", "Starting dependency setup…")
                log = core.DATA / "logs" / "desktop.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("ab") as output:
                    command = (
                        [sys.executable, "--install-dependencies"]
                        if getattr(sys, "frozen", False)
                        else [sys.executable, str(core.ROOT / "desktop/entry.py"), "--install-dependencies"]
                    )
                    start_setup.process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        **background_options(),
                    )
        except Timeout:
            pass
    return setup_status()
