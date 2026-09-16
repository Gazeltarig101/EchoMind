# EchoMemory

EchoMemory is a local-first voice memory assistant. It captures speech in the
browser, transcribes it with a local model, stores memories in SQLite, and
searches them locally. The optional Sarvam integration is the only cloud speech
provider and is enabled only when the user supplies a key in the UI.

## Features

- Local browser microphone capture with live transcript updates.
- SQLite memory storage with local semantic search and a deterministic fallback.
- Explicit model downloads from the Local model setup panel; no model library
  silently downloads weights.
- Optional local GGUF chat models for grounded answers and transcript cleanup.
- Sarvam Saaras v3 support for Indian-language speech when explicitly configured.

## Requirements

- Python 3.12–3.14 on macOS or Windows.
- 4 GB RAM for the basic app; additional memory is needed for larger models.
- Docker Desktop 4.x or newer for the container workflow.

The dependency versions in `requirements.txt` were verified in the development
environment (`Python 3.14.3`). The standard install includes the Python
runtimes used by the built-in Whisper, embeddings, and local GGUF chat cards.
Model weights are not bundled with the repository.

## macOS installation

```bash
git clone https://github.com/nirbhay41120003/EchoMind.git
cd EchoMind
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>, allow microphone access, and use **More → Local
model setup** to download the recommended Whisper and embeddings models. Local
model files are stored under `models/`; memory data and settings are stored under
`data/` or the OS user data directory. Both locations are ignored by Git.

On Apple Silicon, `llama-cpp-python` may use a prebuilt wheel or compile locally.
If compilation is required, install Apple’s command-line tools first:

```bash
xcode-select --install
```

## Windows installation

Open PowerShell:

```powershell
git clone https://github.com/nirbhay41120003/EchoMind.git
Set-Location EchoMind
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> and allow microphone access. If PowerShell blocks
activation for the current session, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Windows users who need to build `llama-cpp-python` locally may also need the
Visual Studio C++ Build Tools and CMake. The core app still starts without a
working local chat runtime and falls back to extractive answers.

## Docker

```bash
docker build -t echomemory .
docker run --rm -p 8000:8000 \
  -v echomemory-data:/app/data \
  -v echomemory-models:/app/models \
  echomemory
```

Open <http://127.0.0.1:8000>. The named volumes preserve the SQLite database,
settings, and downloaded models across container upgrades. The image runs as a
non-root user and installs the same Python dependency set as the local setup.
Browser microphone access works through `localhost` in Docker Desktop.

## Model setup

The recommended setup is downloaded from inside the app after dependencies are
installed. See [MODEL_SETUP.md](MODEL_SETUP.md) for supported model families,
offline setup, and the optional native Nemotron and Fun-ASR runtimes.

The native Nemotron and Fun-ASR executables are platform-specific and are not
silently bundled into the Python requirements or Docker image. Their cards show
the missing runtime instead of crashing the application.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ECHOMEMORY_DB` | `data/echomemory.sqlite3` | SQLite database location |
| `ECHOMEMORY_MODELS_DIR` | `models/` | Downloaded model directory |
| `ECHOMEMORY_ASR_MODEL` | empty | Existing local Whisper model path |
| `ECHOMEMORY_EMBEDDING_MODEL` | empty | Existing local embedding model path |
| `ECHOMEMORY_LLM_MODEL` | empty | Existing local GGUF chat model path |
| `ECHOMEMORY_DEVICE` | `cpu` | ASR device |

Sarvam credentials are entered through the UI and are stored with restrictive
local permissions where the operating system supports them. Never put a real
key in an environment file, screenshot, issue, test, or commit.

## Development and verification

```bash
python -m unittest discover -s tests -v
python scripts/check_public_repo.py
```

The public-repository check requires an initialized Git checkout and rejects
tracked databases, model files, local binaries, environment files, and common
credential markers. Read [SECURITY.md](SECURITY.md) before publishing changes.

## Project layout

```text
app/                    FastAPI server, local inference adapters, and web UI
tests/                  Standard-library unit tests
requirements*.txt       Reproducible Python dependency sets
Dockerfile              Non-root container image
MODEL_SETUP.md          Model downloads and optional native runtimes
SECURITY.md             Public-repository and credential guidance
```
