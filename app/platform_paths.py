"""Writable desktop paths, separate from a source checkout or installed bundle."""

import os
import sys
from pathlib import Path


def desktop_directories(platform=None, home=None, environment=None):
    platform = platform or sys.platform
    home = Path(home or Path.home())
    environment = os.environ if environment is None else environment
    if platform == "darwin":
        application = home / "Library" / "Application Support" / "SlideVoice"
        cache = home / "Library" / "Caches" / "SlideVoice"
    elif platform == "win32":
        application = Path(environment.get("LOCALAPPDATA", home / "AppData" / "Local")) / "SlideVoice"
        cache = application / "Cache"
    else:
        application = Path(environment.get("XDG_DATA_HOME", home / ".local" / "share")) / "slidevoice"
        cache = Path(environment.get("XDG_CACHE_HOME", home / ".cache")) / "slidevoice"
    return {
        "application": application,
        "data": application / "data",
        "cache": cache,
        "config": application / ".env",
    }


def configure_desktop_environment():
    paths = desktop_directories()
    for key in ("application", "data", "cache"):
        paths[key].mkdir(parents=True, exist_ok=True)
    # Desktop storage must never fall back to a bundled, read-only data directory.
    os.environ["SLIDEVOICE_DESKTOP"] = "1"
    os.environ["SLIDEVOICE_CONFIG_FILE"] = str(paths["config"])
    os.environ["SLIDEVOICE_DATA_DIR"] = str(paths["data"])
    os.environ["SLIDEVOICE_RUNTIME_DIR"] = str(paths["cache"] / "runtimes")
    os.environ["UV_CACHE_DIR"] = str(paths["cache"] / "uv")
    os.environ["UV_PYTHON_INSTALL_DIR"] = str(paths["cache"] / "python")
    os.environ["HF_HOME"] = str(paths["cache"] / "huggingface")
    return paths


def bundled_resources():
    if value := os.getenv("SLIDEVOICE_RESOURCE_DIR"):
        return Path(value)
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "desktop_resources"
    return None


def python_in_environment(folder, platform=None):
    return Path(folder) / ("Scripts/python.exe" if (platform or sys.platform) == "win32" else "bin/python")
