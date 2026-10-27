import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path(os.getenv("SLIDEVOICE_CONFIG_FILE", str(ROOT / ".env")))
load_dotenv(CONFIG_FILE)
DATA = Path(os.getenv("SLIDEVOICE_DATA_DIR", str(ROOT / "data"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
MAX_SLIDES = 100
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
locks: dict[str, threading.Lock] = {}
registry_lock = threading.Lock()


class WorkflowError(Exception):
    pass


def now():
    return datetime.now(UTC).isoformat()


def project_dir(project_id):
    if not re.fullmatch(r"[a-f0-9]{32}", project_id):
        raise WorkflowError("Project not found.")
    folder = DATA / project_id
    if not folder.is_dir():
        raise WorkflowError("Project not found.")
    return folder


def project_lock(project_id):
    with registry_lock:
        return locks.setdefault(project_id, threading.Lock())


def save_project(project):
    project["updated_at"] = now()
    folder = project_dir(project["id"])
    temporary = folder / f".{uuid.uuid4().hex}.json"
    temporary.write_text(json.dumps(project, indent=2), encoding="utf-8")
    temporary.replace(folder / "project.json")


def read_project(project_id):
    try:
        return json.loads((project_dir(project_id) / "project.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise WorkflowError("Project not found.") from error


def new_project(title):
    project_id = uuid.uuid4().hex
    (DATA / project_id).mkdir()
    project = {
        "id": project_id,
        "title": title[:160] or "Untitled presentation",
        "created_at": now(),
        "updated_at": now(),
        "slides": [],
        "job": {"status": "idle", "message": "Ready to import slides", "progress": 0},
        "settings": {"pause": 0.5, "resolution": "1080p"},
        "export": None,
    }
    save_project(project)
    return project


def invalidate_export(project):
    project["export"] = None
    folder = project_dir(project["id"])
    for filename in ("video.mp4", "timings.json"):
        (folder / filename).unlink(missing_ok=True)


def find_slide(project, slide_id):
    for slide in project["slides"]:
        if slide["id"] == slide_id:
            return slide
    raise WorkflowError("Slide not found.")


def public_project(project):
    folder = project_dir(project["id"])
    result = json.loads(json.dumps(project))
    if reference := result.get("voice_reference"):
        reference["audio_url"] = f"/api/projects/{project['id']}/files/{reference['file']}"
    for slide in result["slides"]:
        base = f"/api/projects/{project['id']}/files/"
        slide["image_url"] = base + slide["image"]
        slide["audio_url"] = (
            base + slide["audio"] + f"?v={slide.get('audio_version', '')}" if slide.get("audio") else None
        )
        slide["audio_ready"] = bool(slide.get("audio") and (folder / slide["audio"]).is_file())
    if result["export"]:
        base = f"/api/projects/{project['id']}/files/"
        version = result["export"]["version"]
        result["export"]["video_url"] = base + f"video.mp4?v={version}"
        result["export"]["timings_url"] = base + f"timings.json?v={version}"
    return result
