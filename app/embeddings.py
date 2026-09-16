"""Embedding adapter with an always-local deterministic fallback."""
import hashlib
import re
import numpy as np
from .config import EMBEDDING_MODEL

class Embedder:
    def __init__(self):
        self.model = None
        self.name = "local hashed embedding (fallback)"
        self.model_path = EMBEDDING_MODEL
        self.load()

    def load(self, model_path: str | None = None):
        if model_path is not None:
            self.model_path = model_path
        self.model = None
        self.name = "local hashed embedding (fallback)"
        if not self.model_path:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_path, device="cpu", local_files_only=True)
            self.name = self.model_path
        except Exception:
            self.model = None
    def encode(self, text: str):
        if self.model:
            return self.model.encode(text, normalize_embeddings=True).astype(np.float32)
        vec = np.zeros(384, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9']+", text.lower())
        for token in tokens:
            for feature in (token, *[token[i:i+3] for i in range(max(1, len(token)-2))]):
                h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=4).digest(), "big") % len(vec)
                vec[h] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec
