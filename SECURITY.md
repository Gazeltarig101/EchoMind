# Security

EchoMemory is designed for local-first use, but it can still handle sensitive
voice memories and API credentials. Please follow these rules when developing
or publishing the project:

- Never commit `data/`, `models/`, `.local/`, `.venv/`, SQLite files, or `.env` files.
- Never put a Sarvam API key in source code, documentation, screenshots, issues,
  tests, or example configuration. The UI stores it in the local user data directory.
- Run `python scripts/check_public_repo.py` before creating a public commit.
- If a secret is ever committed, revoke it immediately and remove it from the
  repository history; adding it to `.gitignore` does not remove an existing commit.

The application stores downloaded models and memory data locally. Sarvam speech
is the only optional cloud provider and is enabled only after the user enters a
key in the UI.
