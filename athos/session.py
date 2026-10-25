"""Small per-session state, kept under `<home>/sessions/<session_id>.json`: the model the session runs on, how many
tools ran since the last capture, which pieces were loaded and which were saved."""

from __future__ import annotations

import json
import re

from athos import paths


def _file(session_id: str):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "default")
    return paths.sessions() / f"{safe}.json"


def load(session_id: str) -> dict:
    try:
        return json.loads(_file(session_id).read_text())
    except (OSError, ValueError):
        return {}


def save(session_id: str, state: dict) -> None:
    f = _file(session_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, indent=1))


def update(session_id: str, **changes) -> dict:
    state = load(session_id)
    state.update(changes)
    save(session_id, state)
    return state


def model_from_transcript(transcript_path: str | None) -> str:
    """Best effort: the transcript format is internal to the platform and may change, so any failure is "unknown"."""
    if not transcript_path:
        return "unknown"
    try:
        with open(transcript_path, errors="ignore") as fh:
            lines = fh.readlines()[-400:]
    except OSError:
        return "unknown"
    for line in reversed(lines):
        try:
            msg = json.loads(line).get("message")
        except ValueError:
            continue
        if isinstance(msg, dict) and isinstance(msg.get("model"), str) and not msg["model"].startswith("<"):
            return msg["model"]
    return "unknown"
