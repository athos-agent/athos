"""Local evaluation: what each piece of know-how and each model brings to the user's own work.

Everything is appended to `<home>/events.jsonl` on the user's machine and never sent anywhere.

    task_start  a request begins (UserPromptSubmit): task id, session, platform, model, time
    task_end    the assistant stops (Stop): duration, tokens, the pieces loaded and saved. A task may end twice
                when Athos asks for a capture; time and tokens count only up to the first end, so the capture's own
                cost never inflates a baseline
    mark        the user's verdict on a task: ok, corrected or failed. A task never marked stays "unevaluated".
                A marked task that loaded a piece is kept as a case (athos/cases.py)
    test_run    `athos test`: a piece's past corrections replayed on its current version (athos/replay.py)
    shadow      `athos shadow`: one approved task replayed on a cheaper model, and how close it came

A task's baseline is the one in which a piece was first saved: that execution ran without the piece. Later tasks
that load the piece are compared with it on time and tokens.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import uuid
from pathlib import Path

from athos import paths, session, store

RESULTS = {"g": "ok", "ok": "ok", "good": "ok",
           "c": "corrected", "corrected": "corrected", "fix": "corrected",
           "f": "failed", "failed": "failed", "fail": "failed"}
STALE_DAYS = 14
LOW_SUCCESS = 0.5
MIN_EVALUATED = 3


def now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(t: _dt.datetime) -> str:
    return t.isoformat(timespec="milliseconds")


def _parse(ts: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def append(event: dict) -> None:
    f = paths.events_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def events() -> list[dict]:
    try:
        lines = paths.events_file().read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------------------------------------ recording
def tokens_between(transcript_path: str | None, start: str, end: str) -> dict | None:
    """Tokens of the model replies between two times, from the transcript. The format is internal to the platform, so
    this is best effort: None when nothing can be read. Each reply is counted once (it spans several lines)."""
    if not transcript_path:
        return None
    t0, t1 = _parse(start), _parse(end)
    seen, tot = set(), {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    try:
        fh = open(transcript_path, errors="ignore")
    except OSError:
        return None
    with fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            msg, ts = o.get("message"), _parse(o.get("timestamp", ""))
            if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict) or ts is None:
                continue
            if (t0 and ts < t0) or (t1 and ts > t1):
                continue
            key = msg.get("id") or o.get("uuid")
            if key in seen:
                continue
            seen.add(key)
            u = msg["usage"]
            tot["input"] += int(u.get("input_tokens") or 0)
            tot["output"] += int(u.get("output_tokens") or 0)
            tot["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
            tot["cache_write"] += int(u.get("cache_creation_input_tokens") or 0)
    if not seen:
        return None
    tot["total"] = sum(tot.values())
    return tot


def _tokens(platform: str, transcript: str | None, start: str, end: str, session_id: str = "") -> dict | None:
    if platform == "codex":
        from athos.adapters import codex
        return codex.tokens_between(transcript, start, end)
    if platform == "muse-code":                  # Muse sends no transcript path: its session log has the usage
        from athos.adapters import muse
        return muse.tokens_between(session_id, start, end)
    return tokens_between(transcript, start, end)


def request_fields(text: str) -> dict:
    """The request as recorded: its first characters to recognise it, and its whole length, which the bars compare
    with the first run's (what the know-how spares you from explaining)."""
    text = (text or "").strip()
    return {"request": text[:120], "request_chars": len(text)}


def task_start(event: dict, platform: str = "claude-code") -> str:
    sid = event.get("session_id", "default")
    state = session.load(sid)
    if isinstance(event.get("model"), str) and event["model"]:
        state["model"] = event["model"]                          # Codex sends the model on every event
    state["platform"] = platform
    tid = uuid.uuid4().hex[:12]
    model = state.get("model") or session.model_from_transcript(event.get("transcript_path"))
    started = _iso(now())
    # Capture is per request: only the work done for this request can trigger the Stop hook's ask.
    state.update(task_id=tid, task_started=started, task_loaded=[], task_saved=[], tools_since_capture=0,
                 work_since_capture=0, edits_since_capture=0, task_why={}, trail=[],
                 task_request=str(event.get("prompt") or "")[:200],
                 # The whole request, until the task is marked: a case keeps it (athos/cases.py). Only in this
                 # session's own state, replaced by the next request.
                 case_request=str(event.get("prompt") or ""))
    session.save(sid, state)
    append({"type": "task_start", "task_id": tid, "session_id": sid, "platform": platform, "model": model,
            "project": paths.project_of(event.get("cwd")), "at": started, **request_fields(event.get("prompt"))})
    return tid


def task_end(event: dict) -> dict | None:
    sid = event.get("session_id", "default")
    state = session.load(sid)
    tid = state.get("task_id")
    if not tid:
        return None
    ended = now()
    started = _parse(state.get("task_started", "")) or ended
    if not state.get("model") or state.get("model") == "unknown":
        given = event.get("model")
        state["model"] = given if isinstance(given, str) and given else \
            session.model_from_transcript(event.get("transcript_path"))
        session.save(sid, state)
    rec = {"type": "task_end", "task_id": tid, "session_id": sid, "at": _iso(ended),
           "duration_s": round((ended - started).total_seconds(), 1),
           # A platform that counts its own tokens (OpenCode) sends them; the others are read from the transcript.
           "tokens": event["tokens"] if isinstance(event.get("tokens"), dict) else
           _tokens(state.get("platform", "claude-code"), event.get("transcript_path"),
                   state.get("task_started", ""), _iso(ended), sid),
           "model": state.get("model", "unknown"),
           "pieces": state.get("task_loaded", []), "saved": state.get("task_saved", [])}
    append(rec)
    return rec


def record_external(platform: str, model: str, pieces: list[str], duration_s: float, tokens: dict | None,
                    result: str | None = None, request: str = "", project: str | None = None) -> str:
    """One whole task run outside Claude Code (another platform, or a local model)."""
    tid = uuid.uuid4().hex[:12]
    t = _iso(now())
    append({"type": "task_start", "task_id": tid, "session_id": f"{platform}-{tid}", "platform": platform,
            "model": model, "project": project, "at": t, **request_fields(request)})
    append({"type": "task_end", "task_id": tid, "at": t, "duration_s": round(duration_s, 1), "tokens": tokens,
            "model": model, "pieces": pieces, "saved": []})
    if result:
        mark(result, tid)
    return tid


def note_loaded(session_id: str, ids: list[str]) -> None:
    state = session.load(session_id)
    if state.get("task_id"):
        state["task_loaded"] = sorted(set(state.get("task_loaded", [])) | set(ids))
        session.save(session_id, state)


def note_saved(session_id: str, piece_id: str) -> None:
    state = session.load(session_id)
    if state.get("task_id"):
        state["task_saved"] = sorted(set(state.get("task_saved", [])) | {piece_id})
        session.save(session_id, state)


def last_task_id(session_id: str | None = None, project: str | None = None) -> str | None:
    """The task a one-key mark is about: the one that ended last among this session's task and the tasks of this
    project (a Codex task run in the same folder after a Claude Code session is the one meant); else the last one."""
    ts = tasks()
    if not ts:
        return None
    own = session.load(session_id).get("task_id") if session_id else None
    cands = [t for t in ts if t["task_id"] == own or (project and t.get("project") == project)]
    return max(cands or ts, key=lambda t: t.get("ended") or "")["task_id"]


def mark(result: str, task_id: str | None = None, session_id: str | None = None,
         project: str | None = None) -> tuple[str, str]:
    res = RESULTS.get(result.lower())
    if res is None:
        raise ValueError("result must be g (ok), c (corrected) or f (failed)")
    tid = task_id or last_task_id(session_id, project)
    if not tid:
        raise LookupError("no task to mark yet")
    append({"type": "mark", "task_id": tid, "result": res, "at": _iso(now())})
    _keep_case(tid, res, session_id)
    return tid, res


def _keep_case(tid: str, res: str, session_id: str | None, correction: str | None = None) -> None:
    """A marked task that loaded a piece becomes a case (athos/cases.py). Keeping it must never stop the mark."""
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


# ------------------------------------------------------------------------------------------------ report
def tasks() -> list[dict]:
    """One record per task: its start, its last end, and its last mark ("unevaluated" when never marked)."""
    by: dict[str, dict] = {}
    for e in events():
        tid = e.get("task_id")
        if not tid:
            continue
        t = by.setdefault(tid, {"task_id": tid, "result": "unevaluated", "pieces": [], "saved": []})
        if e["type"] == "task_start":
            t.update(started=e.get("at"), platform=e.get("platform", "unknown"), model=e.get("model", "unknown"),
                     project=e.get("project"), request=e.get("request", ""),
                     request_chars=e.get("request_chars"))
        elif e["type"] == "task_end":
            # Time and tokens stop at the first end: later ends of the same task are the capture Athos asked for,
            # which must not inflate a baseline. Pieces loaded and saved accumulate over all ends.
            if "ended" not in t:
                t.update(duration_s=e.get("duration_s"), tokens=e.get("tokens"))
            t.update(ended=e.get("at"), pieces=sorted(set(t["pieces"]) | set(e.get("pieces", []))),
                     saved=sorted(set(t["saved"]) | set(e.get("saved", []))))
            if e.get("model") and e["model"] != "unknown":
                t["model"] = e["model"]
        elif e["type"] == "mark":
            t["result"] = e.get("result", "unevaluated")
    return [t for t in by.values() if "ended" in t]


def _rate(ts: list[dict]) -> tuple[float | None, int]:
    ev = [t for t in ts if t["result"] != "unevaluated"]
    if not ev:
        return None, 0
    return sum(1 for t in ev if t["result"] == "ok") / len(ev), len(ev)


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _shorter(base: dict | None, uses: list[dict]) -> float | None:
    """How much shorter the requests that used a piece are than the one that taught it: what it spares explaining."""
    mean = _mean([t.get("request_chars") for t in uses])
    first = base.get("request_chars") if base else None
    return (first - mean) / first if first and mean is not None else None


def _tok(t: dict) -> int | None:
    return (t.get("tokens") or {}).get("total")


def report(today: _dt.date | None = None) -> dict:
    today = today or _dt.date.today()
    ts = tasks()
    pieces = {p.id: p for p in store.all_pieces()}
    per_piece = []
    for pid in sorted(set(pieces) | {x for t in ts for x in t["pieces"] + t["saved"]}):
        uses = [t for t in ts if pid in t["pieces"]]                                  # improving it is a use too
        base = next((t for t in ts if pid in t["saved"] and pid not in t["pieces"]), None)   # the run without it
        rate, n_ev = _rate(uses)
        mean_d, mean_tok = _mean([t.get("duration_s") for t in uses]), _mean([_tok(t) for t in uses])
        last = max([t["ended"][:10] for t in uses] + ([pieces[pid].last_used] if pid in pieces else []), default="")
        try:
            idle = (today - _dt.date.fromisoformat(last)).days if last else None
        except ValueError:
            idle = None
        flags = []
        if idle is None or idle > STALE_DAYS:
            flags.append(f"not used in {STALE_DAYS} days")
        if rate is not None and n_ev >= MIN_EVALUATED and rate < LOW_SUCCESS:
            flags.append("low success")
        per_piece.append({
            "piece": pid, "title": pieces[pid].title if pid in pieces else "(deleted)",
            "uses": len(uses), "evaluated": n_ev, "success_rate": rate,
            "baseline": {"task_id": base["task_id"], "duration_s": base.get("duration_s"), "tokens": _tok(base)}
            if base else None,
            "mean_duration_s": mean_d, "mean_tokens": mean_tok,
            "time_saved_s": (base["duration_s"] - mean_d) if base and mean_d is not None
            and base.get("duration_s") is not None else None,
            "tokens_saved": (_tok(base) - mean_tok) if base and mean_tok is not None and _tok(base) is not None
            else None,
            "prompt_saved": _shorter(base, uses),
            "last_used": last or None, "review": flags})
    per_model = []
    for (platform, model) in sorted({(t.get("platform", "unknown"), t.get("model", "unknown")) for t in ts}):
        mt = [t for t in ts if (t.get("platform", "unknown"), t.get("model", "unknown")) == (platform, model)]
        rate, n_ev = _rate(mt)
        per_model.append({"platform": platform, "model": model, "tasks": len(mt), "evaluated": n_ev,
                          "success_rate": rate, "with_know_how": sum(1 for t in mt if t["pieces"]),
                          "mean_duration_s": _mean([t.get("duration_s") for t in mt]),
                          "mean_tokens": _mean([_tok(t) for t in mt])})
    return {"generated": _iso(now()), "tasks": len(ts),
            "evaluated": sum(1 for t in ts if t["result"] != "unevaluated"),
            "pieces": per_piece, "models": per_model,
            "review": [p["piece"] for p in per_piece if p["review"]]}



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

def _pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def _num(x, unit=""):
    return "—" if x is None else f"{x:,.0f}{unit}"


def _signed(x, unit=""):
    return "—" if x is None else f"{x:+,.0f}{unit}"


def render(r: dict) -> str:
    out = [f"Athos report · {r['tasks']} task(s), {r['evaluated']} evaluated · local data only", ""]
    out.append("Know-how pieces")
    if not r["pieces"]:
        out.append("  (none yet)")
    for p in r["pieces"]:
        out.append(f"  {p['piece']}  uses {p['uses']}  success {_pct(p['success_rate'])} "
                   f"({p['evaluated']} evaluated)")
        if p["baseline"]:
            if p.get("prompt_saved") is not None:
                out.append(f"    vs the first run, which taught it: requests {p['prompt_saved'] * 100:.0f}% shorter")
        if p["review"]:
            out.append(f"    review: {', '.join(p['review'])}")
    out += ["", "Models on your tasks"]
    if not r["models"]:
        out.append("  (none yet)")
    for m in r["models"]:
        out.append(f"  {m['platform']} / {m['model']}  tasks {m['tasks']}  success {_pct(m['success_rate'])} "
                   f"({m['evaluated']} evaluated)  with know-how {m['with_know_how']}  "
                   f"avg {_num(m['mean_duration_s'], ' s')}, {_num(m['mean_tokens'])} tokens")
    unev = r["tasks"] - r["evaluated"]
    if unev:
        out += ["", f"{unev} task(s) not evaluated yet: mark the last one with `athos mark g|c|f` "
                    "(good, corrected, failed)."]
    return "\n".join(out)
