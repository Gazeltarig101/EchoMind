import sys
import threading

from .config import LLM_MODEL

MAX_CONTEXT_CHARS = 12_000
MAX_CORRECTION_CHARS = 4_000

class Responder:
    def __init__(self):
        self.llm = None
        self.error = None
        self.model_path = None
        self.lock = threading.RLock()
        if LLM_MODEL:
            self.load(LLM_MODEL)

    @staticmethod
    def runtime_available():
        try:
            import llama_cpp  # noqa: F401
        except ImportError:
            return False
        return True

    def load(self, model_path: str):
        if not self.runtime_available():
            version = f"Python {sys.version_info.major}.{sys.version_info.minor}"
            self.error = f"llama-cpp-python is not installed for {version}. Install requirements.txt; EchoMemory will use safe extractive answers meanwhile."
            return False
        try:
            from llama_cpp import Llama
            # Keep prompt and decode batches conservative.  This avoids the
            # set_rows assertion seen with llama.cpp 0.3.x when a long summary
            # or two requests reach the native decoder at the same time.
            model = Llama(
                model_path=model_path,
                n_ctx=4096,
                n_batch=256,
                n_ubatch=128,
                n_threads=4,
                n_threads_batch=4,
                # Keep the default reliable on machines where Metal is not
                # available; users can opt into GPU offload through the runtime.
                n_gpu_layers=0,
                verbose=False,
            )
        except Exception as exc:
            if isinstance(exc, ImportError):
                self.error = "Install requirements.txt to use local chat models."
            else:
                self.error = str(exc)
            return False
        self.llm = model
        self.model_path = model_path
        self.error = None
        return True

    def answer(self, question, memories):
        if not memories:
            return "I couldn't find a matching memory yet. Try capturing more conversation first."
        context = self._context(memories)
        if self.llm:
            prompt = f"Answer only from the memories below. If unknown, say so.\nMemories:\n{context}\nQuestion: {question}\nAnswer:"
            try:
                with self.lock:
                    result = self.llm(prompt, max_tokens=220, temperature=0.2, stop=["\nQuestion:"])
                answer = result["choices"][0]["text"].strip()
                if answer:
                    return answer
            except Exception as exc:
                self.error = f"Local chat inference failed: {exc}"
        return "Here’s what I found:\n\n" + "\n".join(f"• {m['text']}" for m in memories[:3])

    def summary(self, memories):
        if not memories: return "No memories captured today yet."
        if self.llm:
            context = self._context(memories)
            try:
                with self.lock:
                    result = self.llm(f"Write a concise daily summary from these notes:\n{context}\nSummary:", max_tokens=180, temperature=0.2)
                summary = result["choices"][0]["text"].strip()
                if summary:
                    return summary
            except Exception as exc:
                self.error = f"Local summary inference failed: {exc}"
        return "Today you captured:\n\n" + "\n".join(f"• {m['text']}" for m in memories)

    def correct_transcript(self, transcript: str) -> str | None:
        """Correct and merge ASR text without changing its meaning.

        This is deliberately strict for memory creation. A raw transcript is
        never an acceptable substitute for an LLM response.
        """
        original = " ".join((transcript or "").split())
        if not original:
            return None
        if not self.llm:
            self.error = "Select and load a local LLM before stopping capture."
            return None

        prompt = (
            "You clean up live speech-to-text captions for a personal memory.\n"
            "Correct obvious ASR spelling, punctuation, capitalization, and grammar mistakes. "
            "Merge fragments into coherent sentences. Preserve the exact meaning, names, "
            "dates, times, numbers, places, and technical terms. Never invent, infer, or add "
            "facts. If a word is uncertain, keep the original wording. Return only the cleaned "
            "text, with no explanation or quotation marks.\n\n"
            f"Raw captions:\n{original[:MAX_CORRECTION_CHARS]}\n\nCleaned text:"
        )
        try:
            with self.lock:
                result = self.llm(
                    prompt,
                    max_tokens=260,
                    temperature=0.0,
                    # Qwen commonly emits a blank line after a short answer;
                    # stopping on blank lines can therefore return nothing.
                    # Stop only at prompt boundaries / the model end token.
                    stop=["\nRaw captions:", "<|im_end|>"],
                )
            candidate = result["choices"][0]["text"].strip().strip('"')
            candidate = " ".join(candidate.split())
            if self._valid_correction(original, candidate):
                self.error = None
                return candidate
            self.error = "The LLM returned an unusable cleanup response. Nothing was saved."
        except Exception as exc:
            self.error = f"Local transcript cleanup failed: {exc}"
        return None

    @staticmethod
    def _valid_correction(original: str, candidate: str) -> bool:
        """Reject empty, prompt-like, or implausibly expanded model output."""
        if not candidate or len(candidate) > MAX_CORRECTION_CHARS * 1.5:
            return False
        lowered = candidate.lower()
        if lowered.startswith(("cleaned text:", "assistant:", "raw captions:")):
            return False
        # A cleanup may add punctuation or expand contractions, but a large
        # expansion is usually the model inventing content.
        if len(candidate) > max(len(original) * 2.5, len(original) + 160):
            return False
        return True

    @staticmethod
    def _context(memories):
        """Keep native prompts bounded even when a day has many memories."""
        lines = []
        size = 0
        for memory in reversed(memories):
            line = f"[{memory.get('created_at', '')}] {memory['text']}"
            if lines and size + len(line) + 1 > MAX_CONTEXT_CHARS:
                break
            lines.append(line)
            size += len(line) + 1
        return "\n".join(reversed(lines))
