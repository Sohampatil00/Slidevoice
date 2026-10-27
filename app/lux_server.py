"""Optional local LuxTTS voice cloning service."""

import base64
import hashlib
import hmac
import io
import logging
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import core

MODEL = "YatharthS/LuxTTS"
logger = logging.getLogger("uvicorn.error")
inference_lock = threading.Lock()


class LuxEngine:
    def __init__(self):
        os.environ.setdefault("HF_HOME", str(core.DATA / "models" / "huggingface"))
        import torch
        from huggingface_hub import snapshot_download
        from zipvoice.luxvoice import LuxTTS

        torch.set_num_threads(4)
        device = os.getenv("LUX_TTS_DEVICE", "auto")
        if device == "auto":
            device = (
                "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
            )
        if device not in {"cpu", "mps", "cuda"}:
            raise ValueError("LUX_TTS_DEVICE must be auto, cpu, mps, or cuda.")
        self.torch = torch
        self.device = device
        logger.info(
            "Loading %s on %s. First startup also downloads local Whisper transcription weights.",
            MODEL,
            device,
        )
        checkpoint = snapshot_download(
            MODEL,
            allow_patterns=[
                "model.pt",
                "config.json",
                "tokens.txt",
                "vocoder/config.yaml",
                "vocoder/vocos.bin",
            ],
        )
        self.model = LuxTTS(checkpoint, device=device, threads=4)
        self.model.vocos.eval()
        if device != "cpu":
            self.model.model.eval()
        self.reference_hash = None
        self.encoded_prompt = None

    def synthesize(self, text, audio):
        from contextlib import redirect_stdout

        import numpy as np
        import soundfile as sf

        try:
            samples, rate = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
        except (ValueError, RuntimeError) as error:
            raise ValueError("Invalid reference audio. Upload a clean WAV recording.") from error
        if not 3 <= len(samples) / rate <= 20:
            raise ValueError("Reference must contain 3–20 seconds of clean speech.")
        if not np.isfinite(samples).all() or np.max(np.abs(samples)) < 1e-5:
            raise ValueError("Invalid reference audio. Upload a clean WAV recording.")
        fingerprint = hashlib.sha256(audio).hexdigest()
        with self.torch.inference_mode():
            if fingerprint != self.reference_hash:
                with tempfile.TemporaryDirectory(prefix="lux-reference-", dir=core.DATA) as folder:
                    path = Path(folder) / "reference.wav"
                    sf.write(path, samples.mean(axis=1), rate)
                    # Upstream prints the reference transcript; keep it out of service logs.
                    with redirect_stdout(io.StringIO()):
                        encoded = self.model.encode_prompt(str(path), duration=5, rms=0.01)
                self.encoded_prompt = encoded
                self.reference_hash = fingerprint
            waveform = self.model.generate_speech(text, self.encoded_prompt, num_steps=4)
        samples = waveform.detach().float().cpu().numpy().reshape(-1)
        if samples.size == 0 or not np.isfinite(samples).all() or np.max(np.abs(samples)) < 1e-5:
            raise ValueError("The model produced empty or invalid audio. Try another reference recording.")
        peak = float(np.max(np.abs(samples)))
        if peak > 0.99:
            samples *= 0.99 / peak
        buffer = io.BytesIO()
        sf.write(buffer, samples, 48000, format="WAV")
        return buffer.getvalue(), 48000


@asynccontextmanager
async def lifespan(application):
    application.state.engine = await run_in_threadpool(LuxEngine)
    yield
    application.state.engine = None


app = FastAPI(title="SlideVoice LuxTTS", lifespan=lifespan)


@app.middleware("http")
async def protect_local_service(request: Request, call_next):
    if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return JSONResponse({"detail": "This model server is loopback-only."}, status_code=403)
    key = os.getenv("LUX_TTS_API_KEY", "")
    if key and not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {key}"):
        return JSONResponse({"detail": "Unauthorised."}, status_code=401)
    if request.method == "POST" and (
        request.headers.get("x-slidevoice") != "local" or request.headers.get("origin")
    ):
        return JSONResponse({"detail": "Use the local SlideVoice backend."}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "provider": "lux_tts", "model": MODEL}


class Reference(BaseModel):
    type: Literal["base64"]
    data: str = Field(min_length=1, max_length=30 * 1024 * 1024)


class Output(BaseModel):
    format: Literal["base64", "wav"] = "base64"


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    reference: Reference
    model: Literal["YatharthS/LuxTTS"] = MODEL
    output: Output = Field(default_factory=Output)


@app.post("/v1/tts")
def synthesize(body: SpeechRequest):
    if not body.text.strip():
        raise HTTPException(422, "Write a narration script first.")
    try:
        audio = base64.b64decode(body.reference.data, validate=True)
        if not audio or len(audio) > 20 * 1024 * 1024:
            raise ValueError("Invalid reference size")
    except ValueError as error:
        raise HTTPException(400, "Invalid reference audio.") from error
    if not inference_lock.acquire(blocking=False):
        raise HTTPException(429, "The model is busy with another slide. Retry after that job finishes.")
    started = time.monotonic()
    try:
        result, sample_rate = app.state.engine.synthesize(body.text, audio)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("LuxTTS inference failed (%s)", type(error).__name__)
        raise HTTPException(
            500, "Local LuxTTS inference failed. Check lux.log and device settings."
        ) from error
    finally:
        inference_lock.release()
    if body.output.format == "wav":
        return Response(result, media_type="audio/wav")
    return {
        "audio": base64.b64encode(result).decode(),
        "sample_rate": sample_rate,
        "generation_seconds": round(time.monotonic() - started, 3),
        "format": "base64",
    }
