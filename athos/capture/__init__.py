"""Capture: when a task ends, Claude itself writes down the know-how it used, as one piece.

The Stop hook does not extract anything on its own and calls no model: when enough work happened since the last
capture, it asks Claude (who has the whole context) to decide whether the task taught something reusable and, if so,
to save it with `athos save`. Nothing new leaves the machine.
"""

from __future__ import annotations

import os
import re

from athos import eval as ev, paths, session, store

THRESHOLD = 3          # tool calls since the last capture before a Stop asks for one (a release took 3)

FORMAT = """{cmd} save <<'EOF'
---
title: <short imperative title>
when: <the situation this applies to, specific enough to match a future request>
id: <only to improve an existing piece: its id>
note: <only when improving: what changed and why>
---
## #<statement_id>
**When:** <the moment in the task this step applies, as you would recognise it mid-task>
**Do:** <the action, concrete enough to check: a command, a file, a question to the person, a refusal>
**Because:** <the reason or the evidence: an incident, a measurement, the person's decision>
**Links:** <[[page#statement]] of what applies next or alongside, in this piece or another one>

## #<next_statement_id>
...
EOF

One statement per step, in the order the task goes. Keep the person's exact conventions verbatim (names, message
formats, paths, flags); never turn them into placeholders. No secrets, tokens or personal data. Links are the
trajectory: link a statement to the one applied right after it or with it in this task, including statements of
other pieces loaded in this session; never link by topic alone. When improving an old piece written as numbered steps,
rewrite it as statements."""


GUIDE = """## Saving know-how (Athos)

When a task in this session teaches something reusable (how it was solved, the criteria, the steps, the mistakes
avoided), Athos's Stop hook asks once with a short line. Then either save exactly one piece by running:

{format}

or, if nothing reusable came out of it, just stop. If a piece already loaded in this session covers the task, improve
it (its `id:` and a `note:`) instead of creating a new one. Don't announce the save in your answer and don't print the
piece: Athos itself shows the user one line with what was saved and where it is available."""


def guide(cmd: str = "athos") -> str:
    """The capture instructions, given once at session start (out of the user's sight) so the Stop hook can be short."""
    return GUIDE.format(format=FORMAT.format(cmd=cmd))


def origin_for(session_id: str, transcript_path: str | None = None) -> dict:
    state = session.load(session_id)
    model = state.get("model") or session.model_from_transcript(transcript_path)
    return {"platform": state.get("platform", "claude-code"), "model": model}


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
    ev.note_saved(session_id, piece.id)
    from athos import wiki
    try:
        rebuilt = wiki.rebuild()
        if wiki.agents_target():
            wiki.install_agents(wiki.agents_target())
    except OSError:
        rebuilt = None
    state = session.load(session_id)
    state["last_saved"] = {"id": piece.id, "title": piece.title, "version": piece.version,
                           "platforms": ["Claude Code", *sync_other_agents()]}
    state["wiki"] = rebuilt and {"broken": rebuilt["lint"]["broken"], "agents": rebuilt["agents"]}
    session.save(session_id, state)
    return piece, diff


def sync_other_agents() -> list[str]:
    """Where the new piece is also ready: once the person exported the know-how for Codex and Muse Code (both read
    ~/.agents/skills), every save refreshes that export, so the piece is there with no extra step."""
    from athos.adapters import codex
    d = codex.skills_dir()
    try:
        if not any(x.name.startswith(codex.SKILL_PREFIX) for x in d.iterdir()):
            return []
        codex.export_skills(d)
    except OSError:
        return []
    return ["Codex", "Muse Code"]


def _counts(event: dict) -> bool:
    """Only the main conversation's own work counts: a subagent's tool calls (a background agent included) fire the
    hook with the parent's session id, and Athos's own commands are not work to capture."""
    if event.get("agent_id"):
        return False
    cmd = str((event.get("tool_input") or {}).get("command", ""))
    return not re.search(r"(^|[\s/])athos(\s|$)", cmd)


def count_tool(event: dict) -> None:
    if not _counts(event):
        return
    sid = event.get("session_id", "default")
    state = session.load(sid)
    state["tools_since_capture"] = state.get("tools_since_capture", 0) + 1
    session.save(sid, state)


def enabled() -> bool:
    return os.environ.get("ATHOS_CAPTURE", "").lower() not in ("off", "0", "false", "no")


def stop_decision(event: dict, cmd: str = "athos") -> dict | None:
    """The Stop hook's answer: `{"decision": "block", "reason": ...}` asks Claude to capture; None lets it stop."""
    if not enabled():
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
    if state.get("guide"):
        # One short line: the full instructions went in at session start, out of the user's sight (and again after a
        # compaction, which starts the session anew).
        return {"decision": "block",
                "reason": f"Athos: anything reusable to keep? Save or improve one piece with `{cmd} save` as the "
                          f"session guide says, or just stop."}
    used = state.get("loaded", [])
    improve = (f" Pieces loaded in this session: {', '.join(used)}. If this task refined one of them, improve it "
               f"(give its id and a note) instead of creating a duplicate.") if used else ""
    reason = ("Athos: before you stop, decide whether this task taught reusable know-how: how it was solved, the "
              "criteria, the steps, the mistakes avoided. If it did not, just stop. If it did, save exactly one piece "
              "by running:\n\n" + FORMAT.format(cmd=cmd) + "\n\nDon't announce it: Athos shows the user what was "
              "saved." + improve)
    return {"decision": "block", "reason": reason}
