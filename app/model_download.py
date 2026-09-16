"""Download recommended public model artifacts with observable local progress.

Only model files are requested from Hugging Face. EchoMemory recordings, transcripts,
and the database are never included in any request.
"""
import json
import threading
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from .config import MODELS_DIR

RECOMMENDED = {
    "asr_whisper": {
        "label": "Live transcription",
        "repo": "Systran/faster-whisper-small.en",
        "directory": "faster-whisper-small.en",
        "size": "~461 MB",
        "description": "English Whisper — a simple, reliable local transcription choice.",
        "runtime": "faster-whisper",
    },
    "embeddings": {
        "label": "Memory search",
        "repo": "sentence-transformers/all-MiniLM-L6-v2",
        "directory": "all-MiniLM-L6-v2",
        "size": "~90 MB",
        "description": "Compact local model for meaning-based memory retrieval.",
        "runtime": "sentence-transformers",
    },
    "asr_nemotron": {
        "label": "Nemotron 3.5 ASR Streaming 0.6B",
        "repo": "nvidia/nemotron-3.5-asr-streaming-0.6b",
        "directory": "nemotron-3.5-asr-streaming-0.6b",
        "include": ["nemotron-3.5-asr-streaming-0.6b.q8_0.gguf"],
        "model_file": "nemotron-3.5-asr-streaming-0.6b.q8_0.gguf",
        "size": "~742 MB",
        "description": "Multilingual NVIDIA ASR with a ready-to-run GGUF model.",
        "runtime": "nemotron-gguf",
    },
    "asr_funasr_nano": {
        "label": "Fun-ASR-Nano (GGUF)",
        "repo": "FunAudioLLM/Fun-ASR-Nano-GGUF",
        "directory": "fun-asr-nano-gguf",
        "include": ["funasr-encoder-f16.gguf", "qwen3-0.6b-q4km.gguf"],
        "extra_repos": [{"repo": "FunAudioLLM/fsmn-vad-GGUF", "include": ["fsmn-vad.gguf"]}],
        "size": "~956 MB (encoder + Q4 decoder + VAD)",
        "description": "Strong CPU/edge Chinese-English-Japanese model using the FunASR llama.cpp runtime.",
        "runtime": "funasr-gguf",
    },
    "asr_sarvam_ai": {
        "label": "Sarvam AI — Saaras v3",
        "directory": "sarvam-ai",
        "size": "API",
        "description": "Cloud speech-to-text for Indian languages using your Sarvam API key.",
        "runtime": "sarvam-api",
        "downloadable": False,
    },
    "llm_qwen_1_5b": {
        "label": "Qwen 2.5 1.5B Chat",
        "repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "directory": "qwen2.5-1.5b-instruct-q4_k_m",
        "include": ["qwen2.5-1.5b-instruct-q4_k_m.gguf"],
        "model_file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size": "1.12 GB",
        "description": "Fast, compact local chat model for everyday memory questions.",
        "runtime": "llama-cpp",
    },
    "llm_qwen_3b": {
        "label": "Qwen 2.5 3B Chat",
        "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "directory": "qwen2.5-3b-instruct-q4_k_m",
        "include": ["qwen2.5-3b-instruct-q4_k_m.gguf"],
        "model_file": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "size": "2.0 GB",
        "description": "More capable local chat model; needs more memory than the 1.5B option.",
        "runtime": "llama-cpp",
    },
}

class ModelDownloads:
    def __init__(self, on_complete):
        self.on_complete = on_complete
        self.lock = threading.RLock()
        self.running = False
        self.state = {key: {"status": "ready" if self.complete(key) else "not_downloaded", "received": 0, "total": 0, "file": "", "error": ""} for key in RECOMMENDED}
        for key in RECOMMENDED:
            # Alternative native runtimes should not replace the active default
            # merely because their files exist from a previous run.
            if key in {"asr_nemotron", "asr_funasr_nano"}:
                continue
            # Downloaded chat weights are usable assets even when native model
            # initialization cannot happen during server startup (for example
            # when a GPU backend is temporarily unavailable). Keep them ready
            # and initialize only when the user explicitly selects them.
            if key.startswith("llm_"):
                continue
            if self.marker(key).exists() and not self.on_complete(key, str(self.path(key))):
                self.state[key].update(status="error", error="Model files were found, but the local AI runtime is unavailable.")

    def path(self, key):
        return MODELS_DIR / RECOMMENDED[key]["directory"]

    def marker(self, key):
        return self.path(key) / ".echomemory-complete"

    def complete(self, key):
        if self.marker(key).exists():
            return True
        spec = RECOMMENDED[key]
        target = self.path(key)
        required = spec.get("model_file") or spec.get("include")
        if not required:
            return False
        patterns = [required] if isinstance(required, str) else required
        return all(any(item.is_file() for item in target.glob(pattern)) for pattern in patterns)

    @staticmethod
    def model_file(key):
        return RECOMMENDED[key].get("model_file")

    def snapshot(self):
        with self.lock:
            models = []
            for key, spec in RECOMMENDED.items():
                item = dict(spec)
                item.update({"id": key, "path": str(self.path(key)), **self.state[key]})
                models.append(item)
            return {"running": self.running, "models": models}

    def start(self, requested):
        # "all" means the supported default stack; large experimental runtimes
        # stay opt-in so one click does not consume multiple gigabytes.
        names = ["asr_whisper", "embeddings"] if requested == "all" else [requested]
        if not all(name in RECOMMENDED for name in names):
            raise ValueError("Unknown model selection")
        if any(RECOMMENDED[name].get("downloadable", True) is False for name in names):
            raise ValueError("This speech provider does not require a model download. Configure it in the setup panel.")
        with self.lock:
            if self.running:
                raise RuntimeError("A model download is already running")
            names = [name for name in names if self.state[name]["status"] != "ready"]
            if not names:
                return False
            self.running = True
            for name in names:
                self.state[name].update(status="queued", received=0, total=0, file="", error="")
        threading.Thread(target=self._run, args=(names,), daemon=True).start()
        return True

    def _set(self, key, **changes):
        with self.lock:
            self.state[key].update(changes)

    def _run(self, names):
        try:
            for key in names:
                self._download(key)
                # A native GGUF download is complete even when its optional
                # executable has not been installed yet. Runtime readiness is
                # checked at model selection, not treated as a failed download.
                # Downloading is independent from inference. In particular, a
                # GGUF can be installed before llama-cpp-python is available.
                # Runtime readiness is checked when the user selects the model.
                if key in {"asr_whisper", "embeddings"} and not self.on_complete(key, str(self.path(key))):
                    raise RuntimeError("Files are downloaded, but the local AI runtime is unavailable. Install requirements.txt and retry.")
                self.marker(key).touch()
                self._set(key, status="ready", file="", error="")
        except Exception as exc:
            active = next((key for key in names if self.state[key]["status"] == "downloading"), names[0])
            self._set(active, status="error", error=str(exc))
        finally:
            with self.lock:
                self.running = False

    def _files(self, repo, include=None):
        url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true&expand=true"
        request = Request(url, headers={"User-Agent": "EchoMemory local-model-installer/1.0"})
        with urlopen(request, timeout=30) as response:
            items = json.load(response)
        files = []
        for item in items:
            if item.get("type") != "file" or item.get("path") == ".gitattributes":
                continue
            if include and not any(self._matches(item["path"], pattern) for pattern in include):
                continue
            files.append((item["path"], int(item.get("size") or item.get("lfs", {}).get("size") or 0)))
        if not files:
            raise RuntimeError("The model repository returned no downloadable files.")
        return files

    @staticmethod
    def _matches(path, pattern):
        if pattern.startswith("*."):
            return path.endswith(pattern[1:])
        return path == pattern

    def _download(self, key):
        spec = RECOMMENDED[key]
        sources = [(spec["repo"], relative_path, size) for relative_path, size in self._files(spec["repo"], spec.get("include"))]
        for extra in spec.get("extra_repos", []):
            sources.extend((extra["repo"], relative_path, size) for relative_path, size in self._files(extra["repo"], extra.get("include")))
        total = sum(size for _, _, size in sources)
        target = self.path(key)
        target.mkdir(parents=True, exist_ok=True)
        received = 0
        self._set(key, status="downloading", total=total, received=0, file="Preparing files…")
        for repo, relative_path, expected_size in sources:
            output = target / relative_path
            output.parent.mkdir(parents=True, exist_ok=True)
            if expected_size and output.exists() and output.stat().st_size == expected_size:
                received += expected_size
                self._set(key, received=received, file=relative_path)
                continue
            partial = output.with_name(output.name + ".part")
            start = partial.stat().st_size if partial.exists() else 0
            download_url = f"https://huggingface.co/{repo}/resolve/main/{quote(relative_path)}"
            headers = {"User-Agent": "EchoMemory local-model-installer/1.0"}
            if start:
                headers["Range"] = f"bytes={start}-"
            with urlopen(Request(download_url, headers=headers), timeout=60) as response:
                append = start > 0 and response.status == 206
                if not append:
                    start = 0
                mode = "ab" if append else "wb"
                with partial.open(mode) as handle:
                    current = start
                    while block := response.read(1024 * 256):
                        handle.write(block)
                        current += len(block)
                        self._set(key, received=received + current, file=relative_path)
            if expected_size and partial.stat().st_size != expected_size:
                raise RuntimeError(f"Incomplete download for {relative_path}; retry to resume.")
            partial.replace(output)
            received += output.stat().st_size
            self._set(key, received=received, file=relative_path)
