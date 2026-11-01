"""Per-session scratch state for the hooks.

Each session owns one JSON file, `<home>/sessions/<session_id>.json`. It records things such as the model in use,
the number of tool calls since the last capture, and the ids of pieces loaded or saved during the session. Missing or
damaged files simply read as an empty state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from athos import paths

UNKNOWN_MODEL = "unknown"
_TRANSCRIPT_TAIL = 400          # only the last lines of a transcript are searched for the model
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]")
_UNREADABLE = (OSError, UnicodeError)      # missing, unreadable, or not text


def _file(session_id: str) -> Path:
    """State file for a session; characters that are unsafe in a filename become `_`."""
    name = _UNSAFE_CHARS.sub("_", session_id or "default")
    return paths.sessions() / (name + ".json")


def load(session_id: str) -> dict:
    """The stored state of a session, `{}` when there is none or it cannot be read."""
    try:
        raw = _file(session_id).read_text()
    except _UNREADABLE:
        raw = ""
    try:
        state = json.loads(raw) if raw else {}
    except json.JSONDecodeError:        # a damaged file is treated as empty
        state = {}
    return state


def save(session_id: str, state: dict) -> None:
    """Replace a session's state with `state`."""
    target = _file(session_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=1))


def update(session_id: str, **changes) -> dict:
    """Merge `changes` into a session's state, store it and hand back the merged state."""
    merged = {**load(session_id), **changes}
    save(session_id, merged)
    return merged


def _model_in(line: str) -> str | None:
    """The model named by one transcript line, if the line is a message that carries a real model name."""
    try:
        message = json.loads(line).get("message")
    except json.JSONDecodeError:
        return None
    if not isinstance(message, dict):
        return None
    model = message.get("model")
    if isinstance(model, str) and not model.startswith("<"):    # placeholders such as "<synthetic>" do not count
        return model
    return None


def model_from_transcript(transcript_path: str | None) -> str:
    """Model of the latest message in a transcript, or "unknown".

    The transcript layout belongs to the host platform and can change without notice, so an unreadable file or
    lines that are not JSON just yield "unknown"."""
    tail = _last_lines(transcript_path) if transcript_path else []
    for line in reversed(tail):
        found = _model_in(line)
        if found is not None:
            return found
    return UNKNOWN_MODEL


def _last_lines(path: str) -> list[str]:
    """The final lines of a text file (undecodable bytes dropped), or [] when it cannot be opened."""
    try:
        with open(path, errors="ignore") as fh:
            return fh.readlines()[-_TRANSCRIPT_TAIL:]
    except _UNREADABLE:
        return []
