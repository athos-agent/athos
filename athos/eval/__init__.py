"""Athos's own measuring tape: the user's tasks, kept on the user's machine, and what each piece and model did on them.

The log is one JSON object per line in `<home>/events.jsonl`. Nothing in this module sends it anywhere.

Kinds of line written to the log:

    task_start  written when a request arrives (UserPromptSubmit): ids, session, platform, model, the time
    task_end    written when the assistant stops (Stop): how long it took, its tokens, the pieces it loaded and
                saved. When Athos asks for a capture the same task stops a second time; only the first stop sets
                its time and tokens, so a capture never makes a baseline look more expensive than it was
    mark        the person's verdict: ok, corrected or failed. Tasks nobody judges are reported as "unevaluated".
                Judging a task that loaded a piece also keeps it as a case (athos/cases.py)
    test_run    `athos test` replaying a piece's recorded corrections on its latest version (athos/replay.py)
    shadow      `athos shadow` running an approved task again on a cheaper model and scoring the result

Comparisons: the task that first saved a piece ran without it, so it is that piece's baseline. Every later task
that loaded the piece is measured against the baseline on time, tokens and request length.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator

from athos import paths, session, store

# Shapes passed around below. They are all plain JSON-ready dicts; the names only say which is which.
Event = dict[str, Any]          # one line of the log
Task = dict[str, Any]           # a task folded from its lines (see `tasks`)
Tokens = dict[str, int]         # input / output / cache_read / cache_write / total
TaskId = str
PieceId = str
Moment = _dt.datetime

# Every spelling `athos mark` accepts, folded into the three verdicts written to the log.
_SPELLINGS = {"ok": ("g", "good"), "corrected": ("c", "fix"), "failed": ("f", "fail")}
RESULTS = {word: verdict for verdict, extra in _SPELLINGS.items() for word in (verdict, *extra)}
UNMARKED = "unevaluated"

STALE_DAYS = 14             # a piece idle for longer than this is put up for review
LOW_SUCCESS = 0.5           # ...and so is one whose judged tasks succeed less often than this
MIN_EVALUATED = 3           # ...once at least this many of its tasks have been judged

# Working folders that hold tests and demo rehearsals rather than real work; their tasks are flagged `scratch`.
SCRATCH_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/Users/Shared/athos-demo")


# ================================================================================================ time and the log
def now() -> Moment:
    """The current moment, timezone-aware in UTC. Tests freeze it by patching this name."""
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _iso(moment: Moment) -> str:
    return moment.isoformat(timespec="milliseconds")


def _parse(stamp: str) -> Moment | None:
    """A log or transcript timestamp as a datetime (a trailing Z is accepted); None when it can't be read."""
    parsed = None
    if isinstance(stamp, str):
        if stamp.endswith("Z"):
            stamp = stamp[:-1] + "+00:00"
        try:
            parsed = _dt.datetime.fromisoformat(stamp)
        except ValueError:
            parsed = None
    return parsed


def _new_id() -> TaskId:
    return uuid.uuid4().hex[:12]


def new_task_id() -> TaskId:
    """A fresh short task id, for callers that need it before the task is logged (athos delegate)."""
    return _new_id()


def append(event: Event) -> None:
    """Add one event at the end of the log, creating its folder the first time."""
    log = paths.events_file()
    log.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False)
    with log.open("a") as out:
        out.write(line + "\n")


def _decoded(lines: Iterable[str]) -> Iterator[Any]:
    for line in lines:
        try:
            yield json.loads(line)
        except ValueError:          # a half-written or hand-edited line is skipped, never fatal
            pass


def _log_text() -> str:
    try:
        return paths.events_file().read_text()
    except OSError:                 # no log yet (or unreadable): the same as an empty one
        return ""


def events() -> list[Event]:
    """Every readable event in the log, oldest first; an absent log is simply empty."""
    return list(_decoded(_log_text().splitlines()))


# ================================================================================================ tokens
_USAGE_FIELDS = (("input", "input_tokens"), ("output", "output_tokens"),
                 ("cache_read", "cache_read_input_tokens"), ("cache_write", "cache_creation_input_tokens"))


def _replies_in_window(handle, since: Moment | None, until: Moment | None):
    """The (key, usage) of each transcript line that carries a model reply's usage inside the window."""
    for row in _decoded(handle):
        message = row.get("message") if isinstance(row, dict) else None
        when = _parse(row.get("timestamp", "")) if isinstance(message, dict) else None
        has_usage = when is not None and isinstance(message.get("usage"), dict)
        if has_usage and not (since and when < since) and not (until and when > until):
            yield message.get("id") or row.get("uuid"), message["usage"]


def _open_quietly(path: str | None):
    """The file opened for reading (undecodable bytes ignored), or None when there is no path or it can't be read."""
    if path:
        try:
            return open(path, errors="ignore")
        except OSError:
            pass
    return None


def tokens_between(transcript_path: str | None, start: str, end: str) -> Tokens | None:
    """Add up the tokens Claude Code's transcript reports for the replies made between `start` and `end`.

    The transcript is the platform's private format, so this is a best effort that answers None when it finds
    nothing. A single reply is written over several lines that share its id: it is added only once."""
    handle = _open_quietly(transcript_path)
    if handle is None:
        return
    totals = {name: 0 for name, _ in _USAGE_FIELDS}
    counted: set = set()
    with handle:
        for key, usage in _replies_in_window(handle, _parse(start), _parse(end)):
            if key not in counted:
                counted.add(key)
                for name, field in _USAGE_FIELDS:
                    totals[name] += int(usage.get(field) or 0)
    return {**totals, "total": sum(totals.values())} if counted else None


def _tokens(platform: str, transcript_path: str | None, since: str, until: str, sid: str = "") -> Tokens | None:
    """Token usage for a task, read from wherever its platform keeps it."""
    if platform == "muse-code":
        # Muse's hooks carry no transcript path; its own session log has the usage instead.
        from athos.adapters import muse
        return muse.tokens_between(sid, since, until)
    if platform != "codex":
        return tokens_between(transcript_path, since, until)
    from athos.adapters import codex
    return codex.tokens_between(transcript_path, since, until)


# ================================================================================================ recording tasks
def request_fields(text: str) -> dict:
    """What the log keeps of a request: a short head to recognise it by, and its full length. The bars compare
    that length with the first run's, which is how much explaining the know-how saved."""
    cleaned = (text or "").strip()
    return {"request": cleaned[:120], "request_chars": len(cleaned)}


def _start_event(task_id: TaskId, sid: str, platform: str, model: str, project, at: str, request) -> Event:
    """The task_start line, shared by tasks seen through hooks and tasks reported from elsewhere."""
    return {"type": "task_start", "task_id": task_id, "session_id": sid, "platform": platform, "model": model,
            "project": project, "at": at, **request_fields(request)}


def _end_event(task_id: TaskId, at: str, duration_s: float, tokens, model: str, loaded, saved,
               sid: str | None = None) -> Event:
    """The task_end line. Only tasks seen through hooks name their session here."""
    head = {"type": "task_end", "task_id": task_id}
    if sid is not None:
        head["session_id"] = sid
    return {**head, "at": at, "duration_s": round(duration_s, 1),
            "tokens": tokens, "model": model, "pieces": loaded, "saved": saved}


def _hook_session(event: Event) -> tuple[str, dict]:
    """The session a hook event belongs to, and that session's saved state."""
    sid = event.get("session_id", "default")
    return sid, session.load(sid)


def _fresh_task_state(task_id: TaskId, started: str, prompt: str) -> dict:
    """The per-request part of a session's state. Capture works per request, so its counters start again here."""
    return {
        "task_id": task_id, "task_started": started,
        "task_loaded": [], "task_saved": [], "task_why": {}, "trail": [],
        "tools_since_capture": 0, "work_since_capture": 0, "edits_since_capture": 0,
        "task_request": prompt[:200],
        # The full request stays here (this session only, overwritten by the next request) until the task is
        # judged, so a case can keep it (athos/cases.py).
        "case_request": prompt,
    }


def _sent_model(event: Event) -> str | None:
    model = event.get("model")
    return model if isinstance(model, str) and model else None


def _transcript_model(event: Event) -> str:
    return session.model_from_transcript(event.get("transcript_path"))


def _is_scratch(cwd) -> bool:
    return str(cwd or "").startswith(SCRATCH_PREFIXES)


def task_start(event: Event, platform: str = "claude-code") -> TaskId:
    """Open a task for a new request: reset the session's per-task state and log a task_start. Returns its id."""
    sid, state = _hook_session(event)
    if _sent_model(event):
        state["model"] = _sent_model(event)      # Codex repeats the model on every hook event
    new_id, opened_at = _new_id(), _iso(now())
    model = state.get("model") or _transcript_model(event)
    prompt = str(event.get("prompt") or "")
    session.save(sid, {**state, "platform": platform, **_fresh_task_state(new_id, opened_at, prompt)})
    opened = _start_event(new_id, sid, platform, model, paths.project_of(event.get("cwd")), opened_at,
                          event.get("prompt"))
    if _is_scratch(event.get("cwd")):
        opened["scratch"] = True                 # a test or rehearsal: curating ignores it
    append(opened)
    return new_id


def _settle_model(sid: str, state: dict, event: Event) -> None:
    """Fill in the session's model at the end of a task when the start could not tell which one it was."""
    if state.get("model") in (None, "", "unknown"):
        state["model"] = _sent_model(event) or _transcript_model(event)
        session.save(sid, state)


def task_end(event: Event) -> Event | None:
    """Close the session's open task: log a task_end with its duration, tokens and pieces, and return it.
    None when the session has no task open."""
    sid, state = _hook_session(event)
    open_id = state.get("task_id")
    if not open_id:
        return
    finished = now()
    opened_at = state.get("task_started", "")
    began = _parse(opened_at) or finished
    _settle_model(sid, state, event)
    if isinstance(event.get("tokens"), dict):
        used = event["tokens"]                   # OpenCode counts its own tokens and sends them
    else:
        used = _tokens(state.get("platform", "claude-code"), event.get("transcript_path"),
                       opened_at, _iso(finished), sid)
    closed = _end_event(open_id, _iso(finished), (finished - began).total_seconds(), used,
                        state.get("model", "unknown"), state.get("task_loaded", []), state.get("task_saved", []),
                        sid=sid)
    append(closed)
    return closed


def record_external(platform: str, model: str, pieces: list[PieceId], duration_s: float, tokens: Tokens | None,
                    result: str | None = None, request: str = "", project: str | None = None,
                    task_id: TaskId | None = None, steps: list[dict] | None = None) -> TaskId:
    """Log a complete task that ran somewhere Athos has no hooks (another agent, a local model), start and end at
    once, and judge it when `result` is given. `steps` lists, for a delegation run one statement at a time, each
    statement's model, time and tokens; `athos route` reads them."""
    tid = task_id or new_task_id()
    stamp = _iso(now())
    append(_start_event(tid, f"{platform}-{tid}", platform, model, project, stamp, request))
    closed = _end_event(tid, stamp, duration_s, tokens, model, pieces, [])
    if steps:
        closed["steps"] = steps
    append(closed)
    return mark(result, task_id=tid)[0] if result else tid


def _add_to_open_task(sid: str, key: str, ids: Iterable[PieceId]) -> None:
    state = session.load(sid)
    if state.get("task_id"):
        state[key] = sorted(set(state.get(key, [])).union(ids))
        session.save(sid, state)


def note_loaded(session_id: str, ids: list[PieceId]) -> None:
    """Remember that the open task loaded these pieces."""
    _add_to_open_task(session_id, "task_loaded", ids)


def note_saved(session_id: str, piece_id: PieceId) -> None:
    """Remember that the open task saved (or improved) this piece."""
    _add_to_open_task(session_id, "task_saved", [piece_id])


# ================================================================================================ verdicts
def last_task_id(session_id: str | None = None, project: str | None = None) -> TaskId | None:
    """Which task a bare `athos mark` means. Candidates are this session's task and every task of this project
    (so a Codex run in the same folder after a Claude Code session wins if it ended later); with no candidate,
    the task that ended last anywhere."""
    known = tasks()
    sessions_task = session.load(session_id).get("task_id") if session_id and known else None
    candidates = [t for t in known if t["task_id"] == sessions_task or (project and t.get("project") == project)]
    pool = candidates or known
    return max(pool, key=lambda t: t.get("ended") or "")["task_id"] if pool else None


def mark(result: str, task_id: TaskId | None = None, session_id: str | None = None,
         project: str | None = None) -> tuple[TaskId, str]:
    """Log the person's verdict on a task (the given one, else the one `last_task_id` picks).
    Returns (task id, verdict)."""
    verdict = RESULTS.get(result.lower())
    if verdict is None:
        raise ValueError("unknown result: use g (ok), c (corrected) or f (failed)")
    target = task_id or last_task_id(session_id, project)
    if target is None or target == "":
        raise LookupError("nothing to mark: no task has ended yet")
    append({"type": "mark", "task_id": target, "result": verdict, "at": _iso(now())})
    _keep_case(target, verdict, session_id)
    return target, verdict


def _keep_case(tid: TaskId, res: str, session_id: str | None, correction: str | None = None) -> None:
    """Hand a judged task to athos/cases.py. Whatever goes wrong there, the verdict is already logged."""
    from athos import cases
    try:
        cases.on_mark(tid, res, session_id, correction)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass


# What the person says right after a task, when it plainly judges it: the mark nobody has to click. Looked for in
# the first words only ("ok excelente, ¿cómo viene?", "no funciona el login"). Over 702 real follow-ups only 5 judged
# the task this plainly: it helps, but the [Good] key stays.
SAID_OK = re.compile(r"\b(excelente|perfect[oa]?|genial|buen[ií]simo|muy bien|bien hecho|gracias|anduvo|funciona|"
                     r"funcion[oó]|great|perfect|excellent|thanks|thank you|awesome|works|well done|lgtm)\b", re.IGNORECASE)
SAID_FIX = re.compile(r"\b(no funciona|no anda|est[aá] mal|te equivocaste|no es as[ií]|sigue fallando|no veo|"
                      r"fall[oó]|wrong|doesn'?t work|broken|not quite)\b", re.IGNORECASE)
RECENT_DAYS = 7


def infer_mark(session_id: str, prompt: str) -> str | None:
    """Mark the session's previous task from the person's next words when they plainly judge it ("perfecto" → ok,
    "no, está mal" → corrected), if it has no mark yet. Returns the result, or None."""
    head = " ".join((prompt or "").split()[:6])
    res = "corrected" if SAID_FIX.search(head) else "ok" if SAID_OK.search(head) else None
    tid = session.load(session_id).get("task_id")
    if not res or not tid:
        return None
    if any(e.get("type") == "mark" and e.get("task_id") == tid for e in events()):
        return None
    append({"type": "mark", "task_id": tid, "result": res, "by": "inferred", "at": _iso(now())})
    # The words that judged the task wrong are the correction itself: the case keeps them as what to check.
    _keep_case(tid, res, session_id, prompt.strip() if res == "corrected" else None)
    return res


def recent(t: dict, days: int = RECENT_DAYS) -> bool:
    started = _parse(t.get("started") or "")
    return bool(started) and (now() - started).days < days


def record(piece_id: str, tasks: list[dict]) -> dict:
    """How a piece has done: tasks that used it, how many were marked good, and the agents it ran in."""
    used = [t for t in tasks if piece_id in t.get("pieces", [])]
    labels = dict(AGENTS)
    agents = sorted({labels.get(t.get("platform"), t.get("platform")) for t in used if t.get("platform")})
    return {"uses": len(used), "ok": sum(t["result"] == "ok" for t in used),
            "marked": sum(t["result"] != "unevaluated" for t in used), "agents": agents}


# ================================================================================================ folding the log
def _on_start(task: Task, line: Event) -> None:
    task.update(started=line.get("at"), platform=line.get("platform", "unknown"),
                model=line.get("model", "unknown"), project=line.get("project"), request=line.get("request", ""),
                request_chars=line.get("request_chars"), scratch=bool(line.get("scratch")))


def _on_end(task: Task, line: Event) -> None:
    # The first stop fixes time and tokens; any later stop is the capture Athos asked for and would only make
    # the baseline look dearer. The pieces loaded and saved, though, gather across every stop.
    if "ended" not in task:
        task["duration_s"], task["tokens"] = line.get("duration_s"), line.get("tokens")
        if line.get("steps"):
            task["steps"] = line["steps"]
    task["ended"] = line.get("at")
    task["pieces"] = sorted(set(task["pieces"]).union(line.get("pieces", [])))
    task["saved"] = sorted(set(task["saved"]).union(line.get("saved", [])))
    if line.get("model") not in (None, "", "unknown"):
        task["model"] = line["model"]


def _on_mark(task: Task, line: Event) -> None:
    task["result"] = line.get("result", UNMARKED)        # a later verdict replaces an earlier one


_FOLD = {"task_start": _on_start, "task_end": _on_end, "mark": _on_mark}


def tasks() -> list[Task]:
    """The log folded into one dict per finished task (one that has stopped at least once), in the order the
    tasks first appear: its start, its stops, and its latest verdict (`unevaluated` when there is none)."""
    folded: dict[TaskId, Task] = {}
    for line in filter(lambda e: e.get("task_id"), events()):
        task = folded.setdefault(line["task_id"],
                                 {"task_id": line["task_id"], "result": UNMARKED, "pieces": [], "saved": []})
        handler = _FOLD.get(line.get("type"))
        if handler:
            handler(task, line)
    return [task for task in folded.values() if "ended" in task]


# ================================================================================================ statistics
def _rate(group: list[Task]) -> tuple[float | None, int]:
    """(share judged ok, number judged) over the tasks someone judged; (None, 0) when nobody judged any."""
    judged = [t["result"] for t in group if t["result"] != UNMARKED]
    share = judged.count("ok") / len(judged) if judged else None
    return share, len(judged)


def _mean(values: list[float | None]) -> float | None:
    """Average of the values that are present, or None when none are."""
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _minus(before, after):
    return None if before is None or after is None else before - after


def _shorter(base: dict | None, uses: list[dict]) -> float | None:
    """How much shorter the requests that used a piece are than the one that taught it: what it spares explaining."""
    mean = _mean([t.get("request_chars") for t in uses])
    first = base.get("request_chars") if base else None
    return (first - mean) / first if first and mean is not None else None


def _tok(task: Task) -> int | None:
    """A task's total tokens, when they were counted."""
    counted = task.get("tokens") or {}
    return counted.get("total")


def _baseline(pid: PieceId, ts: list[Task]) -> Task | None:
    """The first task that saved the piece without having loaded it: the run done without the know-how."""
    return next((t for t in ts if pid in t["saved"] and pid not in t["pieces"]), None)


def _idle_days(last: str, today: _dt.date) -> int | None:
    try:
        return (today - _dt.date.fromisoformat(last)).days if last else None
    except (TypeError, ValueError):
        return None


def _review_flags(idle: int | None, rate: float | None, judged: int) -> list[str]:
    stale = idle is None or idle > STALE_DAYS
    failing = rate is not None and judged >= MIN_EVALUATED and rate < LOW_SUCCESS
    return [flag for flag, raised in ((f"not used in {STALE_DAYS} days", stale), ("low success", failing)) if raised]


def _piece_row(pid: PieceId, piece, ts: list[Task], today: _dt.date) -> dict:
    uses = [t for t in ts if pid in t["pieces"]]            # a task that loaded and improved it still used it
    base = _baseline(pid, ts)
    rate, judged = _rate(uses)
    mean_s = _mean([t.get("duration_s") for t in uses])
    mean_tok = _mean([_tok(t) for t in uses])
    dates = [t["ended"][:10] for t in uses]
    if piece is not None:
        dates.append(piece.last_used)
    last = max(dates, default="")
    row = {"piece": pid, "title": piece.title if piece is not None else "(deleted)",
           "uses": len(uses), "evaluated": judged, "success_rate": rate, "baseline": None,
           "mean_duration_s": mean_s, "mean_tokens": mean_tok, "time_saved_s": None, "tokens_saved": None,
           "prompt_saved": _shorter(base, uses), "last_used": last or None,
           "review": _review_flags(_idle_days(last, today), rate, judged)}
    if base:
        row["baseline"] = {"task_id": base["task_id"], "duration_s": base.get("duration_s"), "tokens": _tok(base)}
        row["time_saved_s"] = _minus(base.get("duration_s"), mean_s)
        row["tokens_saved"] = _minus(_tok(base), mean_tok)
    return row


def _where(task: Task) -> tuple[str, str]:
    return task.get("platform", "unknown"), task.get("model", "unknown")


def _model_rows(ts: list[Task]) -> list[dict]:
    groups: dict[tuple[str, str], list[Task]] = {}
    for t in ts:
        groups.setdefault(_where(t), []).append(t)
    rows = []
    for (platform, model), group in sorted(groups.items()):
        rate, judged = _rate(group)
        rows.append({"platform": platform, "model": model, "tasks": len(group), "evaluated": judged,
                     "success_rate": rate, "with_know_how": sum(1 for t in group if t["pieces"]),
                     "mean_duration_s": _mean([t.get("duration_s") for t in group]),
                     "mean_tokens": _mean([_tok(t) for t in group])})
    return rows


def report(today: _dt.date | None = None) -> dict:
    """Everything `athos report` shows: one row per piece (known or merely mentioned in the log) and one per
    platform and model, plus the ids of the pieces worth a review."""
    today = today or _dt.date.today()
    ts = tasks()
    known = {p.id: p for p in store.all_pieces()}
    mentioned = {pid for t in ts for pid in t["pieces"] + t["saved"]}
    rows = [_piece_row(pid, known.get(pid), ts, today) for pid in sorted(known.keys() | mentioned)]
    return {"generated": _iso(now()), "tasks": len(ts),
            "evaluated": sum(1 for t in ts if t["result"] != UNMARKED),
            "pieces": rows, "models": _model_rows(ts),
            "review": [row["piece"] for row in rows if row["review"]]}


# ------------------------------------------------------------------------------------------------ bars
AGENTS = (("claude-code", "Claude Code"), ("codex", "Codex"), ("muse-code", "Muse Code"),
          ("opencode", "OpenCode"))
OPTIONAL_AGENTS = {"muse-code", "opencode"}           # shown once Athos is installed in it, or it has run a task


def installed(platform: str) -> bool:
    """Whether Athos's plugin is installed in an optional agent on this machine."""
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    if platform == "muse-code":
        return any((data / "muse" / "plugins" / "cache").glob("*/athos"))
    if platform == "opencode":
        from athos.adapters import opencode
        return (opencode.plugins_dir() / "athos.js").exists()
    return True


def bars(project: str | None = None) -> dict | None:
    """How each agent applies, in this project, the piece of know-how this project used last: one row per agent with
    its uses here, its success rate over the tasks you marked, and how much shorter its requests are than the first
    run's, the one that taught the piece: what the know-how spares you from explaining. None until a task here has
    used or saved a piece."""
    ts = tasks()
    here = [t for t in ts if project is None or t.get("project") == project]
    last = next((t for t in reversed(here) if t["pieces"] or t["saved"]), None)
    if last is None:
        return None
    pid = (last["pieces"] or last["saved"])[0]
    base = next((t for t in ts if pid in t["saved"] and pid not in t["pieces"]), None)
    base_chars = base.get("request_chars") if base else None
    piece = store.get(pid)
    rows = []
    for platform, label in AGENTS:
        # A piece is used only after the run that taught it; an older session that happens to name it (a rehearsal
        # whose Codex log survived, say) is not a use of this piece.
        uses = [t for t in here if pid in t["pieces"] and t.get("platform") == platform
                and (base is None or (t.get("started") or "") >= (base.get("started") or ""))]
        if platform in OPTIONAL_AGENTS and not uses and not installed(platform) and \
                not any(t.get("platform") == platform for t in ts):
            continue
        rate, n_ev = _rate(uses)
        mean_chars = _mean([t.get("request_chars") for t in uses])
        rows.append({"platform": platform, "label": label, "uses": len(uses), "evaluated": n_ev,
                     "ok": sum(1 for t in uses if t["result"] == "ok"), "success_rate": rate,
                     "mean_request_chars": mean_chars,
                     "prompt_saved": (base_chars - mean_chars) / base_chars
                     if base_chars and mean_chars is not None else None})
    return {"piece": pid, "title": piece.title if piece else pid, "baseline_request_chars": base_chars, "agents": rows}


def _k(n: float) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1000:.1f}k" if n >= 1000 else f"{n:.0f}"


def bar_line(row: dict, width: int = 20) -> tuple[str, str]:
    """The bar (filled by the success rate) and the words beside it, shared by `athos watch` and the terminal."""
    filled = round((row["success_rate"] or 0) * width)
    bar = "█" * filled + "░" * (width - filled)
    if not row["uses"]:
        return bar, "not used yet"
    words = [f"{row['ok']}/{row['evaluated']} good" if row["evaluated"] else "not marked yet"]
    if row["prompt_saved"] is not None:
        words.append(f"{row['prompt_saved'] * 100:.0f}% shorter prompt" if row["prompt_saved"] >= 0
                     else f"{-row['prompt_saved'] * 100:.0f}% longer prompt")
    return bar, " · ".join(words)


# ================================================================================================ the text report
_DASH = "—"


def _pct(share: float | None) -> str:
    """A share as a whole percentage, or a dash when there is nothing to show."""
    return _DASH if share is None else format(share, ".0%")


def _num(value: float | None, unit: str = "") -> str:
    """A number with thousands separators and an optional unit, or a dash."""
    return _DASH if value is None else format(value, ",.0f") + unit


def _piece_lines(p: dict) -> list[str]:
    lines = [f"  {p['piece']}  uses {p['uses']}  success {_pct(p['success_rate'])} ({p['evaluated']} evaluated)"]
    if p["baseline"] and p.get("prompt_saved") is not None:
        lines.append(f"    vs the first run, which taught it: requests {p['prompt_saved'] * 100:.0f}% shorter")
    if p["review"]:
        lines.append("    review: " + ", ".join(p["review"]))
    return lines


def _model_line(m: dict) -> str:
    who = f"{m['platform']} / {m['model']}"
    outcome = f"tasks {m['tasks']}  success {_pct(m['success_rate'])} ({m['evaluated']} evaluated)"
    cost = f"avg {_num(m['mean_duration_s'], ' s')}, {_num(m['mean_tokens'])} tokens"
    return f"  {who}  {outcome}  with know-how {m['with_know_how']}  {cost}"


def _section(title: str, rows: list[str]) -> list[str]:
    return [title, *(rows or ["  (none yet)"])]


_HOW_TO_MARK = "mark the last one with `athos mark g|c|f` (good, corrected, failed)."


def render(report: dict) -> str:
    """`athos report` as plain text. Every figure comes from `report`; a missing one is printed as a dash."""
    piece_rows = [line for p in report["pieces"] for line in _piece_lines(p)]
    lines = [f"Athos report · {report['tasks']} task(s), {report['evaluated']} evaluated · local data only", ""]
    lines += _section("Know-how pieces", piece_rows)
    lines += [""] + _section("Models on your tasks", [_model_line(m) for m in report["models"]])
    pending = report["tasks"] - report["evaluated"]
    if pending:
        lines += ["", f"{pending} task(s) not evaluated yet: {_HOW_TO_MARK}"]
    return "\n".join(lines)
