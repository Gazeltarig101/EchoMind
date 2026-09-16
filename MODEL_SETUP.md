# Local model setup

EchoMemory never lets an AI library silently fetch a model. The recommended route is
the explicit **Download recommended setup** button inside the app, which saves model
files under `models/` and shows live progress. It requests only public model files;
recordings, transcripts, and the database are never uploaded.

## 1. Install local model runtimes

```bash
pip install -r requirements.txt
```

The standard requirements file includes the Python runtimes used by the model
cards in the UI: Faster-Whisper, Sentence Transformers, and llama.cpp Python.
The separate `requirements-local-ai.txt` file remains available for older
checkouts, but does not need to be installed again after `requirements.txt`.

For the alternative runtimes, install the matching optional file instead:

```bash
pip install -r requirements-funasr.txt       # Python Fun-ASR path
pip install -r requirements-nemotron.txt     # NeMo Python path
```

The model cards for Nemotron GGUF and Fun-ASR-Nano GGUF use native executables,
not these optional Python runtimes. Install the executable described below when
you choose either alternative.

## 2. Download in the app (recommended)

Start EchoMemory, open `http://127.0.0.1:8000`, and select **Download recommended
setup** in the Local model setup panel. Downloads are resumable and the models are
loaded immediately when complete.

## 3. Or put models in `models/` manually

Use any trusted offline transfer method, or download model files once before using
EchoMemory. The download is model installation, not inference: captured audio and
memory data never leave this app.

Recommended models:

| Purpose | Model | Practical default |
| --- | --- | --- |
| Live ASR (works directly in EchoMemory) | Faster-Whisper CTranslate2 | `Systran/faster-whisper-small.en` |
| Alternative ASR download | NVIDIA Nemotron 3.5 Streaming 0.6B GGUF | `nvidia/nemotron-3.5-asr-streaming-0.6b` |
| Alternative ASR download | Fun-ASR-Nano GGUF + FSMN-VAD | `FunAudioLLM/Fun-ASR-Nano-GGUF` |
| Embeddings | Sentence Transformers | `sentence-transformers/all-MiniLM-L6-v2` |
| RAG chat (optional) | GGUF instruct model | Qwen2.5 3B Instruct Q4_K_M |

For example, with the Hugging Face command-line client installed, download the first
two to local directories:

```bash
huggingface-cli download Systran/faster-whisper-small.en --local-dir models/faster-whisper-small.en
huggingface-cli download sentence-transformers/all-MiniLM-L6-v2 --local-dir models/all-MiniLM-L6-v2
```

The app’s model panel offers the published Nemotron 3.5 GGUF directly. It downloads
`nemotron-3.5-asr-streaming-0.6b.q8_0.gguf` and uses NVIDIA’s native `nemo-speech`
runtime for inference. A manually placed copy of that file is recognized too.
Fun-ASR-Nano remains a native-runtime asset and requires the FunASR
`llama-funasr-cli` binary; alternative weights are not silently routed through an
incompatible decoder.

For GGUF inference, install the native runtime from the official projects:

```bash
# Nemotron GGUF runtime
curl -fsSL https://github.com/NVIDIA/NeMo-Speech.cpp/raw/main/scripts/install.sh | sh

# Fun-ASR-Nano GGUF runtime: install a prebuilt FunASR llama.cpp release
# and ensure `llama-funasr-cli` is on PATH.
```

## 4. Run with manually installed local paths

```bash
export ECHOMEMORY_ASR_MODEL="$PWD/models/faster-whisper-small.en"
export ECHOMEMORY_EMBEDDING_MODEL="$PWD/models/all-MiniLM-L6-v2"
# Optional: export ECHOMEMORY_LLM_MODEL="$PWD/models/qwen2.5-3b-instruct-q4_k_m.gguf"
python -m uvicorn app.main:app
```

Once the assets are present, disconnecting the network does not change app behavior.
Use `tiny.en` only on slower machines. The in-app installer’s Small English Whisper model is the recommended default for responsive conversation transcription.
