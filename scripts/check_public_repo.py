"""Fail if tracked files contain runtime data, credentials, or model artifacts."""

from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path


FORBIDDEN_PREFIXES = ("data/", "models/", ".local/", ".venv/")
FORBIDDEN_NAMES = {".env", "sarvam_api_key", "echomemory.sqlite3"}
SECRET_PATTERNS = (
    re.compile(r"BEGIN [A-Z ]+ PRIVATE KEY", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),
    re.compile(r"\bapi[_-]?key\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
)


def tracked_files(root: Path) -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=root, stderr=subprocess.STDOUT
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Run this check from an initialized Git checkout.") from exc
    return [root / item for item in output.decode().split("\0") if item]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        files = tracked_files(root)
    except RuntimeError as exc:
        print(f"Public-repository check unavailable: {exc}")
        return 2
    violations: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if any(relative.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            violations.append(f"tracked runtime path: {relative}")
            continue
        if path.name in FORBIDDEN_NAMES or path.suffix in {".sqlite3", ".db"}:
            violations.append(f"tracked sensitive file: {relative}")
            continue
        if relative == "scripts/check_public_repo.py":
            continue
        if path.is_file() and path.stat().st_size < 2_000_000:
            text = path.read_text(errors="ignore")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                violations.append(f"possible credential marker: {relative}")

    if violations:
        print("Public-repository check failed:")
        print("\n".join(f"- {item}" for item in violations))
        return 1
    print(f"Public-repository check passed ({len(files)} tracked files inspected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
