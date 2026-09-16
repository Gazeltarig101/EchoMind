"""Runtime configuration. All model paths are deliberately local filesystem paths."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("ECHOMEMORY_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.getenv("ECHOMEMORY_DB", DATA_DIR / "echomemory.sqlite3"))
MODELS_DIR = Path(os.getenv("ECHOMEMORY_MODELS_DIR", ROOT / "models"))
ASR_SELECTION_PATH = Path(os.getenv("ECHOMEMORY_ASR_SELECTION", DATA_DIR / "active_asr.json"))
LLM_SELECTION_PATH = Path(os.getenv("ECHOMEMORY_LLM_SELECTION", DATA_DIR / "active_llm.json"))
# Credentials belong to the OS user, not to a shared checkout. An explicit
# environment variable remains available for managed or multi-profile setups.
USER_DATA_DIR = Path.home() / ".echomemory"
SARVAM_API_KEY_PATH = Path(os.getenv("ECHOMEMORY_SARVAM_API_KEY", USER_DATA_DIR / "sarvam_api_key"))
SARVAM_SETTINGS_PATH = Path(os.getenv("ECHOMEMORY_SARVAM_SETTINGS", USER_DATA_DIR / "sarvam_settings.json"))

# Set these to directories/files already present on this machine. A blank value keeps
# the corresponding optional component disabled rather than attempting a download.
ASR_MODEL = os.getenv("ECHOMEMORY_ASR_MODEL", "")
EMBEDDING_MODEL = os.getenv("ECHOMEMORY_EMBEDDING_MODEL", "")
LLM_MODEL = os.getenv("ECHOMEMORY_LLM_MODEL", "")
DEVICE = os.getenv("ECHOMEMORY_DEVICE", "cpu")
SAMPLE_RATE = 16_000
# Short utterance windows make speech feel live; the browser asks the server to
# flush sooner at natural pauses, so these are upper bounds for continuous speech.
FINALIZE_SECONDS = 2.5
PARTIAL_SECONDS = 1.0
VOICE_RMS_THRESHOLD = float(os.getenv("ECHOMEMORY_VOICE_RMS_THRESHOLD", "0.008"))
MIN_VOICED_SECONDS = float(os.getenv("ECHOMEMORY_MIN_VOICED_SECONDS", "0.18"))
