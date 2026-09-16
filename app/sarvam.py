"""Small local configuration helper for the optional Sarvam AI integration."""
import os
from pathlib import Path

import json
from .config import ROOT, SARVAM_API_KEY_PATH, SARVAM_SETTINGS_PATH

LEGACY_API_KEY_PATH = ROOT / "data" / "sarvam_api_key"
LEGACY_SETTINGS_PATH = ROOT / "data" / "sarvam_settings.json"


def load_api_key() -> str:
    try:
        return SARVAM_API_KEY_PATH.read_text().strip()
    except OSError:
        # Migrate an older project-local key only when it belongs to this OS
        # user. A different user opening the same checkout cannot inherit it.
        try:
            getuid = getattr(os, "getuid", None)
            if getuid is not None and LEGACY_API_KEY_PATH.stat().st_uid != getuid():
                return ""
            value = LEGACY_API_KEY_PATH.read_text().strip()
            if value:
                save_api_key(value)
            return value
        except OSError:
            return ""


def save_api_key(api_key: str) -> None:
    SARVAM_API_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with __import__("contextlib").suppress(OSError):
        os.chmod(SARVAM_API_KEY_PATH.parent, 0o700)
    SARVAM_API_KEY_PATH.write_text(api_key.strip())
    # The key is only intended for this local user. Best effort is deliberate:
    # some platforms do not expose POSIX permissions.
    with __import__("contextlib").suppress(OSError):
        os.chmod(SARVAM_API_KEY_PATH, 0o600)

def load_language_code() -> str:
    try:
        value = json.loads(SARVAM_SETTINGS_PATH.read_text()).get("language_code", "unknown")
        return value if isinstance(value, str) else "unknown"
    except (OSError, json.JSONDecodeError):
        try:
            value = json.loads(LEGACY_SETTINGS_PATH.read_text()).get("language_code", "unknown")
            return value if isinstance(value, str) else "unknown"
        except (OSError, json.JSONDecodeError):
            return "unknown"

def save_language_code(language_code: str) -> None:
    SARVAM_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with __import__("contextlib").suppress(OSError):
        os.chmod(SARVAM_SETTINGS_PATH.parent, 0o700)
    SARVAM_SETTINGS_PATH.write_text(json.dumps({"language_code": language_code}))
    with __import__("contextlib").suppress(OSError):
        os.chmod(SARVAM_SETTINGS_PATH, 0o600)
