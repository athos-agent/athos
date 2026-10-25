"""Capture: when a task ends, Claude itself writes down the know-how it used, as one piece.

The Stop hook does not extract anything on its own and calls no model: when enough work happened since the last
capture, it asks Claude (who has the whole context) to decide whether the task taught something reusable and, if so,
to save it with `athos save`. Nothing new leaves the machine.
"""

from __future__ import annotations

import os

from athos import paths, session, store

THRESHOLD = 5          # tool calls since the last capture before a Stop asks for one

FORMAT = """{cmd} save <<'EOF'
---
title: <short imperative title>
when: <the situation this applies to, specific enough to match a future request>
id: <only to improve an existing piece: its id>
note: <only when improving: what changed and why>
---
<how it was solved: steps, criteria, commands, mistakes to avoid. No secrets, tokens or personal data.>
EOF"""


def origin_for(session_id: str, transcript_path: str | None = None) -> dict:
    state = session.load(session_id)
    model = state.get("model") or session.model_from_transcript(transcript_path)
    return {"platform": "claude-code", "model": model}


def save_text(text: str, session_id: str = "default", cwd: str | None = None,
              transcript_path: str | None = None) -> tuple[store.Piece, str | None]:
    """Save a piece written by Claude. With an existing `id` it improves that piece (new version, history line,
    diff returned); otherwise it creates a new one. Raises ValueError when title, when or body is missing."""
    data, body = store.parse_frontmatter(text.strip())
    body = body.strip()
    title, when = data.get("title", "").strip(), data.get("when", "").strip()
    pid = data.get("id", "").strip()
    origin = origin_for(session_id, transcript_path)
    project = paths.project_of(cwd)
    existing = store.get(pid) if pid else None
    if existing is not None:
        if not (body or title or when):
            raise ValueError("nothing to change")
        piece, diff = store.update(pid, data.get("note", ""), body=body or None, title=title or None,
                                   when=when or None, origin=origin, projects=[project])
    else:
        missing = [k for k, v in (("title", title), ("when", when), ("body", body)) if not v]
        if missing:
            raise ValueError("missing " + ", ".join(missing))
        piece, diff = store.create(title, when, body, projects=[project], origin=origin, piece_id=pid or None), None
    state = session.load(session_id)
    state["saved"] = sorted(set(state.get("saved", [])) | {piece.id})
    state["tools_since_capture"] = 0
    session.save(session_id, state)
    return piece, diff


def count_tool(event: dict) -> None:
    sid = event.get("session_id", "default")
    state = session.load(sid)
    state["tools_since_capture"] = state.get("tools_since_capture", 0) + 1
    session.save(sid, state)


def stop_decision(event: dict, cmd: str = "athos") -> dict | None:
    """The Stop hook's answer: `{"decision": "block", "reason": ...}` asks Claude to capture; None lets it stop."""
    if os.environ.get("ATHOS_CAPTURE", "").lower() in ("off", "0", "false", "no"):
        return None
    if event.get("stop_hook_active"):
        return None
    sid = event.get("session_id", "default")
    state = session.load(sid)
    if state.get("tools_since_capture", 0) < THRESHOLD:
        return None
    state["tools_since_capture"] = 0
    state["asked"] = state.get("asked", 0) + 1
    session.save(sid, state)
    used = state.get("loaded", [])
    improve = (f" Pieces loaded in this session: {', '.join(used)}. If this task refined one of them, improve it "
               f"(give its id and a note) instead of creating a duplicate.") if used else ""
    reason = ("Athos: before you stop, decide whether this task taught reusable know-how: how it was solved, the "
              "criteria, the steps, the mistakes avoided. If it did not, reply with one line, \"Athos: nothing to "
              "capture\", and stop. If it did, save exactly one piece by running:\n\n"
              + FORMAT.format(cmd=cmd) + "\n\nThen tell the user in one line which piece was saved." + improve)
    return {"decision": "block", "reason": reason}
