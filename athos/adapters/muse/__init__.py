"""Muse Code: the same know-how, with Meta's own agent and model.

    athos export --muse      writes each piece as a skill in `~/.agents/skills`, which Muse Code reads (as Codex does);
                             `athos export --muse .agents/skills` writes them into one project
    athos import muse        records Muse Code's past tasks from its session logs, as platform `muse-code`

Muse Code keeps every session in `~/.local/share/muse/sessions/YYYY/MM/DD/<id>/session.jsonl`. Its records nest
inside one another (some as JSON text in `record_json`), so the import looks for fields by name: the workspace, the
model, each request the person typed, the provider usage records (subagents included, since they are part of what the
task cost) and the Athos skills Muse read. A task is one request, from the moment it was typed until the next one.

Contributor mode (a `-contributor` model) lets Meta train on what it was sent; such tasks are recorded as they ran, and
`athos watch` and the report say so.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path

from athos import store

SKILL_USE = re.compile(r'read-skill-result name=\\*"athos-([a-z0-9][a-z0-9-]*)\\*"')
TMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/")


def sessions_dir() -> Path:
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "muse" / "sessions"


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _records(o):
    """Every dict in a line, including the records Muse nests as JSON text."""
    for d in _walk(o):
        yield d
        rj = d.get("record_json")
        if isinstance(rj, str):
            try:
                yield from _records(json.loads(rj))
            except ValueError:
                pass


def _iso(us: int | None) -> str | None:
    if not us:
        return None
    return _dt.datetime.fromtimestamp(us / 1e6, _dt.timezone.utc).isoformat().replace("+00:00", "Z")


def read_session(path: Path) -> dict:
    """The session's workspace and its tasks: request, start and end, model, tokens and the Athos pieces read."""
    workspace, model, tasks, usage_seen = None, "unknown", [], set()
    with open(path, errors="ignore") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            ts = None
            for d in _records(o):
                if ts is None and isinstance(d.get("recorded_at"), int):
                    ts = d["recorded_at"]
                if workspace is None and isinstance(d.get("workspace_root"), str):
                    workspace = d["workspace_root"]
                if d.get("provider_id") and isinstance(d.get("model_id"), str):
                    model = d["model_id"]
                    if tasks:
                        tasks[-1]["model"] = model
                if isinstance(d.get("refill_blocks"), list):
                    text = " ".join(b.get("text", "") for b in d["refill_blocks"] if isinstance(b, dict)).strip()
                    if text and (not tasks or tasks[-1]["request"] != text):
                        tasks.append({"request": text, "start": ts, "end": ts, "model": model, "pieces": set(),
                                      "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}})
                q = d.get("quantity")
                if d.get("usage_family") == "provider" and isinstance(q, dict) and tasks and \
                        d.get("usage_id") not in usage_seen:
                    usage_seen.add(d.get("usage_id"))
                    cached = int(q.get("cached_tokens") or 0)
                    tok = tasks[-1]["tokens"]
                    tok["input"] += int(q.get("input_tokens") or 0) - cached
                    tok["cache_read"] += cached
                    tok["output"] += int(q.get("output_tokens") or 0)
            if tasks:
                tasks[-1]["pieces"] |= set(SKILL_USE.findall(line))
                if ts:
                    tasks[-1]["end"] = ts
    for t in tasks:
        t["tokens"]["total"] = sum(t["tokens"].values())
    return {"session_id": path.parent.name, "workspace": workspace, "tasks": tasks}


def import_sessions(root: Path | None = None, include_tmp: bool = False) -> dict:
    """Record Muse Code's tasks in the evaluation log as platform muse-code. Idempotent: a task is imported once.
    Sessions in temporary folders (tests) are left out unless asked."""
    from athos import eval as ev
    root = root or sessions_dir()
    known = {e.get("task_id") for e in ev.events()}
    pieces = {p.id for p in store.all_pieces()}
    out = {"files": 0, "imported": 0, "skipped": 0}
    for f in sorted(root.glob("*/*/*/*/session.jsonl")) if root.is_dir() else []:
        out["files"] += 1
        s = read_session(f)
        ws = s["workspace"] or ""
        for i, t in enumerate(s["tasks"]):
            tid = f"mu-{s['session_id']}-{i}"
            if tid in known or not t["start"] or (not include_tmp and ws.startswith(TMP_PREFIXES)):
                out["skipped"] += 1
                continue
            ev.append({"type": "task_start", "task_id": tid, "session_id": s["session_id"], "platform": "muse-code",
                       "model": t["model"], "project": Path(ws).name if ws else None, "at": _iso(t["start"]),
                       **ev.request_fields(t["request"]), "source": "muse-import"})
            ev.append({"type": "task_end", "task_id": tid, "session_id": s["session_id"], "at": _iso(t["end"]),
                       "duration_s": round((t["end"] - t["start"]) / 1e6, 1), "tokens": t["tokens"],
                       "model": t["model"], "pieces": sorted(x for x in t["pieces"] if x in pieces), "saved": []})
            known.add(tid)
            out["imported"] += 1
    return out
