"""Cases: the tasks a person marked, kept as examples of their own work with a piece of know-how.

    <home>/cases/<piece-id>/<task-id>.json
        task_id, piece, version   the task and the piece (and its version) it loaded
        request, answer           the whole request, and the agent's final answer (None when it could not be read)
        mark                      ok, corrected or failed
        correction                for a corrected task: what the person said next to fix it

Only tasks that loaded a piece and were marked become cases, and they stay on this machine. A corrected case is a test
of the piece: the request, and what the person had to correct (`athos test`). A good one is a reference answer a
cheaper model can be compared with (`athos shadow`).

When a task ends, what a case needs waits in the session's state (`case`); the mark writes it out.
"""

from __future__ import annotations

import json
import re

from athos import paths, session, store

MAX_TEXT = 20000           # an answer longer than this is cut: a case is an example, not an archive


def root():
    return paths.home() / "cases"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "_")


def _file(piece_id: str, task_id: str):
    return root() / _safe(piece_id) / f"{_safe(task_id)}.json"


# ------------------------------------------------------------------------------------------------ the answer
def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type") in ("text", "output_text")).strip()
    return ""


def answer_from_transcript(path: str | None) -> str | None:
    """The last text the assistant wrote, from a Claude Code transcript (JSONL, `message.content`) or a Codex rollout
    (`response_item` messages). The formats are the platforms' own, so this is best effort: None when unreadable."""
    if not path:
        return None
    from athos.adapters import codex
    try:
        fh = codex._open_rollout(path)                 # plain files too; Codex compresses old rollouts
    except (OSError, ImportError):
        return None
    last = None
    with fh:
        for line in fh:
            if '"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            msg = o.get("message") if isinstance(o.get("message"), dict) else None
            p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
            if msg and msg.get("role") == "assistant":
                text = _text(msg.get("content"))
            elif o.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "assistant":
                text = _text(p.get("content"))
            else:
                continue
            if text.strip():
                last = text.strip()
    return last[:MAX_TEXT] if last else None


def last_answer(event: dict) -> str | None:
    """The agent's final answer: the Stop event's own copy when it sends one (Claude Code, Codex), else the transcript."""
    given = event.get("last_assistant_message")
    if isinstance(given, str) and given.strip():
        return given.strip()[:MAX_TEXT]
    try:
        return answer_from_transcript(event.get("transcript_path"))
    except OSError:
        return None


# ------------------------------------------------------------------------------------------------ recording
def on_task_end(event: dict, rec: dict | None) -> None:
    """Stop: keep what a case of this task would need, in the session, until the person marks it."""
    if not rec or not rec.get("pieces"):
        return
    sid = event.get("session_id", "default")
    state = session.load(sid)
    old = state.get("case") or {}
    if old.get("task_id") == rec["task_id"] and old.get("answer"):
        return             # a second end of the same task is Athos's own capture turn, not the answer the person judged
    versions = {pid: p.version for pid in rec["pieces"] if (p := store.get(pid))}
    if not versions:
        return
    state["case"] = {"task_id": rec["task_id"], "request": state.get("case_request") or state.get("task_request", ""),
                     "answer": last_answer(event), "pieces": versions, "platform": state.get("platform"),
                     "model": rec.get("model"), "at": rec.get("at")}
    session.save(sid, state)


def _draft(task_id: str, session_id: str | None) -> tuple[str | None, dict | None]:
    """The session holding this task's draft case: the one named first, else any (a mark from `athos watch` or from
    another folder doesn't say which session the task was in)."""
    if session_id and (session.load(session_id).get("case") or {}).get("task_id") == task_id:
        return session_id, session.load(session_id)["case"]
    for f in paths.sessions().glob("*.json"):
        try:
            draft = json.loads(f.read_text()).get("case") or {}
        except (OSError, ValueError):
            continue
        if draft.get("task_id") == task_id:
            return f.stem, draft
    return None, None


def _write(data: dict) -> None:
    f = _file(data["piece"], data["task_id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def on_mark(task_id: str, result: str, session_id: str | None = None, correction: str | None = None) -> int:
    """A task was marked: write its case (one per piece it loaded) or update the mark of one already written. A
    corrected task with no correction yet waits for the person's next words. Returns the cases touched."""
    sid, draft = _draft(task_id, session_id)
    kept = {f.parent.name: f for f in root().glob(f"*/{_safe(task_id)}.json")}
    touched = 0
    for pid, version in ((draft or {}).get("pieces") or {}).items():
        if _safe(pid) not in kept:
            _write({"task_id": task_id, "piece": pid, "version": version, "request": draft.get("request", ""),
                    "answer": draft.get("answer"), "mark": result, "correction": correction,
                    "platform": draft.get("platform"), "model": draft.get("model"), "at": draft.get("at")})
            touched += 1
    for f in kept.values():
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        data["mark"] = result
        if correction:
            data["correction"] = correction
        _write(data)
        touched += 1
    if touched and sid and result == "corrected" and not correction:
        session.update(sid, await_correction=task_id)
    return touched


def note_prompt(session_id: str, prompt: str) -> bool:
    """The person's next request after `athos mark c` is their correction: kept with the case it corrects."""
    state = session.load(session_id)
    tid = state.get("await_correction")
    if not tid:
        return False
    state["await_correction"] = None
    session.save(session_id, state)
    text = (prompt or "").strip()
    if not text:
        return False
    for f in root().glob(f"*/{_safe(tid)}.json"):
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if data.get("mark") == "corrected" and not data.get("correction"):
            data["correction"] = text[:MAX_TEXT]
            _write(data)
    return True


# ------------------------------------------------------------------------------------------------ reading
def all_cases(piece_id: str | None = None) -> list[dict]:
    out = []
    for f in root().glob(f"{_safe(piece_id) if piece_id else '*'}/*.json"):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda c: c.get("at") or "")


def tests(piece_id: str) -> list[dict]:
    """The corrected cases of a piece that say what was corrected: each one a test of its current version."""
    return [c for c in all_cases(piece_id) if c.get("mark") == "corrected" and c.get("correction") and c.get("request")]


def references(piece_id: str | None = None) -> list[dict]:
    """The good cases with an answer: what the person approved, to compare a cheaper model with."""
    return [c for c in all_cases(piece_id) if c.get("mark") == "ok" and c.get("answer") and c.get("request")]
