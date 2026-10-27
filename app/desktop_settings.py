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


@router.put("/api/desktop/settings")
def save_settings(settings: DesktopSettings):
    require_desktop()
    updates = {"SCRIPT_PROVIDER": "gemini"}
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
