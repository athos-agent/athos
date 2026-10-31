"""Short-term memory: what happened lately in a project, read from the task log Athos already keeps.

The ways of working are the long-term memory (pages that change only when the person saves or approves). Next to
them, a session needs the recent past of its own project: the last requests, what each followed or saved, how it
went, and what was left corrected or failed. That is the journal. It is a view over `events.jsonl` (nothing new is
written), one per project, and only the latest tasks: older ones are summed up per way of working, so the journal
stays short however long the project runs. Everything stays local.
"""

from __future__ import annotations

import re
import time
from collections import Counter

from athos import eval as ev, store

RECENT = 6              # tasks shown one by one; older ones are only counted
OPEN_DAYS = 7           # a corrected or failed task stays "open" this long
REQUEST_CHARS = 90
# Harness messages and Athos's own requests are not the person's work.
NOISE = re.compile(r"^\s*(<(task-notification|system-reminder|agent-message)[\s>]|Athos · )")
RESULT = {"ok": "good", "corrected": "corrected", "failed": "failed", "unevaluated": "not marked"}


def _when(t: dict) -> str:
    """Local time, as the person lives it (the log keeps UTC)."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(t["started"]).astimezone().strftime("%Y-%m-%d %H:%M")
    except (KeyError, TypeError, ValueError):
        return (t.get("started") or "")[:16].replace("T", " ")


def _line(t: dict, titles: dict[str, str]) -> str:
    # `titles` holds only pages that belong here (this project's or general ones): a page of another project that
    # loaded by mistake in an old task is not part of this project's past.
    req = " ".join((t.get("request") or "").split())
    req = req[:REQUEST_CHARS] + ("…" if len(req) > REQUEST_CHARS else "")
    followed = [titles[p] for p in t.get("pieces") or [] if p in titles][:2]
    saved = [titles.get(p, p) for p in t.get("saved") or []][:2]
    bits = [f"- {_when(t)} · {t.get('platform', '?')} · «{req}»"]
    if followed:
        bits.append("with " + ", ".join(f"«{x}»" for x in followed))
    if saved:
        bits.append("saved " + ", ".join(f"«{x}»" for x in saved))
    bits.append(RESULT.get(t.get("result"), t.get("result", "")))
    return " · ".join(bits)


def tasks_of(project: str) -> list[dict]:
    """The project's tasks, newest first, without harness messages."""
    ts = [t for t in ev.tasks() if t.get("project") == project and t.get("request")
          and not NOISE.match(t["request"])]
    return sorted(ts, key=lambda t: t.get("started") or "", reverse=True)


def text(project: str) -> str:
    """The journal as the session reads it: the last tasks, what is open, and the older ones counted."""
    ts = tasks_of(project)
    if not ts:
        return ""
    titles = {p.id: p.title for p in store.all_pieces() if not p.projects or project in p.projects}
    lines = [f"Recently in {project} (newest first):"] + [_line(t, titles) for t in ts[:RECENT]]
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - OPEN_DAYS * 86400))
    open_ = [t for t in ts if t.get("result") in ("corrected", "failed") and (t.get("started") or "") >= cutoff]
    if open_:
        lines.append(f"Open (corrected or failed in the last {OPEN_DAYS} days): "
                     + "; ".join(f"«{' '.join(t['request'].split())[:60]}»" for t in open_[:3]))
    older = ts[RECENT:]
    if older:
        used = Counter(p for t in older for p in t.get("pieces") or [] if p in titles)
        top = ", ".join(f"«{titles[p]}» ×{n}" for p, n in used.most_common(3))
        lines.append(f"Before that: {len(older)} tasks" + (f", most with {top}" if top else "") + ".")
    return "\n".join(lines)
