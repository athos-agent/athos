"""Learning from the person's own edits: the agent writes a file while following a piece, the person then changes it
by hand before sending it on, and that change is often an unspoken rule of their way of working.

When the agent writes or edits a text file during a task that follows a piece, the tool hook keeps the file as the
agent left it (`<home>/snapshots/<session>/<hash>.txt`, plus `index.json`: path, pieces, current step, task). On the
person's next request in that session, each snapshot is compared with the file on disk; a file the person changed
gets a short diff and an instruction for the model: propose the rule in one line and ask before saving. The snapshot is
then forgotten, so each edit is offered once. Everything stays local; snapshots are deleted after use and kept only
for the last few tasks, under a size cap.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

from athos import paths, session, store

FILE_CAP = 200_000         # bigger files are not snapshotted: a contract or a report fits, a dataset does not
SESSION_CAP = 2_000_000    # all snapshots of one session; the oldest go first
KEEP_TASKS = 3             # snapshots of older tasks are dropped
DIFF_LINES = 60
PER_PROMPT = 2             # files offered with one request; the rest wait for the next one
# The tools that write a file, in each agent's names (capture.EDIT_TOOLS, without notebooks).
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "apply_patch", "write_file", "edit_file", "write", "edit", "patch",
               "multiedit"}
# Codex's apply_patch names its files inside the patch text.
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$|^\*\*\* Move to: (.+)$", re.MULTILINE)


def _dir(session_id: str) -> Path:
    return paths.home() / "snapshots" / re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "default")


def _index(session_id: str) -> list[dict]:
    try:
        return json.loads((_dir(session_id) / "index.json").read_text())
    except (OSError, ValueError):
        return []


def _save_index(session_id: str, entries: list[dict]) -> None:
    d = _dir(session_id)
    if not entries:
        shutil.rmtree(d, ignore_errors=True)
        return
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.json").write_text(json.dumps(entries, indent=1, ensure_ascii=False))


def _text(path: Path) -> str | None:
    """The file's text, or None for a missing, binary or too large file."""
    try:
        if not path.is_file() or path.stat().st_size > FILE_CAP:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def written_paths(event: dict) -> list[Path]:
    """The files a tool call wrote, absolute (relative paths are taken from the event's folder)."""
    if (event.get("tool_name") or "") not in WRITE_TOOLS:
        return []
    tin = event.get("tool_input") or {}
    found = [str(tin[k]) for k in ("file_path", "path", "filePath") if tin.get(k)]
    for k in ("command", "patch", "input", "patchText"):
        v = tin.get(k)
        text = " ".join(map(str, v)) if isinstance(v, list) else str(v or "")
        found += [(m.group(1) or m.group(2)).strip() for m in PATCH_FILE.finditer(text)]
    cwd = Path(event.get("cwd") or os.getcwd())
    out = []
    for f in found:
        p = Path(os.path.expanduser(f))
        p = p if p.is_absolute() else cwd / p
        if p not in out:
            out.append(p)
    return out


def _following(state: dict) -> tuple[list[str], str | None]:
    """The pieces the task follows (loaded, or walked step by step) and the step it is on, if any."""
    trail = state.get("trail") or []
    pieces = list(state.get("task_loaded") or [])
    for x in trail:
        if x.get("piece") and x["piece"] not in pieces:
            pieces.append(x["piece"])
    now = next((f"{x['piece']}#{x['step']}" for x in reversed(trail) if x.get("kind") == "step" and not x.get("done")),
               None)
    return pieces, now


def on_tool(event: dict, session_id: str) -> None:
    """PostToolUse: keep each file the agent just wrote, as it left it, when the task follows a piece."""
    files = written_paths(event)
    if not files:
        return
    state = session.load(session_id)
    pieces, now = _following(state)
    if not pieces:
        return
    kh = str(paths.know_how())
    entries = _index(session_id)
    for path in files:
        if str(path).startswith(kh):          # a piece written by hand is Athos's, not the person's work
            continue
        text = _text(path)
        if text is None:
            continue
        h = hashlib.sha1(str(path).encode()).hexdigest()[:16]
        d = _dir(session_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{h}.txt").write_text(text)
        entries = [e for e in entries if e["hash"] != h]
        entries.append({"path": str(path), "hash": h, "pieces": pieces, "statement": now,
                        "task_id": state.get("task_id"), "at": round(time.time(), 1), "size": len(text)})
    _prune(session_id, entries)


def _prune(session_id: str, entries: list[dict]) -> None:
    """Only the last few tasks, and under the session's size cap (newest kept)."""
    tasks: list = []
    for e in reversed(entries):
        if e.get("task_id") not in tasks:
            tasks.append(e.get("task_id"))
    keep, size = [], 0
    for e in reversed(entries):
        if e.get("task_id") in tasks[:KEEP_TASKS] and size + e.get("size", 0) <= SESSION_CAP:
            keep.append(e)
            size += e.get("size", 0)
    keep.reverse()
    for e in entries:
        if e not in keep:
            _forget(session_id, e)
    _save_index(session_id, keep)


def _forget(session_id: str, entry: dict) -> None:
    try:
        (_dir(session_id) / f"{entry['hash']}.txt").unlink()
    except OSError:
        pass


def diff(before: str, after: str, name: str) -> str:
    """A compact unified diff, at most DIFF_LINES lines."""
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"{name} (as you wrote it)",
                                      f"{name} (as the person left it)", n=1, lineterm=""))
    if len(lines) > DIFF_LINES:
        lines = lines[:DIFF_LINES] + [f"… ({len(lines) - DIFF_LINES} more lines)"]
    return "\n".join(lines)


def _same(a: str, b: str) -> bool:
    """Equal but for whitespace: not worth a word."""
    return a.split() == b.split()


def check(session_id: str) -> list[dict]:
    """The files the person changed since the agent wrote them: each with its diff, the piece and the step. Their
    snapshots are forgotten (offered once); files not changed yet stay for a later request."""
    entries = _index(session_id)
    found, keep = [], []
    for e in entries:
        try:
            before = (_dir(session_id) / f"{e['hash']}.txt").read_text()
        except OSError:
            continue
        after = _text(Path(e["path"]))
        if after is None:                        # deleted, or no longer text: nothing to learn from
            _forget(session_id, e)
            continue
        if after == before or len(found) >= PER_PROMPT:
            keep.append(e)
            continue
        _forget(session_id, e)
        if _same(before, after):
            continue
        stmt = e.get("statement") or ""
        pid = stmt.partition("#")[0] or (e.get("pieces") or [""])[0]
        p = store.get(pid)
        found.append({"file": e["path"], "name": os.path.basename(e["path"]), "piece": pid,
                      "title": p.title if p else pid, "statement": stmt.partition("#")[2] or None,
                      "task_id": e.get("task_id"), "diff": diff(before, after, os.path.basename(e["path"]))})
    _save_index(session_id, keep)
    return found


def model_text(found: list[dict], cmd: str = "athos") -> str:
    """What the model is told about the person's edits."""
    if not found:
        return ""
    parts = ["# Athos — the person edited what you wrote\n"]
    for f in found:
        where = f"step `{f['piece']}#{f['statement']}`" if f["statement"] else f"the piece `{f['piece']}`"
        parts.append(f"The person edited `{f['file']}` after you wrote it, while following «{f['title']}» "
                     f"({where}):\n\n```diff\n{f['diff']}\n```\n")
    parts.append(f"If an edit shows a rule of their way of working (for example: always imperative verbs in penalty "
                 f"clauses), propose it in one line, in the person's language, naming the step of «{found[0]['title']}» "
                 f"it belongs to, and ask whether to add it; do it before or after answering their request, briefly. "
                 f"Never save it without their yes. If they say yes, save it the way an `Athos · adjust "
                 f"<piece>#<step>` request does: read the piece with `{cmd} show <id>`, then `{cmd} save` with its "
                 f"`id:` and a `note:`, sending every statement with only that step changed (or one new statement). "
                 f"If the edit is trivial (a typo, spacing, a single word with no pattern), say nothing about it.\n")
    return "\n".join(parts)


def on_prompt(event: dict, cmd: str = "athos") -> str:
    """UserPromptSubmit, after the new task started: the person's edits since the agent's last writes, told to the
    model, and kept in the session (`learned_from_edit`) for the panels."""
    sid = event.get("session_id", "default")
    found = check(sid)
    if not found:
        return ""
    from athos import eval as ev
    task_id = session.load(sid).get("task_id")
    notes = [{k: f[k] for k in ("file", "name", "piece", "title", "statement")} for f in found]
    session.update(sid, learned_from_edit={"task_id": task_id, "files": notes})
    for n in notes:
        ev.append({"type": "learned_from_edit", "session_id": sid, "task_id": task_id, "at": ev._iso(ev.now()), **n})
    return model_text(found, cmd)
