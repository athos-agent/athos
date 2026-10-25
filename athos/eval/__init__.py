"""Local evaluation: what each piece of know-how and each model brings to the user's own work.

Everything is appended to `<home>/events.jsonl` on the user's machine and never sent anywhere.

    task_start  a request begins (UserPromptSubmit): task id, session, platform, model, time
    task_end    the assistant stops (Stop): duration, tokens, the pieces loaded and saved. A task may end twice
                when Athos asks for a capture; time and tokens count only up to the first end, so the capture's own
                cost never inflates a baseline
    mark        the user's verdict on a task: ok, corrected or failed. A task never marked stays "unevaluated".

A task's baseline is the one in which a piece was first saved: that execution ran without the piece. Later tasks
that load the piece are compared with it on time and tokens.
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid

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


def task_start(event: dict, platform: str = "claude-code") -> str:
    sid = event.get("session_id", "default")
    state = session.load(sid)
    tid = uuid.uuid4().hex[:12]
    model = state.get("model") or session.model_from_transcript(event.get("transcript_path"))
    started = _iso(now())
    # Capture is per request: only the work done for this request can trigger the Stop hook's ask.
    state.update(task_id=tid, task_started=started, task_loaded=[], task_saved=[], tools_since_capture=0)
    session.save(sid, state)
    append({"type": "task_start", "task_id": tid, "session_id": sid, "platform": platform, "model": model,
            "project": paths.project_of(event.get("cwd")), "at": started,
            "request": (event.get("prompt") or "")[:120]})
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
        state["model"] = session.model_from_transcript(event.get("transcript_path"))
        session.save(sid, state)
    rec = {"type": "task_end", "task_id": tid, "session_id": sid, "at": _iso(ended),
           "duration_s": round((ended - started).total_seconds(), 1),
           "tokens": tokens_between(event.get("transcript_path"), state.get("task_started", ""), _iso(ended)),
           "model": state.get("model", "unknown"),
           "pieces": state.get("task_loaded", []), "saved": state.get("task_saved", [])}
    append(rec)
    return rec


def record_external(platform: str, model: str, pieces: list[str], duration_s: float, tokens: dict | None,
                    result: str | None = None, request: str = "") -> str:
    """One whole task run outside Claude Code (another platform, or a local model)."""
    tid = uuid.uuid4().hex[:12]
    t = _iso(now())
    append({"type": "task_start", "task_id": tid, "session_id": f"{platform}-{tid}", "platform": platform,
            "model": model, "at": t, "request": request[:120]})
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


def last_task_id(session_id: str | None = None) -> str | None:
    if session_id:
        tid = session.load(session_id).get("task_id")
        if tid:
            return tid
    ends = [e for e in events() if e.get("type") == "task_end"]
    return ends[-1]["task_id"] if ends else None


def mark(result: str, task_id: str | None = None, session_id: str | None = None) -> tuple[str, str]:
    res = RESULTS.get(result.lower())
    if res is None:
        raise ValueError("result must be g (ok), c (corrected) or f (failed)")
    tid = task_id or last_task_id(session_id)
    if not tid:
        raise LookupError("no task to mark yet")
    append({"type": "mark", "task_id": tid, "result": res, "at": _iso(now())})
    return tid, res


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
                     project=e.get("project"), request=e.get("request", ""))
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
            out.append(f"    vs first run without it: time saved {_signed(p['time_saved_s'], ' s')}, "
                       f"tokens saved {_signed(p['tokens_saved'])}")
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
