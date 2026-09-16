"""Local streaming-friendly ASR adapter.

The browser sends 16 kHz mono float32 PCM. Faster-whisper runs only against the
model path supplied by ECHOMEMORY_ASR_MODEL; it never resolves a hosted model ID.
"""
import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
import numpy as np
from .config import ASR_MODEL, DEVICE, SAMPLE_RATE, VOICE_RMS_THRESHOLD, MIN_VOICED_SECONDS

class Transcriber:
    def __init__(self):
        self.model = None
        self.error = None
        self.model_path = ASR_MODEL
        self.backend = "faster-whisper"
        self.native_binary = None
        self.sarvam_api_key = ""
        self.sarvam_client = None
        self.sarvam_language_code = "unknown"
        self.load()

    @property
    def sarvam_configured(self) -> bool:
        return bool(self.sarvam_api_key)

    def set_sarvam_api_key(self, api_key: str) -> None:
        self.sarvam_api_key = api_key.strip()
        self.sarvam_client = None

    def set_sarvam_language_code(self, language_code: str) -> None:
        self.sarvam_language_code = language_code.strip() or "unknown"

    def load_sarvam(self) -> bool:
        if not self.sarvam_configured:
            self.error = "Add a Sarvam AI API key in the setup panel."
            return False
        try:
            from sarvamai import SarvamAI
            self.sarvam_client = SarvamAI(api_subscription_key=self.sarvam_api_key)
        except Exception as exc:
            self.error = f"Sarvam AI client is unavailable: {exc}"
            return False
        self.model = {"backend": "sarvam-api"}
        self.backend = "sarvam-api"
        self.error = None
        return True

    def load(self, model_path: str | None = None):
        target_path = model_path if model_path is not None else self.model_path
        if not target_path:
            self.error = "No local ASR model path is configured."
            return False
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(target_path, device=DEVICE, compute_type="int8", local_files_only=True)
        except Exception as exc:
            self.error = str(exc)
            return False
        self.model = model
        self.error = None
        self.model_path = target_path
        self.backend = "faster-whisper"
        self.native_binary = None
        return True

    def load_native(self, backend: str, model_path: str):
        """Switch to a native backend only after its complete setup is verified.

        This deliberately leaves the current model untouched on failure.  The old
        implementation cleared a working Whisper model before discovering that a
        GGUF command was missing, which made a failed selection stop capture.
        """
        binary, error = self.native_runtime(backend, model_path)
        if error:
            self.error = error
            return False
        self.model = {"backend": backend, "path": model_path}
        self.error = None
        self.model_path = model_path
        self.backend = backend
        self.native_binary = binary
        return True

    @staticmethod
    def native_runtime(backend: str, model_path: str) -> tuple[str | None, str | None]:
        if backend == "nemotron-gguf":
            binary = os.getenv("ECHOMEMORY_NEMO_SPEECH_BIN") or shutil.which("nemo-speech")
            if not binary:
                return None, "Nemotron needs NVIDIA NeMo-Speech.cpp (`nemo-speech`). Install it, then select this model again."
            ggufs = list(Path(model_path).glob("*.gguf")) if Path(model_path).is_dir() else [Path(model_path)]
            if not any(item.is_file() for item in ggufs):
                return None, "Nemotron needs its ready-to-run ASR .gguf file in the model folder."
            return binary, None

        project_binary = Path(__file__).resolve().parent.parent / ".local" / "bin" / "llama-funasr-cli"
        binary = os.getenv("ECHOMEMORY_FUNASR_BIN") or shutil.which("llama-funasr-cli")
        if not binary and project_binary.is_file() and os.access(project_binary, os.X_OK):
            binary = str(project_binary)
        if not binary:
            return None, "Fun-ASR-Nano needs `llama-funasr-cli` from llama.cpp on PATH."
        required = ("funasr-encoder-f16.gguf", "qwen3-0.6b-q4km.gguf")
        missing = [name for name in required if not (Path(model_path) / name).is_file()]
        if missing:
            return None, f"Fun-ASR-Nano is missing: {', '.join(missing)}."
        return binary, None

    async def transcribe_segments(self, pcm_bytes: bytes) -> list[dict]:
        if not self.model or len(pcm_bytes) < 1_600:
            return []
        audio = np.frombuffer(pcm_bytes, dtype=np.float32).copy()
        # Do not give the decoder near-silent audio: Whisper can confidently
        # hallucinate text from noise or a long silent window.
        frame_size = int(SAMPLE_RATE * 0.02)
        frames = audio[:len(audio) // frame_size * frame_size].reshape(-1, frame_size)
        rms = np.sqrt(np.mean(np.square(frames), axis=1)) if len(frames) else np.array([])
        if (rms > VOICE_RMS_THRESHOLD).sum() * 0.02 < MIN_VOICED_SECONDS:
            return []

        if self.backend == "sarvam-api":
            text = await asyncio.to_thread(self._transcribe_sarvam, audio)
            return [{"text": text, "start": 0.0, "end": len(audio) / SAMPLE_RATE}] if text else []
        if self.backend != "faster-whisper":
            text = await asyncio.to_thread(self._transcribe_native, audio)
            return [{"text": text, "start": 0.0, "end": len(audio) / SAMPLE_RATE}] if text else []

        def infer():
            segments, _ = self.model.transcribe(
                audio,
                language="en",
                beam_size=1,
                best_of=1,
                temperature=0,
                condition_on_previous_text=False,
                repetition_penalty=1.15,
                no_repeat_ngram_size=3,
                no_speech_threshold=0.55,
                log_prob_threshold=-0.8,
                vad_filter=True,
                vad_parameters={"threshold": 0.55, "min_speech_duration_ms": 120, "min_silence_duration_ms": 450, "speech_pad_ms": 260},
            )
            accepted = []
            for segment in segments:
                # Belt-and-braces filter: VAD and decoder confidence must both
                # agree that this is speech before it becomes a memory.
                if segment.no_speech_prob > 0.55 and segment.avg_logprob < -0.5:
                    continue
                text = segment.text.strip()
                if text:
                    accepted.append({"text": text, "start": float(segment.start), "end": float(segment.end)})
            return accepted

        return await asyncio.to_thread(infer)

    def _transcribe_sarvam(self, audio: np.ndarray) -> str:
        if not self.sarvam_client and not self.load_sarvam():
            raise RuntimeError(self.error or "Sarvam AI is not configured")
        with tempfile.NamedTemporaryFile(suffix=".wav") as temporary:
            pcm16 = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm16 * 32767).astype(np.int16)
            with wave.open(temporary.name, "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(SAMPLE_RATE); wav.writeframes(pcm16.tobytes())
            with open(temporary.name, "rb") as handle:
                arguments = {"file": handle, "model": "saaras:v3", "mode": "transcribe"}
                if self.sarvam_language_code != "unknown":
                    arguments["language_code"] = self.sarvam_language_code
                response = self.sarvam_client.speech_to_text.transcribe(**arguments)
        if isinstance(response, dict):
            return str(response.get("transcript") or response.get("text") or "").strip()
        return str(getattr(response, "transcript", getattr(response, "text", "")) or "").strip()

    def _transcribe_native(self, audio: np.ndarray) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav") as temporary:
            pcm16 = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm16 * 32767).astype(np.int16)
            with wave.open(temporary.name, "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(SAMPLE_RATE); wav.writeframes(pcm16.tobytes())
            if self.backend == "nemotron-gguf":
                model = next(iter(Path(self.model_path).glob("*.gguf")), Path(self.model_path))
                command = [self.native_binary, "transcribe", temporary.name, "--model", str(model)]
            else:
                encoder = f"{self.model_path}/funasr-encoder-f16.gguf"
                decoder = f"{self.model_path}/qwen3-0.6b-q4km.gguf"
                # llama-funasr-cli's native interface accepts the encoder, LLM,
                # audio, and an optional chunk duration. It does not accept the
                # VAD flag used by the previous adapter.
                command = [self.native_binary, "--enc", encoder, "-m", decoder, "-a", temporary.name, "--chunk", "15"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout or "Native ASR failed").strip()[-500:])
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return lines[-1] if lines else ""

    async def transcribe(self, pcm_bytes: bytes) -> str:
        segments = await self.transcribe_segments(pcm_bytes)
        return self._clean(" ".join(segment["text"] for segment in segments))

    @staticmethod
    def _clean(text: str) -> str:
        text = " ".join(text.split())
        # Fun-ASR emits this control token for non-speech. It is not a memory.
        if text.lower() in {"/sil", "[sil]", "<sil>", "sil"}:
            return ""
        words = re.findall(r"[a-z']+", text.lower())
        # Repeated boilerplate is a common silence-hallucination signature. This
        # only rejects a result when a single word dominates a non-trivial output.
        if len(words) >= 8 and max(words.count(word) for word in set(words)) / len(words) >= 0.62:
            return ""
        return text
