"""PyInstaller entry point. Configure writable paths before importing the server."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.platform_paths import configure_desktop_environment

if __name__ == "__main__":
    paths = configure_desktop_environment()
    log_path = paths["data"] / "logs" / "desktop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = log_path.open("a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    if "--lux-bootstrap" in sys.argv:
        from app.lux_bootstrap import main

        raise SystemExit(main())
    elif "--prepare-lux-runtime" in sys.argv:
        import subprocess

        from app.lux_bootstrap import prepare_runtime

        python, worker = prepare_runtime()
        raise SystemExit(
            subprocess.call(
                [str(python), "-c", "from zipvoice.luxvoice import LuxTTS; import torch, soundfile"],
                cwd=worker,
            )
        )
    elif "--backend" in sys.argv:
        import uvicorn

        port = int(sys.argv[sys.argv.index("--port") + 1])
        uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_config=None)
    else:
        from app.desktop import main

        raise SystemExit(main(smoke="--smoke-test" in sys.argv))
