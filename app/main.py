import json
import logging
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import core, media, providers, script_import
from .core import WorkflowError

logger = logging.getLogger("slidevoice")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(application):
    for path in core.DATA.glob("*/project.json"):
        try:
            project = json.loads(path.read_text())
            if project["job"]["status"] == "running":
                project["job"] = {
                    "status": "failed",
                    "message": "The app restarted. Completed slides are saved; retry the operation to continue.",
                    "progress": 0,
                }
                core.save_project(project)
        except (OSError, ValueError, KeyError):
            continue
    yield


app = FastAPI(title="SlideVoice", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return JSONResponse({"detail": "SlideVoice is a local-only application."}, status_code=403)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("x-slidevoice") != "local":
            return JSONResponse({"detail": "Missing local request header."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(WorkflowError)
async def workflow_error(request, error):
    return JSONResponse({"detail": str(error)}, status_code=400)


@app.exception_handler(httpx.HTTPError)
async def network_error(request, error):
    return JSONResponse(
        {"detail": "Could not reach the AI provider. Check your connection and retry."}, status_code=502
    )


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {
        "claude": bool(os.getenv("ANTHROPIC_API_KEY")),
        "indic_mio": providers.indic_status(),
        "preview": bool(shutil.which("say")),
        "pptx": bool(media.soffice()),
        "default_voice_id": os.getenv("INDIC_MIO_PRESET_ID", ""),
        "indic_model": os.getenv("INDIC_MIO_MODEL", "SPRINGLab/Indic-Mio"),
        "preview_voice": os.getenv("MACOS_PREVIEW_VOICE", "Aman"),
    }


@app.get("/api/voices")
def voices():
    return providers.available_voices()


@app.get("/api/projects")
def projects():
    results = []
    for source in core.DATA.glob("*/project.json"):
        try:
            project = json.loads(source.read_text())
            results.append({key: project[key] for key in ("id", "title", "updated_at", "job")})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(results, key=lambda entry: entry["updated_at"], reverse=True)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return core.public_project(core.read_project(project_id))


def lock_for_edit(project_id):
    core.project_dir(project_id)
    lock = core.project_lock(project_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "A job is running. Wait for it to finish before editing.")
    return lock


def queue_job(project_id, tasks, operation):
    lock = lock_for_edit(project_id)
    try:
        project = core.read_project(project_id)
        project["job"] = {"status": "running", "message": "Starting…", "progress": 0}
        core.save_project(project)
    except Exception:
        lock.release()
        raise

    def execute():
        def progress(fraction, message):
            project["job"].update(progress=round(fraction * 100), message=message)
            core.save_project(project)

        try:
            operation(project, progress)
            project["job"] = {
                "status": "complete",
                "message": "All done. Your work is saved.",
                "progress": 100,
            }
        except WorkflowError as error:
            project["job"] = {"status": "failed", "message": str(error), "progress": 0}
        except httpx.HTTPError:
            project["job"] = {
                "status": "failed",
                "message": "Could not reach the AI provider. Completed slides are saved; retry to continue.",
                "progress": 0,
            }
        except Exception as error:
            logger.error("Job failed (%s)", type(error).__name__)
            project["job"] = {
                "status": "failed",
                "message": "Processing failed. Check your source file and settings, then retry. Completed slides are saved.",
                "progress": 0,
            }
        finally:
            try:
                core.save_project(project)
            finally:
                lock.release()

    tasks.add_task(execute)
    return core.public_project(project)


async def save_upload(upload, destination, remaining):
    written = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            written += len(chunk)
            if written > remaining:
                raise WorkflowError("Uploads are limited to 80 MB in total per operation.")
            output.write(chunk)
    await upload.close()
    if not written:
        raise WorkflowError("The uploaded file is empty.")
    return written


@app.post("/api/projects")
async def create_project(tasks: BackgroundTasks, files: Annotated[list[UploadFile], File()]):
    if not 1 <= len(files) <= core.MAX_SLIDES:
        raise WorkflowError("Upload one presentation, or up to 100 images.")
    suffixes = [Path(upload.filename or "").suffix.lower() for upload in files]
    document = len(files) == 1 and suffixes[0] in {".pdf", ".pptx"}
    if not document and not all(suffix in {".png", ".jpg", ".jpeg", ".webp"} for suffix in suffixes):
        raise WorkflowError("Upload one PPTX/PDF, or a set of PNG/JPG/WebP slide images.")
    title = Path(files[0].filename or "Presentation").stem if document else "My presentation"
    project = core.new_project(title)
    folder = core.project_dir(project["id"])
    sources = []
    try:
        remaining = core.MAX_UPLOAD_BYTES
        for position, (upload, suffix) in enumerate(zip(files, suffixes, strict=True), 1):
            target = folder / f"source-{position:03}{suffix}"
            title = Path(upload.filename or f"Slide {position}").stem
            remaining -= await save_upload(upload, target, remaining)
            sources.append((target, title))
    except Exception:
        shutil.rmtree(folder)
        raise

    def operation(current, progress):
        progress(0.1, "Converting presentation into slide images…")
        if document:
            current["slides"] = media.import_document(sources[0][0], folder)
        else:
            current["slides"] = [
                media.import_image(source, folder, index, title)
                for index, (source, title) in enumerate(sources, 1)
            ]

    return queue_job(project["id"], tasks, operation)


@app.post("/api/demo")
def create_demo():
    project = core.new_project("A little less busywork")
    project["slides"] = media.demo_slides(core.project_dir(project["id"]))
    project["job"] = {
        "status": "idle",
        "message": "Demo slides and scripts are ready. Generate preview narration next.",
        "progress": 0,
    }
    core.save_project(project)
    return core.public_project(project)


class SlideEdit(BaseModel):
    script: str = Field(max_length=12000)
    title: str = Field(min_length=1, max_length=160)


@app.patch("/api/projects/{project_id}/slides/{slide_id}")
def edit_slide(project_id: str, slide_id: str, body: SlideEdit):
    lock = lock_for_edit(project_id)
    try:
        project = core.read_project(project_id)
        slide = core.find_slide(project, slide_id)
        if slide["script"] != body.script.strip():
            slide.update(
                script=body.script.strip(), audio=None, duration=None, audio_signature=None, audio_source=None
            )
        slide["title"] = body.title.strip() or f"Slide {slide['number']}"
        core.invalidate_export(project)
        core.save_project(project)
        return core.public_project(project)
    finally:
        lock.release()


class ScriptRequest(BaseModel):
    slide_ids: list[str] | None = Field(default=None, max_length=100)
    instructions: str = Field(
        default="Explain clearly in English. Use examples only when supported by the slide.", max_length=2000
    )


@app.post("/api/projects/{project_id}/scripts")
def scripts(project_id: str, body: ScriptRequest, tasks: BackgroundTasks):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise WorkflowError("Add ANTHROPIC_API_KEY to .env and restart, or paste your own narration.")

    def operation(project, progress):
        selected = (
            [core.find_slide(project, slide_id) for slide_id in dict.fromkeys(body.slide_ids)]
            if body.slide_ids
            else [slide for slide in project["slides"] if not slide["script"]]
        )
        titles = [slide["title"] for slide in project["slides"]]
        for index, slide in enumerate(selected):
            progress(index / len(selected), f"Claude is explaining slide {slide['number']}…")
            script = providers.generate_script(slide, core.project_dir(project_id), titles, body.instructions)
            slide.update(script=script, audio=None, duration=None, audio_signature=None, audio_source=None)
            core.invalidate_export(project)
            core.save_project(project)

    return queue_job(project_id, tasks, operation)


class FullScriptRequest(BaseModel):
    script: str = Field(min_length=1, max_length=script_import.MAX_FULL_SCRIPT_LENGTH)
    method: Literal["headings", "claude"] = "headings"


@app.post("/api/projects/{project_id}/scripts/preview")
def preview_full_script(project_id: str, body: FullScriptRequest):
    lock = lock_for_edit(project_id)
    try:
        project = core.read_project(project_id)
    finally:
        lock.release()
    if not project["slides"]:
        raise WorkflowError("Import slides first.")
    script = body.script.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not script:
        raise WorkflowError("Paste your full narration script first.")
    sections = script_import.labelled_scripts(script, project["slides"])
    method = "headings"
    if sections is None:
        if len(project["slides"]) == 1:
            sections = [script]
        elif body.method == "claude":
            sections = providers.distribute_script(
                script_import.script_units(script), project["slides"], core.project_dir(project_id)
            )
            method = "claude"
        else:
            raise WorkflowError(
                "Add standalone Slide 1, Slide 2 headings before each section, "
                "or choose Match slide content with Claude for an unlabelled script."
            )
    script_import.validate_sections(sections, len(project["slides"]))
    return {
        "revision": project["updated_at"],
        "method": method,
        "slides": [
            {"id": slide["id"], "number": slide["number"], "title": slide["title"], "script": section}
            for slide, section in zip(project["slides"], sections, strict=True)
        ],
    }


class ScriptAssignment(BaseModel):
    id: str = Field(max_length=80)
    script: str = Field(min_length=1, max_length=script_import.MAX_SCRIPT_LENGTH)


class ApplyFullScriptRequest(BaseModel):
    revision: str = Field(max_length=80)
    slides: list[ScriptAssignment] = Field(min_length=1, max_length=100)


@app.post("/api/projects/{project_id}/scripts/apply")
def apply_full_script(project_id: str, body: ApplyFullScriptRequest):
    lock = lock_for_edit(project_id)
    try:
        project = core.read_project(project_id)
        if project["updated_at"] != body.revision:
            raise HTTPException(
                409, "This presentation changed after the preview. Preview the full script again."
            )
        if [entry.id for entry in body.slides] != [slide["id"] for slide in project["slides"]]:
            raise WorkflowError("Provide exactly one script for each slide, in presentation order.")
        if any(not entry.script.strip() for entry in body.slides):
            raise WorkflowError("Fill in every slide's script before applying. You can edit the preview.")
        changed = False
        for slide, entry in zip(project["slides"], body.slides, strict=True):
            if slide["script"] != entry.script.strip():
                slide.update(
                    script=entry.script.strip(),
                    audio=None,
                    duration=None,
                    audio_signature=None,
                    audio_source=None,
                )
                changed = True
        if changed:
            core.invalidate_export(project)
            core.save_project(project)
        return core.public_project(project)
    finally:
        lock.release()


class AudioRequest(BaseModel):
    provider: str = Field(default="indic_mio", pattern="^(indic_mio|preview)$")
    voice_id: str = Field(default="", max_length=120, pattern=r"^[a-zA-Z0-9_-]*$")
    speed: float = Field(default=1, ge=0.7, le=1.2, allow_inf_nan=False)
    consent: bool = False
    use_reference: bool = True
    slide_ids: list[str] | None = Field(default=None, max_length=100)


@app.post("/api/projects/{project_id}/audio")
def audio(project_id: str, body: AudioRequest, tasks: BackgroundTasks):
    voice_id = body.voice_id or os.getenv("INDIC_MIO_PRESET_ID", "")
    if body.provider == "indic_mio":
        if not body.consent:
            raise WorkflowError("Confirm you own this voice or have permission to use it.")
    elif not shutil.which("say"):
        raise WorkflowError("Free preview requires macOS. Use Indic-MIO or upload your own audio.")

    def operation(project, progress):
        selected = (
            [core.find_slide(project, slide_id) for slide_id in dict.fromkeys(body.slide_ids)]
            if body.slide_ids
            else project["slides"]
        )
        if not selected:
            raise WorkflowError("Import slides first.")
        folder = core.project_dir(project_id)
        reference = (
            project.get("voice_reference") if body.provider == "indic_mio" and body.use_reference else None
        )
        reference_audio = folder / reference["file"] if reference else None
        if body.provider == "indic_mio" and body.use_reference and not reference_audio:
            raise WorkflowError(
                "Upload a 3–20 second voice sample first, or switch Voice reference to a server preset."
            )
        if body.provider == "indic_mio" and not reference_audio and not voice_id:
            raise WorkflowError(
                "Upload a 3–20 second voice sample or choose an Indic-MIO server preset first."
            )
        for slide in selected:
            if not body.slide_ids and slide.get("audio_source") == "uploaded":
                continue
            if not slide["script"].strip():
                raise WorkflowError(f"Write or generate the script for slide {slide['number']} first.")
        for index, slide in enumerate(selected):
            progress(index / len(selected), f"Creating narration for slide {slide['number']}…")
            effective_voice = (
                voice_id if body.provider == "indic_mio" else os.getenv("MACOS_PREVIEW_VOICE", "Aman")
            )
            signature = providers.audio_signature(
                slide["script"], body.provider, effective_voice, body.speed, reference_audio=reference_audio
            )
            if not body.slide_ids and slide.get("audio_source") == "uploaded":
                continue
            if (
                slide.get("audio_signature") == signature
                and slide.get("audio")
                and (folder / slide["audio"]).is_file()
            ):
                continue
            filename = f"{slide['id']}-{uuid.uuid4().hex[:12]}.wav"
            try:
                duration = providers.synthesize(
                    slide["script"],
                    folder / filename,
                    body.provider,
                    voice_id,
                    body.speed,
                    reference_audio=reference_audio,
                )
            except WorkflowError as error:
                raise WorkflowError(f"Slide {slide['number']}: {error}") from error
            old_audio = slide.get("audio")
            core.invalidate_export(project)
            slide.update(
                audio=filename,
                duration=duration,
                audio_signature=signature,
                audio_source=body.provider,
                audio_version=uuid.uuid4().hex,
            )
            core.save_project(project)
            if old_audio:
                (folder / old_audio).unlink(missing_ok=True)

    return queue_job(project_id, tasks, operation)


@app.post("/api/projects/{project_id}/reference")
async def upload_reference(
    project_id: str, file: Annotated[UploadFile, File()], consent: Annotated[bool, Form()] = False
):
    if not consent:
        raise WorkflowError(
            "Confirm this recording is yours or you have permission to clone the speaker's voice."
        )
    lock = lock_for_edit(project_id)
    folder = core.project_dir(project_id)
    source = folder / f"reference-upload-{uuid.uuid4().hex}.bin"
    filename = f"reference-{uuid.uuid4().hex}.wav"
    destination = folder / filename
    try:
        project = core.read_project(project_id)
        await save_upload(file, source, 20 * 1024 * 1024)
        duration = await run_in_threadpool(media.normalize_audio, source, destination)
        if not 3 <= duration <= 20:
            raise WorkflowError("Choose a clean voice recording between 3 and 20 seconds long.")
        previous = project.get("voice_reference")
        project["voice_reference"] = {"file": filename, "duration": duration}
        core.save_project(project)
        if previous:
            (folder / previous["file"]).unlink(missing_ok=True)
        return core.public_project(project)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        source.unlink(missing_ok=True)
        lock.release()


@app.post("/api/projects/{project_id}/slides/{slide_id}/audio")
async def upload_audio(project_id: str, slide_id: str, file: Annotated[UploadFile, File()]):
    lock = lock_for_edit(project_id)
    folder = core.project_dir(project_id)
    source = folder / f"upload-{uuid.uuid4().hex}.bin"
    filename = f"{uuid.uuid4().hex}.wav"
    try:
        project = core.read_project(project_id)
        slide = core.find_slide(project, slide_id)
        await save_upload(file, source, core.MAX_UPLOAD_BYTES)
        duration = await run_in_threadpool(media.normalize_audio, source, folder / filename)
        old_audio = slide.get("audio")
        slide.update(
            audio=filename,
            duration=duration,
            audio_signature=None,
            audio_source="uploaded",
            audio_version=uuid.uuid4().hex,
        )
        core.invalidate_export(project)
        core.save_project(project)
        if old_audio:
            (folder / old_audio).unlink(missing_ok=True)
        return core.public_project(project)
    finally:
        source.unlink(missing_ok=True)
        lock.release()


class RenderRequest(BaseModel):
    pause: float = Field(default=0.5, ge=0, le=5, allow_inf_nan=False)
    resolution: str = Field(default="1080p", pattern="^(1080p|720p)$")


@app.post("/api/projects/{project_id}/render")
def render(project_id: str, body: RenderRequest, tasks: BackgroundTasks):
    def operation(project, progress):
        if not project["slides"]:
            raise WorkflowError("Import slides first.")
        media.timeline_for(project["slides"], body.pause)
        core.invalidate_export(project)
        folder = core.project_dir(project_id)
        timeline = media.render_video(folder, project["slides"], body.pause, body.resolution, progress)
        (folder / "timings.json").write_text(json.dumps({"fps": media.FPS, "slides": timeline}, indent=2))
        project["settings"] = body.model_dump()
        project["export"] = {"duration": timeline[-1]["end"], "version": uuid.uuid4().hex}

    return queue_job(project_id, tasks, operation)


@app.get("/api/projects/{project_id}/files/{filename}")
def project_file(project_id: str, filename: str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+\.(png|wav|mp4|json)", filename):
        raise HTTPException(404)
    project = core.read_project(project_id)
    allowed = {slide["image"] for slide in project["slides"]}
    allowed.update(slide["audio"] for slide in project["slides"] if slide.get("audio"))
    if reference := project.get("voice_reference"):
        allowed.add(reference["file"])
    if project["export"]:
        allowed.update({"video.mp4", "timings.json"})
    path = core.project_dir(project_id) / filename
    if filename not in allowed or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=filename if filename in {"video.mp4", "timings.json"} else None)
