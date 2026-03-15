"""JSON persistence for sessions at ~/.sam/sessions/."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sam.config import SESSIONS_DIR


def _ensure_dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def save_session(
    session_id: str,
    messages: list[dict],
    model: str,
    working_dir: str,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save session to disk."""
    _ensure_dir()
    path = SESSIONS_DIR / f"{session_id}.json"

    # Load existing to preserve created_at
    existing = load_session(session_id)
    created_at = existing.get("created_at", time.time()) if existing else time.time()

    data = {
        "session_id": session_id,
        "model": model,
        "working_dir": working_dir,
        "messages": messages,
        "created_at": created_at,
        "updated_at": time.time(),
        "metadata": metadata or {},
    }

    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_session(session_id: str) -> dict | None:
    """Load a session from disk."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


