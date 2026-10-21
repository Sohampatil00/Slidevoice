import base64
import hashlib
import hmac
import io
import logging
import math
import os
import re
import tempfile
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import core

logger = logging.getLogger("uvicorn.error")
inference_lock = threading.Lock()


class IndicEngine:
    def __init__(self):
        os.environ.setdefault("HF_HOME", str(core.DATA / "models" / "huggingface"))
        import torch
        from miocodec import MioCodecModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(4)
        self.torch = torch
        self.model_id = os.getenv("INDIC_MIO_MODEL", "SPRINGLab/Indic-Mio")
        device = os.getenv("INDIC_MIO_DEVICE", "auto")
        if device == "auto":
            device = (
                "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
            )
        self.device = device
        self.codec_device = os.getenv("INDIC_MIO_CODEC_DEVICE", "cpu")
        logger.info("Loading %s on %s. First run downloads the model weights.", self.model_id, device)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=False)
        self.model = (
            AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch.float32,
                attn_implementation="sdpa",
                trust_remote_code=False,
            )
            .eval()
            .to(device)
        )
        codec_id = os.getenv("INDIC_MIO_CODEC_MODEL", "Aratako/MioCodec-25Hz-44.1kHz-v2")
        logger.info("Loading MioCodec on %s.", self.codec_device)
        self.codec = MioCodecModel.from_pretrained(codec_id).eval().to(self.codec_device)
        self.embeddings = OrderedDict()

    def reference_embedding(self, audio):
        from miocodec import load_audio

        fingerprint = hashlib.sha256(audio).hexdigest()
        if fingerprint not in self.embeddings:
            with tempfile.TemporaryDirectory(prefix="indic-reference-", dir=core.DATA) as folder:
                reference_path = Path(folder) / "reference.wav"
                reference_path.write_bytes(audio)
                waveform = load_audio(str(reference_path), sample_rate=self.codec.config.sample_rate)
            duration = waveform.shape[-1] / self.codec.config.sample_rate
            if not 3 <= duration <= 20:
                raise ValueError("Reference must contain 3–20 seconds of clean speech.")
            with self.torch.inference_mode():
                features = self.codec.encode(
                    waveform.to(self.codec_device), return_content=False, return_global=True
                )
            self.embeddings[fingerprint] = features.global_embedding
            if len(self.embeddings) > 4:
                self.embeddings.popitem(last=False)
        self.embeddings.move_to_end(fingerprint)
        return self.embeddings[fingerprint]

    def synthesize(self, text, audio, parameters):
        import soundfile

        embedding = self.reference_embedding(audio)
        prompt = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": text}],
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        max_tokens = parameters.get("max_tokens", 1400)
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=parameters.get("temperature", 0.9),
                top_p=parameters.get("top_p", 0.9),
                use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )
            generated = output[0, inputs["input_ids"].shape[1] :]
            if len(generated) >= max_tokens:
                raise ValueError("Generation reached its token limit. Shorten the sentence.")
            decoded = self.tokenizer.decode(generated, skip_special_tokens=False)
            tokens = [int(value) for value in re.findall(r"<\|s_(\d+)\|>", decoded)]
            if not tokens or any(token >= 12800 for token in tokens):
                raise ValueError("The model did not return valid speech tokens. Try a shorter sentence.")
            waveform = self.codec.decode(
                content_token_indices=self.torch.tensor(
                    tokens, dtype=self.torch.long, device=self.codec_device
                ),
                global_embedding=embedding,
            )
        buffer = io.BytesIO()
        samples = waveform.detach().float().cpu().numpy().reshape(-1)
        peak = float(abs(samples).max()) if samples.size else 0
        if not math.isfinite(peak) or peak <= 0:
            raise ValueError("The model produced empty or invalid audio. Try another reference recording.")
        if peak > 0.99:
            samples = samples * (0.99 / peak)
        soundfile.write(buffer, samples, self.codec.config.sample_rate, format="WAV")
        return buffer.getvalue(), self.codec.config.sample_rate, len(tokens)


@asynccontextmanager
async def lifespan(application):
    application.state.engine = await run_in_threadpool(IndicEngine)
    yield
    application.state.engine = None


app = FastAPI(title="SlideVoice Indic-MIO", lifespan=lifespan)


@app.middleware("http")
async def protect_local_service(request: Request, call_next):
    if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return JSONResponse({"detail": "This model server is loopback-only."}, status_code=403)
    api_key = os.getenv("INDIC_MIO_API_KEY", "")
    if api_key and not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {api_key}"):
        return JSONResponse({"detail": "Unauthorised."}, status_code=401)
    if request.method == "POST" and (
        request.headers.get("x-slidevoice") != "local" or request.headers.get("origin")
    ):
        return JSONResponse({"detail": "Use the local SlideVoice backend."}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "model": os.getenv("INDIC_MIO_MODEL", "SPRINGLab/Indic-Mio")}


@app.get("/v1/presets")
def presets():
    return {"presets": []}


class Reference(BaseModel):
    type: Literal["base64", "preset"]
    data: str = Field(default="", max_length=30 * 1024 * 1024)
    preset_id: str = Field(default="", max_length=120)


class Sampling(BaseModel):
    model: str = Field(default="SPRINGLab/Indic-Mio", max_length=160)
    max_tokens: int = Field(default=1400, ge=100, le=2048)
    temperature: float = Field(default=0.9, ge=0.1, le=2, allow_inf_nan=False)
    top_p: float = Field(default=0.9, gt=0, le=1, allow_inf_nan=False)


class Output(BaseModel):
    format: Literal["base64", "wav"] = "base64"


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=280)
    reference: Reference
    llm: Sampling = Field(default_factory=Sampling)
    output: Output = Field(default_factory=Output)


@app.post("/v1/tts")
def synthesize(body: SpeechRequest):
    if body.llm.model != os.getenv("INDIC_MIO_MODEL", "SPRINGLab/Indic-Mio"):
        raise HTTPException(400, "The requested model is not loaded in this server.")
    if body.reference.type != "base64":
        raise HTTPException(
            400, "Upload your voice sample in SlideVoice. This local server has no bundled voice presets."
        )
    try:
        audio = base64.b64decode(body.reference.data, validate=True)
        if not audio or len(audio) > 20 * 1024 * 1024:
            raise ValueError("Invalid reference size")
    except ValueError as error:
        raise HTTPException(400, "Invalid reference audio.") from error
    if not inference_lock.acquire(blocking=False):
        raise HTTPException(429, "The model is busy with another slide. Retry after that job finishes.")
    try:
        result, sample_rate, token_count = app.state.engine.synthesize(
            body.text, audio, body.llm.model_dump()
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.error("Indic-MIO inference failed (%s)", type(error).__name__)
        raise HTTPException(500, "Local inference failed. Check model/device settings in .env.") from error
    finally:
        inference_lock.release()
    if body.output.format == "wav":
        return Response(result, media_type="audio/wav")
    return {
        "audio": base64.b64encode(result).decode(),
        "sample_rate": sample_rate,
        "token_count": token_count,
        "format": "base64",
    }
