"""Learning from the person's own edits: the agent writes a file while following a piece, the person then changes it
by hand before sending it on, and that change is often an unspoken rule of their way of working.

When the agent writes or edits a text file during a task that follows a piece, the tool hook keeps the file as the
agent left it (`<home>/snapshots/<session>/<hash>.txt`, plus `index.json`: path, pieces, current step, the task's best
routed piece, and the file's size and times as last seen). Everything stays local; snapshots are deleted after use and
kept only for the last few tasks, under a size cap.

A change is given to the person only on evidence that no agent tool call made it, and in doubt it is given to nobody.
The agent changes files in many ways besides its edit tools (a script, `sed -i`, a formatter, `git checkout`, a build,
another plugin's hook, a subagent, a task it left running), and until 0.1.111 every one of them read as the person's
edit. So:

- Each tool call's start is stamped by the PreToolUse hook (`session.live_start`): the hook's own clock, never an
  estimate from `duration_ms`. After every tool call (PostToolUse, and PostToolUseFailure where the agent has it) each
  kept file is looked at: a `stat` first, the content only when the stat moved. A changed file is the person's only
  when its status-change time (ctime, which no tool can set back) falls after the previous look, more than GRACE_S
  after the last tool call ended (another plugin's formatter runs right after a write), and clearly before this call's
  stamped start, and while no other tool call, subagent or background task was running. Otherwise it is the agent's
  (the change could have happened during the call) or nobody's.
- On the person's next request each kept file is compared again. A change counts as the person's only when it came
  more than GRACE_S after the agent's turn ended (the Stop hook: another Stop hook may still be writing), with no tool
  call since or still open, no background task left running, and no other session working in the same project since.
- Anything else (no start stamp, a subagent or background task live, a change inside a grace window, a ctime in the
  future, as a network file system's clock may give) is given to nobody: an `edit_seen` event records it as
  `agent_shell`, `agent_tool` or `unexplained` with the reason, and the model is told nothing.

Blind spots, said plainly: a process the agent started in the background that writes after its turn ended is taken for
the person when the Stop hook reported no background task and the grace window has passed; a change made while the
model writes its final answer (after its last tool call, before Stop) is given to nobody; a file the agent never wrote
through a tool Athos can read is not watched; a hand edit followed by the agent's own edit tool on the same file before
any other tool call is folded into the agent's write; an agent with no PreToolUse hook (Codex, OpenCode) only gets the
after-the-turn evidence.

Who the change is credited to (F6): the step the agent was on when it wrote the file; else the best-ranked piece of the
task's route decision; else no piece. Finding the person's edits (`check`) and telling the model about them
(`model_text`) are separate steps, so a later version can learn from them without a word to the model.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import time
from pathlib import Path

from athos import paths, session, store

FILE_CAP = 200_000         # bigger files are not snapshotted: a contract or a report fits, a dataset does not
SESSION_CAP = 2_000_000    # all snapshots of one session; the oldest go first
KEEP_TASKS = 3             # snapshots of older tasks are dropped
DIFF_LINES = 60
PER_PROMPT = 2             # files offered with one request; the rest wait for the next one
MARGIN_S = 1.0             # a change this close to a tool call's start may still be that call's
GRACE_S = 15.0             # a change this soon after a tool call or a turn ended may be a hook's (a formatter's)
SUBAGENT_TOOLS = {"Agent", "Task"}
SHELL_NAMED_MAX = 10       # files a shell command names that are snapshotted with it
# The tools that write a file, in each agent's names (capture.EDIT_TOOLS, without notebooks).
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "apply_patch", "write_file", "edit_file", "write", "edit", "patch",
               "multiedit"}
SHELL_TOOLS = {"Bash", "bash", "shell", "exec_command", "run_shell_command", "local_shell", "BashOutput"}
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
    paths.write_atomic(d / "index.json", json.dumps(entries, indent=1, ensure_ascii=False))


def _clock(session_id: str) -> dict:
    """When the agent's last tool call ended (`tool_end`), when its last turn ended (`turn_end`) and whether it left a
    background task running then (`background`)."""
    try:
        found = json.loads((_dir(session_id) / "clock.json").read_text())
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def _save_clock(session_id: str, **changes) -> None:
    d = _dir(session_id)
    if not (d / "index.json").exists():          # nothing watched: no clock to keep
        return
    with paths.locked(d / "clock.json"):
        paths.write_atomic(d / "clock.json", json.dumps({**_clock(session_id), **changes}))


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


def _stat(path: str) -> list[int] | None:
    """Size, modification and status-change times (ns): what is compared before any content is read."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def _resolve(found: list[str], event: dict) -> list[Path]:
    cwd = Path(event.get("cwd") or os.getcwd())
    out: list[Path] = []
    for f in found:
        p = Path(os.path.expanduser(f))
        p = p if p.is_absolute() else cwd / p
        if p not in out:
            out.append(p)
    return out


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
    return _resolve(found, event)


def is_shell(event: dict) -> bool:
    return (event.get("tool_name") or "") in SHELL_TOOLS


def shell_paths(event: dict) -> list[Path]:
    """The existing files inside the event's folder that a shell command names (a script's output, `sed -i x.md`):
    snapshotted with the command, so a later hand edit of them is seen too. A cheap look at the words, no parsing of
    what the command does."""
    if not is_shell(event):
        return []
    cmd = (event.get("tool_input") or {}).get("command")
    cmd = " ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or "")
    try:
        words = shlex.split(cmd, comments=True)
    except ValueError:
        words = cmd.split()
    cwd = Path(event.get("cwd") or os.getcwd())
    out = []
    for w in words:
        w = w.lstrip(">").rstrip(";")
        if not w or w.startswith("-") or "=" in w or len(out) >= SHELL_NAMED_MAX:
            continue
        p = _resolve([w], event)[0]
        try:
            inside = p.resolve().is_relative_to(cwd.resolve())
        except OSError:
            continue
        if inside and p.is_file() and p not in out:
            out.append(p)
    return out


def _following(state: dict) -> tuple[list[str], str | None]:
    """The pieces the task follows (loaded, or walked step by step) and the step it is on, if any."""
    trail = state.get("trail") or []
    pieces = list(state.get("task_route") or [])
    pieces += [p for p in state.get("task_loaded") or [] if p not in pieces]
    for x in trail:
        if x.get("piece") and x["piece"] not in pieces:
            pieces.append(x["piece"])
    now = next((f"{x['piece']}#{x['step']}" for x in reversed(trail) if x.get("kind") == "step" and not x.get("done")),
               None)
    return pieces, now


def _hash(path: str) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:16]


def _tool_label(event: dict) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", str(event.get("tool_name") or "tool"))[:60]


def call_id(event: dict) -> str | None:
    found = event.get("tool_use_id")
    return str(found) if found else None


def on_tool_start(event: dict, session_id: str, extra: dict | None = None) -> None:
    """PreToolUse: stamp the call's start, whether a subagent makes it, and whether it runs in the background (then
    the session has a task the Stop hook must report finished before a change can be anyone's)."""
    cid = call_id(event)
    tin = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    background = bool(tin.get("run_in_background"))
    if cid:
        session.live_start(session_id, cid, {"at": round(time.time(), 3), "tool": _tool_label(event),
                                             "agent": bool(event.get("agent_id")), "background": background,
                                             **(extra or {})})
    # Kept in the session's state (not with the snapshots, which may not exist yet): a task left running and a
    # subagent's work are what makes a later change nobody's.
    if background:
        session.update(session_id, background_since=round(time.time(), 3))
    if event.get("agent_id") or (event.get("tool_name") or "") in SUBAGENT_TOOLS:
        session.update(session_id, subagent_at=round(time.time(), 3))


def on_tool(event: dict, session_id: str, failed: bool = False, started: dict | None = None) -> None:
    """PostToolUse (and PostToolUseFailure): look at the kept files for changes, then keep each file this call wrote
    (or a shell command named), as it left it, when the task follows a piece. `started` is the call's PreToolUse
    stamp (`session.live_end`), None when the agent has no such hook."""
    now = time.time()
    entries = _index(session_id)
    written = written_paths(event)
    if entries:
        entries = _look(event, session_id, entries, {str(p) for p in written}, now, failed, started)
    state = session.load(session_id)
    pieces, step = _following(state)
    files = [(p, "agent_tool") for p in written]
    if not failed:
        files += [(p, "agent_shell") for p in shell_paths(event) if p not in written]
    if pieces and files:
        entries = _keep(event, session_id, state, entries, files, pieces, step, now)
    if entries or _index(session_id):
        _prune(session_id, entries)
        _save_clock(session_id, tool_end=now)


def _keep(event: dict, session_id: str, state: dict, entries: list[dict], files: list[tuple[Path, str]],
          pieces: list[str], step: str | None, now: float) -> list[dict]:
    kh = str(paths.know_how())
    route = list(state.get("task_route") or [])
    for path, source in files:
        if str(path).startswith(kh):          # a piece written by hand is Athos's, not the person's work
            continue
        text = _text(path)
        if text is None:
            continue
        h = _hash(path)
        old = next((e for e in entries if e["hash"] == h), None)
        if old is not None and source == "agent_shell" and old.get("task_id") == state.get("task_id"):
            continue                          # already watched in this task; `_look` keeps it current
        d = _dir(session_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{h}.txt").write_text(text)
        entries = [e for e in entries if e["hash"] != h]
        entries.append({"path": str(path), "hash": h, "pieces": pieces, "statement": step,
                        "route_best": route[0] if route else None, "task_id": state.get("task_id"),
                        "at": round(now, 3), "checked": now, "stat": _stat(str(path)), "size": len(text),
                        "by": source, **({"pending": old["pending"]} if old and old.get("pending") else {})})
        _seen(session_id, state.get("task_id"), h, "snapshot", source, [f"{source}:{_tool_label(event)}"], "agent")
    return entries


def _between_calls(changed_at: float, entry: dict, start: float | None, others: dict, clock: dict, now: float,
                   event: dict) -> tuple[bool, str]:
    """Whether a change found after a tool call happened between two calls, by the person: (True, "") or (False, why
    not). In doubt, not."""
    if start is None:
        return False, "no_start_stamp"
    if changed_at > now + MARGIN_S:
        return False, "ctime_in_the_future"
    if changed_at <= entry.get("checked", 0) or changed_at >= start - MARGIN_S:
        return False, "changed_during"
    if clock.get("background"):
        return False, "background_task_running"
    if event.get("agent_id") or any(o.get("agent") or o.get("tool") in SUBAGENT_TOOLS for o in others.values()) \
            or (clock.get("subagent_at") or 0) >= changed_at - GRACE_S:
        return False, "subagent_running"
    if any(float(o.get("at") or 0) <= changed_at + MARGIN_S for o in others.values()):
        return False, "another_call_running"
    if changed_at <= max(clock.get("tool_end") or 0, clock.get("turn_end") or 0) + GRACE_S:
        return False, "within_grace_after_a_call"
    return True, ""


def _look(event: dict, session_id: str, entries: list[dict], written: set[str], now: float,
          failed: bool, started: dict | None = None) -> list[dict]:
    """Each kept file against what was last seen of it: unchanged, changed during this call (the agent's), changed
    between the previous look and this call's start with nothing else running (the person's, kept as `pending` for
    the next request), or changed when that cannot be told (nobody's)."""
    start = float(started["at"]) if started and started.get("at") else None
    others = session.live(session_id)
    state = session.load(session_id)
    clock = {**_clock(session_id)}
    clock["background"] = bool(clock.get("background") or state.get("background_since"))
    clock["subagent_at"] = state.get("subagent_at") or 0
    tool = _tool_label(event)
    source = "agent_shell" if is_shell(event) else "agent_tool"
    task_id = session.load(session_id).get("task_id")
    out = []
    for e in entries:
        if e["path"] in written:
            out.append(e)                     # this call wrote it: `_keep` takes the new copy
            continue
        st = _stat(e["path"])
        if st is not None and st == e.get("stat"):
            e["checked"] = now
            out.append(e)
            continue
        before = _snapshot(session_id, e)
        after = _text(Path(e["path"])) if st is not None else None
        if before is None or after is None:   # deleted, or no longer text: nothing to learn from
            _forget(session_id, e)
            continue
        if after == before:                   # touched, not changed
            e.update(stat=st, checked=now)
            out.append(e)
            continue
        changed_at = st[2] / 1e9
        person, why = _between_calls(changed_at, e, start, others, clock, now, event)
        if person:
            basis = ["changed_between_tool_calls", f"ctime_before_start:{tool}", "start_stamped"]
            pend = dict(e.get("pending") or {})
            pend.setdefault("diffs", []).append(diff(before, after, os.path.basename(e["path"])))
            pend["basis"] = basis
            pend["detector"] = "between_tool_calls"
            e["pending"] = pend
            _seen(session_id, task_id, e["hash"], "pending", "outside", basis, "person",
                  detector="between_tool_calls")
        elif why == "changed_during":
            basis = [f"changed_during:{tool}"] + (["tool_failed"] if failed else [])
            _seen(session_id, task_id, e["hash"], "rebased", source, basis, "agent")
        else:
            _seen(session_id, task_id, e["hash"], "unattributed", "unexplained", [f"{why}:{tool}"], None)
        _write_snapshot(session_id, e, after)
        e.update(stat=st, checked=now, size=len(after))
        out.append(e)
    return out


def _snapshot(session_id: str, entry: dict) -> str | None:
    try:
        return (_dir(session_id) / f"{entry['hash']}.txt").read_text()
    except OSError:
        return None


def _write_snapshot(session_id: str, entry: dict, text: str) -> None:
    (_dir(session_id) / f"{entry['hash']}.txt").write_text(text)


def on_stop(event: dict, session_id: str) -> None:
    """Stop: the agent's turn ended. A change after this (and a grace window), with no tool call since, is the
    person's; a background task the agent left running (Claude Code's `background_tasks`) takes that evidence away.
    No foreground call of the turn is running any more."""
    session.live_clear(session_id)
    running = bool(event.get("background_tasks"))
    if not running and session.load(session_id).get("background_since"):
        session.update(session_id, background_since=None)       # the tasks it started have all ended
    if not (_dir(session_id) / "index.json").exists():
        return
    _save_clock(session_id, turn_end=time.time(), background=running)


def _seen(session_id: str, task_id, file_hash: str, decision: str, source: str, basis: list[str],
          attributed_to: str | None, **more) -> dict:
    """The `edit_seen` audit event: what the detector decided about a file (by the hash of its path, never its name
    or content), on what evidence, and to whom it gave the change."""
    from athos import eval as ev
    event = {"type": "edit_seen", "session_id": session_id, "task_id": task_id, "file_sha": file_hash,
             "decision": decision, "source": source, "basis": basis, "attributed_to": attributed_to, **more}
    ev.audit(event)
    return event


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


# ------------------------------------------------------------------------------------------------ the next request
def _after_turn(changed_at: float, entry: dict, clock: dict, session_id: str = "",
                project: str | None = None) -> tuple[list[str], str | None]:
    """The evidence that a change found at the person's next request is theirs, or why there is none."""
    turn_end, tool_end = clock.get("turn_end"), clock.get("tool_end") or 0
    if not turn_end:
        return [], "no_turn_end"
    if turn_end < tool_end:
        return [], "tool_after_turn_end"
    if clock.get("background") or (session_id and session.peek(session_id).get("background_since")):
        return [], "background_task_running"
    if session_id and session.live(session_id):
        return [], "tool_call_running"
    if changed_at > time.time() + MARGIN_S:
        return [], "ctime_in_the_future"
    if changed_at <= turn_end or changed_at <= entry.get("checked", 0):
        return [], "changed_before_turn_end"
    if changed_at <= turn_end + GRACE_S:
        return [], "within_grace_after_turn_end"
    if session_id and _other_session_since(session_id, project, turn_end):
        return [], "another_session_active"
    return ["changed_after_turn_end", "no_tool_call_since"], None


def _other_session_since(session_id: str, project: str | None, since: float) -> bool:
    """Whether another agent session working in the same project (any, when this one's project is not known) moved
    since `since`: a change made then could be its agent's."""
    from athos import paths
    own = session._file(session_id).name
    try:
        files = [f for f in paths.sessions().glob("*.json") if f.name != own and f.stat().st_mtime > since]
    except OSError:
        return True
    for f in files:
        other = session.peek(f.stem)
        if other.get("task_id") and (not project or other.get("project") == project):
            return True
    return False


def _target(entry: dict) -> tuple[str | None, str | None, str]:
    """(piece, step, why): the step the agent was on when it wrote the file, else the task's best routed piece, else
    none. Never the first piece by name (F6)."""
    stmt = entry.get("statement") or ""
    if stmt:
        return stmt.partition("#")[0], stmt.partition("#")[2] or None, "current_step"
    if entry.get("route_best"):
        return entry["route_best"], None, "route_best"
    return None, None, "none"


def check(session_id: str) -> list[dict]:
    """The files the person changed, on evidence (see the module's notes): each with its diff, the evidence, the piece
    and the step it is credited to. A file given to the person is forgotten (offered once); a change with no evidence
    is given to nobody and the snapshot moves on; files not changed yet stay for a later request."""
    entries = _index(session_id)
    clock = _clock(session_id)
    state = session.load(session_id)
    task_id, project = state.get("task_id"), state.get("project")
    found, keep = [], []
    for e in entries:
        before = _snapshot(session_id, e)
        after = _text(Path(e["path"]))
        pending = e.get("pending") or {}
        if before is None or after is None:      # deleted, or no longer text: nothing to learn from
            _forget(session_id, e)
            continue
        if len(found) >= PER_PROMPT or (after == before and not pending):
            keep.append(e)
            continue
        diffs, basis, detector = list(pending.get("diffs") or []), list(pending.get("basis") or []), \
            pending.get("detector")
        if after != before:
            evidence, missing = _after_turn((_stat(e["path"]) or [0, 0, 0])[2] / 1e9, e, clock, session_id,
                                            project)
            if evidence:
                diffs.append(diff(before, after, os.path.basename(e["path"])))
                basis, detector = basis + evidence, detector or "after_turn_end"
            elif not _same(before, after):
                _seen(session_id, task_id, e["hash"], "unattributed", "unexplained", [missing], None)
                _log("a file change given to nobody", missing, None, None, project)
        if not diffs:                             # only the agent's or an unexplained change: watch on from here
            _write_snapshot(session_id, e, after)
            e.update(stat=_stat(e["path"]), checked=time.time())
            e.pop("pending", None)
            keep.append(e)
            continue
        _forget(session_id, e)
        if _same(before, after) and not pending:
            continue
        pid, step, why = _target(e)
        p = store.get(pid) if pid else None
        found.append({"file": e["path"], "name": os.path.basename(e["path"]), "piece": pid,
                      "title": (p.title if p else pid), "statement": step, "piece_basis": why,
                      "basis": basis, "detector": detector, "file_sha": e["hash"],
                      "task_id": e.get("task_id"), "diff": "\n".join(diffs)})
    _save_index(session_id, keep)
    return found


def model_text(found: list[dict], cmd: str = "athos") -> str:
    """What the model is told about the person's edits: short, and only for those credited to a piece."""
    found = [f for f in found if f.get("piece")]
    if not found:
        return ""
    parts = ["# Athos — the person edited what you wrote\n"]
    for f in found:
        where = f"`{f['piece']}#{f['statement']}`" if f["statement"] else f"`{f['piece']}`"
        parts.append(f"`{f['name']}`, while following «{f['title']}» ({where}):\n\n```diff\n{f['diff']}\n```\n")
    parts.append(f"If an edit shows a rule of how they work, propose it in one line, in their language, and ask before "
                 f"adding it. Never save it without their yes; on a yes, `{cmd} show <id>`, then `{cmd} save` with its "
                 f"`id:`, a `note:` and only that step changed. Say nothing about a trivial edit.\n")
    return "\n".join(parts)


def on_prompt(event: dict, cmd: str = "athos", tell: bool = True) -> tuple[str, list[dict]]:
    """UserPromptSubmit, after the new task started: find the person's edits since the agent's last writes, record
    them (`edit_seen`, `learned_from_edit`), then, with `tell`, tell the model. The telling is the last, separable
    step: with autonomous learning, or on an apply model, the edits are only evidence (athos/evidence.py) and the
    model hears nothing. Returns the text for the model and what was found."""
    sid = event.get("session_id", "default")
    found = record(sid, check(sid))
    return (model_text(found, cmd) if tell else ""), found


def record(sid: str, found: list[dict]) -> list[dict]:
    """The person's edits as evidence: one `edit_seen` and one `learned_from_edit` each, and the panels' note (only
    for those credited to a piece). In a repository marked public the events keep hashes, never a path or a title."""
    if not found:
        return found
    from athos import eval as ev
    state = session.load(sid)
    task_id, public = state.get("task_id"), bool(state.get("public"))
    notes = [{k: f[k] for k in ("file", "name", "piece", "title", "statement")} for f in found if f.get("piece")]
    if notes:
        session.update(sid, learned_from_edit={"task_id": task_id, "files": notes})
    for f in found:
        if public:
            kept = {"file_sha": f["file_sha"], "piece_sha": _hash(f["piece"]) if f["piece"] else None,
                    "statement_sha": _hash(f["statement"]) if f["statement"] else None, "public": True}
        else:
            kept = {k: f[k] for k in ("file", "name", "piece", "title", "statement")}
        ev.append({"type": "learned_from_edit", "session_id": sid, "task_id": task_id, "at": ev._iso(ev.now()),
                   **kept, "basis": f["basis"], "piece_basis": f["piece_basis"]})
    try:
        _audit_found(sid, task_id, found, public)
    except Exception as problem:  # noqa: BLE001 — the audit never costs the person the offer
        ev.hook_error("prompt", "edits.audit", problem, sid)
    return found


def _log(what: str, basis: str, piece: str | None, why: str | None, project: str | None = None) -> None:
    from athos import eval as ev
    ev.log_line("edit_seen", project, f"{what} ({basis})" + (f" · piece {piece} ({why})" if why else ""))


def _audit_found(sid: str, task_id, found: list[dict], public: bool) -> None:
    """One `edit_seen` per change given to the person, with its evidence and the piece it is credited to."""
    from athos import load
    project = session.load(sid).get("project")
    for f in found:
        _seen(sid, task_id, f["file_sha"], "attributed", "outside", f["basis"], "person", detector=f["detector"],
              piece=(None if public else f.get("piece")), piece_basis=f["piece_basis"])
        piece = store.get(f.get("piece") or "")
        named = load.loggable([piece], project) if piece and not public else ("no piece" if not piece else "a piece")
        _log("a file change given to the person", ", ".join(f["basis"]), named, f["piece_basis"], project)


def kept(session_id: str, prompt: str) -> None:
    """An adjust request that names an edited file ([Keep this rule], or the person's own words): that edit is dealt
    with, so the panels stop offering it."""
    state = session.load(session_id)
    learned = state.get("learned_from_edit") or {}
    files = [f for f in learned.get("files") or [] if f.get("name") not in prompt]
    if len(files) != len(learned.get("files") or []):
        session.update(session_id, learned_from_edit={**learned, "files": files})
