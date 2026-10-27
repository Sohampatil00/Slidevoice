"""Install/run LuxTTS without a system Python or Git in packaged desktop builds."""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import core
from .platform_paths import bundled_resources, python_in_environment


def find_uv():
    resources = bundled_resources()
    name = "uv.exe" if sys.platform == "win32" else "uv"
    candidates = [
        resources / "bin" / name if resources else None,
        shutil.which("uv"),
        Path.home() / ".local" / "bin" / name,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError(
        "Install uv to prepare LuxTTS, or reinstall the desktop app containing its runtime manager."
    )


def runtime_inputs():
    resources = bundled_resources()
    root = resources if resources else core.ROOT
    requirements = root / "requirements-lux.txt"
    worker = root / "worker" if resources else core.ROOT
    runtime_base = os.getenv("SLIDEVOICE_RUNTIME_DIR")
    environment = Path(runtime_base) / "lux-venv" if runtime_base else core.ROOT / ".lux-venv"
    return requirements, worker, environment


def runtime_command(command, **options):
    # Windowed bundles have no console handles; send child diagnostics to the app log.
    if not options.get("capture_output"):
        options.setdefault("stdout", sys.stdout)
        options.setdefault("stderr", sys.stderr)
    return subprocess.run(command, **options)


def prepare_runtime(run=runtime_command):
    requirements, worker, environment = runtime_inputs()
    uv = find_uv()
    python = python_in_environment(environment)
    if not python.is_file():
        environment.parent.mkdir(parents=True, exist_ok=True)
        run([uv, "venv", "--python", "3.12", "--managed-python", str(environment)], check=True)
    fingerprint = hashlib.sha256(requirements.read_bytes())
    for wheel in sorted((requirements.parent / "wheels").glob("*.whl")):
        fingerprint.update(wheel.read_bytes())
    version = fingerprint.hexdigest()
    stamp = environment / ".slidevoice-runtime"
    current = stamp.read_text().strip() if stamp.is_file() else ""
    if current != version:
        # Reuse the optional environment already installed by the source launcher.
        installed = None
        if not bundled_resources() and not current:
            installed = run(
                [
                    str(python),
                    "-c",
                    "from zipvoice.luxvoice import LuxTTS; import uvicorn, fastapi, soundfile, dotenv",
                ],
                check=False,
                capture_output=True,
            )
        if installed is None or installed.returncode:
            command = [uv, "pip", "install", "--python", str(python), "-r", str(requirements)]
            if sys.platform == "win32":
                command.extend(["--torch-backend", "cpu"])
            run(command, cwd=requirements.parent, check=True)
        stamp.write_text(version)
    return python, worker


def main():
    python, worker = prepare_runtime()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(worker)
    port = int(environment.get("LUX_TTS_PORT", "8004"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid LuxTTS port")
    command = [str(python), "-m", "uvicorn", "app.lux_server:app", "--host", "127.0.0.1", "--port", str(port)]
    print("Starting the local LuxTTS worker.", flush=True)
    return subprocess.call(
        command, cwd=worker, env=environment, stdout=sys.stdout, stderr=sys.stderr
    )


if __name__ == "__main__":
    raise SystemExit(main())
