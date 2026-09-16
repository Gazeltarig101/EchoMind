import json
import uuid
import asyncio
from contextlib import suppress
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .asr import Transcriber
from .config import ASR_SELECTION_PATH, FINALIZE_SECONDS, LLM_SELECTION_PATH, PARTIAL_SECONDS, SAMPLE_RATE
from .embeddings import Embedder
from .llm import Responder
from .model_download import ModelDownloads
from .store import Store, now
from .sarvam import load_api_key, load_language_code, save_api_key, save_language_code

WEB = Path(__file__).parent / "web"
app = FastAPI(title="EchoMemory", docs_url=None, redoc_url=None)
store, embedder, transcriber, responder = Store(), Embedder(), Transcriber(), Responder()
transcriber.set_sarvam_api_key(load_api_key())
transcriber.set_sarvam_language_code(load_language_code())
if transcriber.sarvam_configured:
    transcriber.load_sarvam()
active_asr = "asr_sarvam_ai" if transcriber.backend == "sarvam-api" else ("asr_whisper" if transcriber.model else None)
active_llm = None

def load_saved_asr() -> str | None:
    try:
        value = json.loads(ASR_SELECTION_PATH.read_text()).get("model")
        return value if value in {"asr_whisper", "asr_nemotron", "asr_funasr_nano", "asr_sarvam_ai"} else None
    except (OSError, json.JSONDecodeError):
        return None

def save_active_asr(model: str) -> None:
    ASR_SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASR_SELECTION_PATH.write_text(json.dumps({"model": model}))

def load_saved_llm() -> str | None:
    try:
        value = json.loads(LLM_SELECTION_PATH.read_text()).get("model")
        return value if value in {"llm_qwen_1_5b", "llm_qwen_3b"} else None
    except (OSError, json.JSONDecodeError):
        return None

def save_active_llm(model: str) -> None:
    LLM_SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    LLM_SELECTION_PATH.write_text(json.dumps({"model": model}))

def load_downloaded_model(kind: str, path: str):
    global active_asr
    if kind == "asr_whisper":
        transcriber.load(path)
        active_asr = kind
        return transcriber.model is not None
    if kind == "asr_sarvam_ai":
        loaded = transcriber.load_sarvam()
        if loaded:
            active_asr = kind
        return loaded
    elif kind == "embeddings":
        embedder.load(path)
        return embedder.model is not None
    elif kind.startswith("llm_"):
        filename = ModelDownloads.model_file(kind)
        return responder.load(str(Path(path) / filename))
    # These artifacts use their own native runtimes (NeMo/Transformers for
    # Nemotron and FunASR's llama.cpp binary for Fun-ASR-Nano). They are marked
    # downloaded here, but are not silently routed through Faster-Whisper.
    if kind in {"asr_nemotron", "asr_funasr_nano"}:
        backend = "nemotron-gguf" if kind == "asr_nemotron" else "funasr-gguf"
        return transcriber.load_native(backend, path)
    return False

downloads = ModelDownloads(load_downloaded_model)
# ModelDownloads may eagerly load the local Whisper fallback while checking
# downloaded files. Restore the saved Sarvam provider afterwards so a saved key
# is reflected as the active choice on restart.
if transcriber.sarvam_configured and transcriber.load_sarvam():
    active_asr = "asr_sarvam_ai"
# Respect the user's last successful choice after a restart. A stale or incomplete
# selection is harmless: the already-loaded Whisper fallback stays available.
saved_asr = load_saved_asr()
# A saved Sarvam key is an explicit speech-provider choice. Keep that choice
# active on restart so the setup panel accurately reports the provider in use.
if saved_asr and not transcriber.sarvam_configured:
    saved_state = next(item for item in downloads.snapshot()["models"] if item["id"] == saved_asr)
    if load_downloaded_model(saved_asr, saved_state["path"]):
        active_asr = saved_asr
saved_llm = load_saved_llm()
if saved_llm:
    saved_state = next(item for item in downloads.snapshot()["models"] if item["id"] == saved_llm)
    if load_downloaded_model(saved_llm, saved_state["path"]):
        active_llm = saved_llm
app.mount("/static", StaticFiles(directory=WEB), name="static")

class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)

class Memory(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)

class ModelDownload(BaseModel):
    model: str = Field(pattern="^(asr_whisper|embeddings|asr_nemotron|asr_funasr_nano|asr_sarvam_ai|llm_qwen_1_5b|llm_qwen_3b|all)$")

class ModelSelection(BaseModel):
    model: str = Field(pattern="^(asr_whisper|asr_nemotron|asr_funasr_nano|asr_sarvam_ai|llm_qwen_1_5b|llm_qwen_3b)$")

class SarvamSettings(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)
    language_code: str = Field(default="unknown", pattern="^(unknown|en-IN|hi-IN|bn-IN|gu-IN|kn-IN|ml-IN|mr-IN|pa-IN|ta-IN|te-IN)$")

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")

@app.get("/api/status")
def status():
    return {
        "asr_ready": transcriber.model is not None,
        "asr_message": None if transcriber.model else transcriber.error,
        "active_asr": active_asr,
        "asr_backend": transcriber.backend,
        "embedding": embedder.name,
        "llm_ready": responder.llm is not None,
        "active_llm": active_llm,
        "local_only": transcriber.backend != "sarvam-api",
        "sarvam_configured": transcriber.sarvam_configured,
        "sarvam_language_code": transcriber.sarvam_language_code,
    }

@app.get("/api/models")
def models():
    snapshot = downloads.snapshot()
    for model in snapshot["models"]:
        model["downloaded"] = downloads.complete(model["id"])
        # A previous server version could mark downloaded LLM weights as an
        # initialization error. The files are still present and selectable;
        # model loading is retried only when the user chooses the model.
        if model["id"].startswith("llm_") and downloads.complete(model["id"]):
            model["status"] = "ready"
            model["error"] = ""
        if model["id"] == "asr_sarvam_ai":
            model["status"] = "ready" if transcriber.sarvam_configured else "not_configured"
            model["configured"] = transcriber.sarvam_configured
            model["runtime_ready"] = transcriber.sarvam_configured
            model["runtime_message"] = None if transcriber.sarvam_configured else "Enter your API key below to enable Saaras v3."
            continue
        if model["runtime"] in {"nemotron-gguf", "funasr-gguf"}:
            _, message = transcriber.native_runtime(model["runtime"], model["path"])
            model["runtime_ready"] = message is None
            model["runtime_message"] = message
        elif model["runtime"] == "llama-cpp":
            model["runtime_ready"] = responder.runtime_available()
            if not model["runtime_ready"]:
                model["runtime_message"] = responder.error or "Install the dependencies from requirements.txt to use this model."
    return snapshot

@app.post("/api/models/download", status_code=202)
def download_models(request: ModelDownload):
    try:
        started = downloads.start(request.model)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409 if isinstance(exc, RuntimeError) else 422, detail=str(exc)) from exc
    return {"started": started, **downloads.snapshot()}

@app.post("/api/models/select")
def select_model(request: ModelSelection):
    global active_asr, active_llm
    state = next(model for model in downloads.snapshot()["models"] if model["id"] == request.model)
    if request.model.startswith("llm_") and downloads.complete(request.model):
        # Recover from stale startup errors left by older versions. The model
        # is selectable; the native load is still attempted below.
        state["status"] = "ready"
    if request.model == "asr_sarvam_ai" and transcriber.sarvam_configured:
        state["status"] = "ready"
    if request.model == "asr_sarvam_ai" and not transcriber.sarvam_configured:
        raise HTTPException(status_code=409, detail="Add and verify your Sarvam API key before selecting Saaras v3.")
    if state["status"] != "ready" and not downloads.complete(request.model):
        raise HTTPException(status_code=409, detail="Download this model before selecting it.")
    if not load_downloaded_model(request.model, state["path"]):
        raise HTTPException(status_code=409, detail=responder.error or transcriber.error or "The selected model runtime is unavailable.")
    if request.model.startswith("llm_"):
        active_llm = request.model
        save_active_llm(active_llm)
        return {"active_llm": active_llm}
    active_asr = request.model
    save_active_asr(active_asr)
    return {"active_asr": active_asr, "backend": transcriber.backend}

@app.post("/api/sarvam")
def configure_sarvam(request: SarvamSettings):
    global active_asr
    api_key = request.api_key.strip()
    transcriber.set_sarvam_api_key(api_key)
    transcriber.set_sarvam_language_code(request.language_code)
    if not transcriber.load_sarvam():
        raise HTTPException(status_code=422, detail=transcriber.error or "The Sarvam AI client could not be initialized.")
    save_api_key(api_key)
    save_language_code(request.language_code)
    # Saving a working key is also an explicit model choice: the user can start
    # capturing immediately, while the model card still exposes the choice later.
    active_asr = "asr_sarvam_ai"
    save_active_asr(active_asr)
    return {"configured": True, "active_asr": active_asr, "backend": transcriber.backend, "message": "API key saved securely on this device."}

@app.get("/api/memories")
def memories():
    return {"memories": store.recent(), "total": store.count()}

@app.post("/api/memories", status_code=201)
def add_memory(memory: Memory):
    """Accessibility escape hatch for a memory the microphone missed."""
    session_id = f"note-{uuid.uuid4()}"
    store.start_session(session_id)
    try:
        memory_id = store.add(session_id, memory.text, embedder.encode(memory.text), raw_text=memory.text)
    finally:
        store.end_session(session_id)
    return {"id": memory_id, "text": " ".join(memory.text.split())}

@app.post("/api/chat")
def chat(question: Question):
    matches = store.search(embedder.encode(question.question))
    return {"answer": responder.answer(question.question, matches), "sources": matches}

@app.get("/api/summary")
def summary(date: str | None = None):
    if date is not None and (len(date) != 10 or date[4] != "-" or date[7] != "-"):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    day_memories = store.day(date)
    return {"date": date, "summary": responder.summary(day_memories), "count": len(day_memories)}

@app.websocket("/ws/capture")
async def capture(ws: WebSocket):
    await ws.accept()
    session_id = str(uuid.uuid4())
    store.start_session(session_id)
    audio = bytearray()
    started_at = now()
    partial_sent = False
    last_partial_bytes = 0
    pending_captions = []
    pending_started_at = None
    partial_bytes = int(SAMPLE_RATE * 4 * PARTIAL_SECONDS)
    finalize_bytes = int(SAMPLE_RATE * 4 * FINALIZE_SECONDS)
    await ws.send_json({"type": "ready", "session_id": session_id, "asr_ready": transcriber.model is not None})

    async def commit_pending(force=False):
        nonlocal pending_captions, pending_started_at
        # Cleanup is intentionally deferred until capture stops. During a live
        # session we only collect ASR text so the LLM cannot add latency or
        # create memories for unfinished thoughts.
        if not force or not pending_captions:
            return
        raw_text = " ".join(pending_captions)
        pending_captions = []
        memory_started_at = pending_started_at or now()
        pending_started_at = None
        await ws.send_json({"type": "processing", "message": "Polishing caption…"})
        cleaned = await asyncio.to_thread(responder.correct_transcript, raw_text)
        if not cleaned:
            await ws.send_json({
                "type": "error",
                "message": responder.error or "The LLM did not return a cleaned memory. Nothing was saved.",
            })
            return
        memory_id = store.add(
            session_id,
            cleaned,
            embedder.encode(cleaned),
            memory_started_at,
        )
        await ws.send_json({
            "type": "transcript",
            "id": memory_id,
            "text": cleaned,
            # This is sent only to the live transcript view. It is not written
            # to SQLite or used to create the embedding.
            "raw_text": raw_text,
            "final": True,
        })

    async def finalize():
        nonlocal started_at, partial_sent, last_partial_bytes, pending_started_at
        if not audio:
            return
        await ws.send_json({"type": "transcribing", "backend": transcriber.backend})
        try:
            text = await transcriber.transcribe(bytes(audio))
        except Exception as exc:
            audio.clear()
            partial_sent = False
            last_partial_bytes = 0
            await ws.send_json({"type": "error", "message": f"Transcription failed: {str(exc)[-300:]}"})
            started_at = now()
            return
        audio.clear()
        partial_sent = False
        last_partial_bytes = 0
        if text:
            if pending_started_at is None:
                pending_started_at = started_at
            pending_captions.append(text)
            # Keep adjacent ASR windows together. The LLM is called only once
            # capture stops, so it receives the complete spoken session.
            # This event is display-only: it lets the browser keep the full
            # live raw transcript without saving or embedding this segment.
            await ws.send_json({"type": "live_caption", "text": text})
        started_at = now()

    try:
        while True:
            message = await ws.receive()
            if message.get("text") is not None:
                try:
                    command = json.loads(message["text"])
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid capture command."})
                    continue
                if command.get("type") == "flush":
                    if audio:
                        await finalize()
                    continue
                if command.get("type") == "stop":
                    break
                continue
            frame = message.get("bytes")
            if not frame:
                continue
            audio.extend(frame)
            if transcriber.model and len(audio) >= partial_bytes and len(audio) - last_partial_bytes >= partial_bytes:
                partial = await transcriber.transcribe(bytes(audio))
                partial_sent = True
                last_partial_bytes = len(audio)
                if partial:
                    await ws.send_json({"type": "transcript", "text": partial, "final": False})
            if len(audio) >= finalize_bytes:
                await finalize()
        if audio:
            await finalize()
        # This is the only point where cleanup, embedding, and persistence are
        # triggered for live capture.
        await commit_pending(force=True)
        await ws.send_json({"type": "stopped"})
    except WebSocketDisconnect:
        pass
    except Exception:
        with suppress(Exception):
            await ws.send_json({"type": "error", "message": "Capture stopped unexpectedly. Your finalized memories are safe."})
    finally:
        store.end_session(session_id)
