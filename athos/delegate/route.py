"""Which model each step of a piece needs, learned from your own marks.

    athos route <piece>            per statement: the models that ran it in `athos delegate --by-step`, how those
                                   tasks ended, and the cheapest model that never ended in a correction or a failure
    athos route <piece> --apply    write those suggestions as `**Model:**` lines (a new version; history kept)

A mark is for the whole task, not one step: a step's record is the record of the tasks it ran in. So a model is
suggested for a step only after MIN_RUNS marked runs there, all good; a failure anywhere in the task counts against
every model that ran a step of it. Unmarked runs are counted but prove nothing.
"""

from __future__ import annotations

import re

from athos import eval as ev, store, wiki
from athos.delegate import parse_spec, spec_of

MIN_RUNS = 3
SIZE = re.compile(r"(\d+(?:\.\d+)?)b\b", re.I)


def cost(platform: str, model: str) -> tuple:
    """A rough order of what a model costs to run, cheapest first: a local model before a hosted one, a smaller local
    model (its size in the tag, `gemma4:12b`) before a larger one, Meta's default before its larger models. Only the
    order is used, never shown as a price."""
    if platform == "local":
        m = SIZE.search(model)
        return (0, float(m.group(1)) if m else 1e6, model)
    from athos.adapters import meta
    return (1, 0 if model == meta.DEFAULT_MODEL else 1, model)


def table(piece_id: str, tasks: list[dict] | None = None) -> dict:
    """Per statement of the piece: each model that ran it, with its runs and how those tasks ended, and the
    suggestion (a `**Model:**` spec) or why there is none."""
    piece = store.get(piece_id)
    if piece is None:
        raise LookupError(f"no piece {piece_id}")
    tasks = ev.tasks() if tasks is None else tasks
    runs = [t for t in tasks if piece.id in t.get("pieces", []) and t.get("steps")]
    out = []
    for s in wiki.statements(piece):
        models: dict[tuple[str, str], dict] = {}
        for t in runs:
            for st in t["steps"]:
                if st.get("id") != s.id:
                    continue
                row = models.setdefault((st.get("platform", "local"), st.get("model", "")),
                                        {"runs": 0, "ok": 0, "corrected": 0, "failed": 0, "unevaluated": 0,
                                         "seconds": 0.0, "tokens": 0})
                row["runs"] += 1
                row[t["result"] if t["result"] in row else "unevaluated"] += 1
                row["seconds"] += float(st.get("duration_s") or 0)
                row["tokens"] += int((st.get("tokens") or {}).get("total") or 0)
        clean = [k for k, r in models.items() if r["ok"] >= MIN_RUNS and not r["corrected"] and not r["failed"]]
        best = min(clean, key=lambda k: cost(*k)) if clean else None
        tried = any(r["ok"] + r["corrected"] + r["failed"] >= MIN_RUNS for r in models.values())
        why = None if best else ("every model with enough marked runs here ended corrected or failed at least once"
                                 if tried else f"not enough runs (a model needs {MIN_RUNS} good marked runs here)")
        out.append({"id": s.id, "current": s.model, "suggest": spec_of(*best) if best else None, "why": why,
                    "models": [{"platform": p, "model": m, **r} for (p, m), r in
                               sorted(models.items(), key=lambda kv: cost(*kv[0]))]})
    return {"piece": piece.id, "title": piece.title, "tasks": len(runs), "steps": out}


def render(r: dict) -> str:
    lines = [f"{r['title']} ({r['piece']}): {r['tasks']} by-step delegation(s).", ""]
    if not r["tasks"]:
        return lines[0] + "\nNo runs yet: `athos delegate " + r["piece"] + ' "<request>" --by-step`, then mark it.'
    for s in r["steps"]:
        lines.append(f"#{s['id']}" + (f"  (now: {s['current']})" if s["current"] else ""))
        for m in s["models"]:
            avg = f"{m['seconds'] / m['runs']:.0f} s, {m['tokens'] // m['runs']:,} tokens per run"
            lines.append(f"  {spec_of(m['platform'], m['model']):28} {m['runs']} run(s): {m['ok']} good, "
                         f"{m['corrected']} corrected, {m['failed']} failed, {m['unevaluated']} unmarked · {avg}")
        if not s["models"]:
            lines.append("  never run step by step")
        lines.append(f"  → {s['suggest']}" if s["suggest"] else f"  → {s['why']}")
    lines += ["", "A mark is for the whole task, so each step shares its task's mark."]
    return "\n".join(lines)


def with_models(body: str, specs: dict[str, str]) -> str:
    """The body with each statement in `specs` given that `**Model:**` line (replaced if it had one, else added after
    its last field). Everything else stays as written."""
    heads = list(wiki.STATEMENT.finditer(body))
    out, pos = [], 0
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        text = body[h.end():end]
        if h.group(1) in specs:
            line = f"**Model:** {specs[h.group(1)]}"
            if re.search(r"^\*\*Model:\*\*.*$", text, re.M):
                text = re.sub(r"^\*\*Model:\*\*.*$", line, text, count=1, flags=re.M)
            else:
                fields = list(wiki.FIELD.finditer(text))
                at = fields[-1].end() if fields else len(text.rstrip("\n"))
                text = text[:at] + "\n" + line + text[at:]
        out += [body[pos:h.end()], text]
        pos = end
    return "".join(out) + body[pos:]


def apply(piece_id: str, tasks: list[dict] | None = None) -> tuple[store.Piece | None, dict]:
    """Write the suggestions that differ from the piece's current lines. Returns the new version (None when nothing
    changes) and the table it came from."""
    r = table(piece_id, tasks)
    specs = {s["id"]: s["suggest"] for s in r["steps"]
             if s["suggest"] and parse_spec(s["current"] or "") != parse_spec(s["suggest"])}
    if not specs:
        return None, r
    piece = store.get(piece_id)
    new, _ = store.update(piece.id, "routed by results", body=with_models(piece.body, specs),
                          origin={"platform": "athos", "model": "route"})
    try:
        wiki.rebuild()
    except OSError:
        pass
    return new, r
