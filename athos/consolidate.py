"""The overnight review ("dream"): what of the day's work should go into permanent memory.

During the day Athos only records: the stars the person gave each step, what the agent said it did there, the branches
each task took or skipped, and the tasks the person marked corrected or failed. The review reads that log and
proposes; it never writes a page. A proposal carries its evidence (which ratings, which tasks, what was done) and,
when the person approves it, becomes an ordinary adjust request that their agent (Claude or Codex) carries out in
sight, the way [Change this step] does.

- avoid: a step rated 1-2 at least twice, or rated 1-2 once in a task the person also marked corrected or failed
- keep:  a step rated 4-5 at least twice: what was done there is a mechanic to write down so it repeats
- trajectories: for each branch, how often tasks took it and the stars its steps got (for picking it next time)

A proposal is not repeated once the page changed after its evidence (the agent already acted on it), and a rating
counts once. `review()` is pure (events and pages in, proposals out), so a week of logs can be replayed without
touching the store.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from athos import paths

LOW, HIGH = 2, 4
EVERY = 20 * 3600            # at most one review this often, at session start


class Review:
    """Athos's own consolidator: counted evidence, no model, nothing written."""

    def review(self, events: Iterable[dict], pieces: list) -> dict:
        events = list(events)
        by_id = {p.id: p for p in pieces}
        ratings = [e for e in events if e.get("type") == "rating" and e.get("piece") and e.get("step")]
        marked = {e["task_id"]: e.get("result") for e in events if e.get("type") == "mark"}
        bad_tasks = {t for t, r in marked.items() if r in ("corrected", "failed", "c", "f")}

        steps: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in ratings:
            steps[(r["piece"], r["step"])].append(r)

        proposals = []
        for (piece, step), rs in sorted(steps.items()):
            page = by_id.get(piece)
            if not page:
                continue
            # Ratings given on an older version were already acted on (the page changed since).
            fresh = [r for r in rs if (r.get("version") or page.version) >= page.version]
            low = [r for r in fresh if r["stars"] <= LOW]
            high = [r for r in fresh if r["stars"] >= HIGH]
            low_and_bad = [r for r in low if r.get("task_id") in bad_tasks]
            label = next((r.get("label") for r in reversed(rs) if r.get("label")), step)
            if len(low) >= 2 or low_and_bad:
                proposals.append(_proposal("avoid", piece, step, label, page.title, low))
            elif len(high) >= 2:
                proposals.append(_proposal("keep", piece, step, label, page.title, high))

        return {"proposals": proposals, "trajectories": _trajectories(events, ratings)}


def _proposal(kind: str, piece: str, step: str, label: str, title: str, rs: list[dict]) -> dict:
    evidence = [{"rating": r.get("id"), "stars": r["stars"], "at": r.get("at"), "request": (r.get("request") or "")[:120],
                 "did": r.get("did", "")} for r in rs]
    return {"id": f"{kind}:{piece}#{step}", "kind": kind, "piece": piece, "step": step, "label": label, "title": title,
            "evidence": evidence}


def _trajectories(events: list[dict], ratings: list[dict]) -> list[dict]:
    """For each page a task walked (a branch included): how many tasks went through it, and the stars it got."""
    tasks_of: dict[str, set[str]] = defaultdict(set)
    for e in events:
        if e.get("type") == "trail" and e.get("kind") == "step" and e.get("piece") and e.get("task_id"):
            tasks_of[e["piece"]].add(e["task_id"])
    stars: dict[str, list[int]] = defaultdict(list)
    for r in ratings:
        stars[r["piece"]].append(r["stars"])
    return [{"page": page, "tasks": len(ts), "stars": round(sum(stars[page]) / len(stars[page]), 2) if stars[page] else None}
            for page, ts in sorted(tasks_of.items(), key=lambda kv: -len(kv[1]))]


# ------------------------------------------------------------------------------------------------ the stored review
def path() -> Path:
    return paths.home() / "dream.json"


def last() -> dict:
    try:
        return json.loads(path().read_text())
    except (OSError, ValueError):
        return {}


def run(events: Iterable[dict] | None = None, write: bool = True) -> dict:
    """Review the log with the consolidator in use; keep the result unless it is a dry run (a replay)."""
    from athos import services
    rec, st = services.get("recorder"), services.get("store")
    out = services.get("consolidator").review(rec.events() if events is None else events, st.all_pieces())
    done = set(last().get("applied") or [])
    out["proposals"] = [p for p in out["proposals"] if p["id"] not in done]
    out["at"] = time.time()
    if write:
        out["applied"] = sorted(done)
        path().write_text(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def due() -> bool:
    return time.time() - (last().get("at") or 0) > EVERY


def request(p: dict, lang: str) -> str:
    """An approved proposal as the adjust request the person's agent carries out (in Claude or Codex alike)."""
    from athos import capture
    did = "; ".join(f"«{e['did']}»" for e in p["evidence"] if e.get("did"))[:400]
    n = len(p["evidence"])
    if lang == "es":
        what = (f"lo califiqué bajo {n} {'vez' if n == 1 else 'veces'}"
                + (f"; lo que hiciste ahí: {did}" if did else "")
                + ". Escribí en ese paso una regla que evite eso.") if p["kind"] == "avoid" else \
               (f"lo califiqué alto {n} veces" + (f"; lo que hiciste ahí: {did}" if did else "")
                + ". Escribí en ese paso lo que funcionó, para que se repita.")
    else:
        what = (f"I rated it low {n} time{'s' if n != 1 else ''}" + (f"; what you did there: {did}" if did else "")
                + ". Write into that step a rule that avoids it.") if p["kind"] == "avoid" else \
               (f"I rated it high {n} times" + (f"; what you did there: {did}" if did else "")
                + ". Write into that step what worked, so it repeats.")
    return f"{capture.ADJUST_PREFIX['es' if lang == 'es' else 'en']} {p['piece']}#{p['step']}: {what}"


def apply(n: int, lang: str) -> str:
    """The person approved proposal n (1-based): its adjust request, and it won't be proposed again."""
    st = last()
    props = st.get("proposals") or []
    if not 1 <= n <= len(props):
        raise IndexError(f"no proposal {n}: there are {len(props)}")
    p = props[n - 1]
    st["applied"] = sorted({*(st.get("applied") or []), p["id"]})
    st["proposals"] = [x for x in props if x["id"] != p["id"]]
    path().write_text(json.dumps(st, ensure_ascii=False, indent=2))
    return request(p, lang)


def summary(st: dict, lang: str) -> str:
    props = st.get("proposals") or []
    es = lang == "es"
    if not props:
        return "La revisión no encontró nada para guardar." if es else "The review found nothing to keep."
    lines = [("La revisión propone, para tu memoria permanente:" if es else "The review proposes, for your permanent memory:")]
    for i, p in enumerate(props, 1):
        stars = ", ".join(f"{e['stars']}★" for e in p["evidence"])
        verb = ("evitar" if p["kind"] == "avoid" else "repetir") if es else ("avoid" if p["kind"] == "avoid" else "repeat")
        lines.append(f"{i}. «{p['title']}» · «{p['label']}» → {verb} ({stars})")
    lines.append(("Para aplicar una: `athos dream --apply N`." if es else "To apply one: `athos dream --apply N`."))
    return "\n".join(lines)
