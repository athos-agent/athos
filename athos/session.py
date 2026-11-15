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


def latest_model(transcript_path: str | None, max_bytes: int = 512_000) -> str | None:
    """The model of the latest assistant message in the transcript's last `max_bytes`, or None. For the audit log
    only: it reads a bounded tail, so a long session costs the same as a short one."""
    if not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            tail = fh.read().decode("utf-8", "ignore").splitlines()
    except _UNREADABLE:
        return None
    if size > max_bytes and tail:
        tail = tail[1:]                          # the first line of a cut tail is a fragment
    for line in reversed(tail):
        try:
            found = _model_in(line)
        except AttributeError:                   # a JSON line that is not an object
            continue
        if found is not None:
            return found
    return None


def _last_lines(path: str) -> list[str]:
    """The final lines of a text file (undecodable bytes dropped), or [] when it cannot be opened."""
    try:
        with open(path, errors="ignore") as fh:
            return fh.readlines()[-_TRANSCRIPT_TAIL:]
    except _UNREADABLE:
        return []


def _tail_rows(transcript_path: str | None, max_bytes: int = 512_000) -> list[dict]:
    """The JSON objects in a transcript's last `max_bytes`, oldest first ([] when it cannot be read)."""
    if not transcript_path:
        return []
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except _UNREADABLE:
        return []
    if size > max_bytes and lines:
        lines = lines[1:]                        # the first line of a cut tail is a fragment
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def prompt_origin(transcript_path: str | None, prompt_id: str | None) -> str | None:
    """Who wrote a prompt, as Claude Code's transcript records it on the prompt's entry (`promptId`): "person" for an
    entry whose `origin.kind` is `human` (typed, queued, a suggestion accepted), or Athos's own button pressed by the
    person (`origin.kind` `plugin`, `name` athos, `asUser`); "harness" for anything else the harness sent (a subagent's
    report, a task notification, a meta entry). None when there is no such entry: Claude Code 2.1 writes it only after
    the prompt hook has run, so at prompt time it is usually missing."""
    if not (transcript_path and prompt_id):
        return None
    for row in _tail_rows(transcript_path):
        if row.get("type") != "user" or row.get("promptId") != prompt_id or row.get("toolUseResult") is not None:
            continue
        origin = row.get("origin") if isinstance(row.get("origin"), dict) else {}
        kind = origin.get("kind")
        if row.get("isMeta"):
            return "harness"
        if kind == "human" or (kind is None and row.get("turnOrigin") == "human"):
            return "person"
        if kind == "plugin" and origin.get("name") == "athos" and origin.get("asUser"):
            return "person"
        return "harness"
    return None
