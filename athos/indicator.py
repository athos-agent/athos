"""What the person sees of Athos: one state, computed here and nowhere else.

    learning        the session runs on a frontier model with autonomous learning on, no piece is in use for the
                    task, and Athos is gathering evidence for the task in progress (the task did work, or a
                    verification or a commit was seen), or a save or an independent verifier run this session
                    started is under way
    collaborating   a piece is in use for the task in progress: delivered to an apply model, or opened by a frontier
                    model from the index; it stays on until the task ends
    idle            everything else: Athos switched off, nothing matched, a read-only question, between tasks

`collaborating` wins over `learning`. The state is polled by the hooks module (`athos status --ui`), so it reads a
few small files and never writes, except once when the state changes: then the session's `sessions/ui/<id>.json`
is replaced and one `ui` audit event is written.

Which interface the person gets (`mode`): `minimal`, the default, draws only that state (a small red or green square
with a few words) and keeps every other Athos line out of sight; `classic` brings back the old interface (status
line, trail pane, band with buttons, toasts, and the hook lines the person used to read). It is read from the
ATHOS_UI environment variable, then from `"ui"` in `<home>/config.json`.
"""

from __future__ import annotations

import json
import os
import time

from athos import session

LEARNING, COLLABORATING, IDLE = "learning", "collaborating", "idle"
MINIMAL, CLASSIC = "minimal", "classic"
MODES = (MINIMAL, CLASSIC)
STALE_S = 20 * 60          # a task whose session has not moved for this long is not shown as in progress (an
#                            interrupted turn never reaches the Stop hook)


def mode() -> str:
    """`minimal` or `classic`: ATHOS_UI first, then `"ui"` in config.json, then `minimal`."""
    env = os.environ.get("ATHOS_UI", "").strip().lower()
    if env in MODES:
        return env
    from athos import start
    saved = start.config()
    value = saved.get("ui") if isinstance(saved, dict) else None
    if isinstance(value, str) and value.strip().lower() in MODES:
        return value.strip().lower()
    return MINIMAL


def minimal() -> bool:
    return mode() == MINIMAL


def _off() -> bool:
    return os.environ.get("ATHOS_HOOKS", "").lower() in ("off", "0", "false", "no")


def _fresh(sid: str) -> bool:
    """Whether the session's state moved recently (any hook writes it)."""
    try:
        return time.time() - session._file(sid).stat().st_mtime < STALE_S
    except OSError:
        return False


def compute(sid: str | None, state: dict | None = None) -> tuple[str, str]:
    """The state and a short machine-readable reason: (`learning`|`collaborating`|`idle`, why)."""
    if _off():
        return IDLE, "off"
    if not sid:
        return IDLE, "no_session"
    state = session.load(sid) if state is None else state
    task = state.get("task_id")
    ended = (state.get("task_end") or {}).get("task_id") == task
    working = bool(task) and not ended and _fresh(sid)
    if working and state.get("task_loaded"):
        delivered = state.get("task_delivery") == "piece" and any(
            p not in (state.get("task_opened") or []) for p in state["task_loaded"])
        return COLLABORATING, "piece_delivered" if delivered else "piece_opened"
    from athos import autolearn
    if autolearn.autonomous_state(state):
        if working:
            from athos import evidence
            if evidence.of_task(task):
                return LEARNING, "gathering_evidence"
            if state.get("work_since_capture") or state.get("edits_since_capture"):
                return LEARNING, "task_with_work"
        asked = state.get("auto_ask") or {}
        if asked.get("task_id") == task and asked.get("ask") == "stop" and not asked.get("answered") \
                and not asked.get("closed") and _fresh(sid):
            return LEARNING, "save_asked"
        since = state.get("verifying_since")
        if since:
            from athos import verify
            if verify.running_since(float(since)):
                return LEARNING, "verifying"
    if not task:
        return IDLE, "no_task"
    if not working:
        return IDLE, "between_tasks" if ended else "stale_task"
    return IDLE, "nothing_in_use"


def _file(sid: str):
    """sessions/ui/<session>.json: the last state recorded, beside (not among) the session files."""
    own = session._file(sid)
    return own.parent / "ui" / own.name


def observe(sid: str | None, state: dict | None = None, project: str | None = None) -> dict:
    """Compute the state and, only when it differs from the last one recorded for the session, record it: the
    session's `sessions/ui/<id>.json` and one `ui` audit event. Returns {state, why}."""
    now, why = compute(sid, state)
    out = {"state": now, "why": why}
    if not sid:
        return out
    target = _file(sid)
    try:
        before = json.loads(target.read_text())
    except (OSError, ValueError):
        before = {}
    if ((before.get("state") if isinstance(before, dict) else None) or IDLE) == now:
        return out                            # no record yet counts as idle: the first idle is no change
    try:
        import fcntl
    except ImportError:                       # no file locks here: a rare duplicate event at worst
        fcntl = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target.with_suffix(".lock"), "w") as lock:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                before = json.loads(target.read_text())
            except (OSError, ValueError):
                before = {}
            before = before if isinstance(before, dict) else {}
            if (before.get("state") or IDLE) == now:     # another process recorded this change first
                return out
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps({"state": now, "why": why, "at": time.time()}))
            os.replace(tmp, target)
    except OSError:
        return out
    from athos import eval as ev
    st = session.load(sid) if state is None else state
    project = project or st.get("project")
    ev.audit({"type": "ui", "session_id": sid, "task_id": st.get("task_id"), "state": now, "why": why,
              "from": before.get("state") or IDLE, "mode": mode(), "project": project},
             line=f"{before.get('state') or IDLE} → {now} ({why})", project=project)
    return out


def for_folder(cwd: str) -> str | None:
    """The session the hooks last noted for a folder (its by-cwd note), or None."""
    from athos import cli
    return cli._current_session(cwd).get("session_id")


def brief(cwd: str) -> dict:
    """What the minimal interface reads: the state, why, the interface mode and the person's language."""
    from athos import start
    return {**observe(for_folder(cwd)), "ui": mode(), "lang": start.lang()}

