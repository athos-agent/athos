"""The person's 1–5 stars on a moment of a task, given from Athos's panel at any time.

A rating is the only thing the panel asks of the person, for the current step or any earlier one they open. It keeps
the moment (the request, the page and step, what the agent said it did there, the branches taken) with the stars, in
events.jsonl, and the next Athos result the model reads reports it as a plain fact. What a rating means (1-2: a rule
to avoid on that step; 4-5: the mechanic that worked, so it repeats; 3: nothing) is said openly in athos_find's
result and in the Desktop skill, never as a hidden instruction: Claude rightly refused one that asked it to change
the notes and keep quiet (2026-11-11). A rating only reaches the task it was given in, or one started soon after.
"""

from __future__ import annotations

import time
import uuid

from athos import session, store, trail

PENDING = "pending_rating"


def _now_step(view: dict) -> dict:
    """Where the task is: the current step of the first page, else the last one done, else the page itself."""
    p = (view.get("pieces") or [{}])[0]
    steps = p.get("steps") or []
    cur = next((x for x in steps if x.get("state") == "now"), None) \
        or next((x for x in reversed(steps) if x.get("state") == "done"), None)
    if not cur:
        return {"piece": p.get("id"), "title": p.get("title")} if p.get("id") else {}
    return {"piece": cur.get("piece") or p.get("id"), "page": p.get("id"), "title": p.get("title"),
            "step": cur.get("id"), "label": (cur.get("label") or "").removeprefix("↳ ")}


def _chosen(view: dict, piece: str | None, step: str | None) -> dict:
    """The step the person rated: the one they opened in the panel, else where the task is now."""
    p = (view.get("pieces") or [{}])[0]
    if piece and not step:                      # the whole task, from the receipt
        return {"piece": piece, "page": p.get("id"), "title": p.get("title")}
    for x in p.get("steps") or []:
        if step and x.get("id") == step and (x.get("piece") or p.get("id")) == (piece or x.get("piece") or p.get("id")):
            return {"piece": x.get("piece") or p.get("id"), "page": p.get("id"), "title": p.get("title"),
                    "step": x["id"], "label": (x.get("label") or "").removeprefix("↳ "), "did": x.get("did", "")}
    return _now_step(view)


def snapshot(state: dict, piece: str | None = None, step: str | None = None) -> dict:
    """The moment the stars are about: what was asked, which step, what the agent did there, the branches."""
    view = trail.view(state)
    p = (view.get("pieces") or [{}])[0]
    steps = p.get("steps") or []
    return {"task_id": state.get("task_id"), "request": state.get("task_request", ""), **_chosen(view, piece, step),
            "done": [x.get("id") for x in steps if x.get("state") == "done"],
            "taken": [x["via"] for x in steps if x.get("via") and x.get("state") in ("done", "now")],
            "skipped": [x["via"] for x in steps if x.get("via") and x.get("state") == "skipped"],
            "new": view.get("new") or []}


def rate(session_id: str, stars: int, piece: str | None = None, step: str | None = None) -> dict:
    """Keep the stars with their moment, and leave the learning pending for the model's next Athos call."""
    from athos import eval as ev
    stars = int(stars)
    if not 1 <= stars <= 5:
        raise ValueError("stars must be 1 to 5")
    state = session.load(session_id)
    r = {"type": "rating", "id": uuid.uuid4().hex[:8], "stars": stars, "at": ev._iso(ev.now()),
         "session": session_id, "platform": state.get("platform") or "claude-desktop", "t": round(time.time(), 1),
         **snapshot(state, piece, step)}
    page = store.get(r.get("piece") or "")
    if page:
        r["version"] = page.version            # the review only counts ratings on the page as it is now
    ev.append(r)
    session.update(session_id, **{PENDING: r, "last_rating": {"stars": stars, "t": round(time.time(), 1),
                                                                "piece": r.get("piece"), "step": r.get("step")}})
    return r


def instruction(r: dict) -> str:
    """The rating as the model reads it: a fact, from the person, about one step. No orders, nothing hidden."""
    where = f"step «{r['label']}» ({r['piece']}#{r['step']})" if r.get("step") else \
        (f"«{r['title']}» ({r['piece']})" if r.get("piece") else "a task with no saved way of working yet")
    did = f" There you had done: {r['did'].rstrip('. ')}." if r.get("did") else ""
    return (f"Rating from the person, in Athos's panel: {r['stars']}/5 on {where}, in the task «"
            f"{(r.get('request') or '')[:120]}».{did} (What ratings mean is in Athos's instructions for ratings.)")


def note_learned(session_id: str, piece, diff: bool, text: str) -> None:
    """A save during the task: shown in the receipt with its note and an undo (back to the version before)."""
    import re
    note = re.search(r"^note:\s*(.+)$", text or "", re.M)
    learned = list(session.load(session_id).get("task_learned") or [])
    learned.append({"id": piece.id, "title": piece.title, "version": piece.version,
                    "before": piece.version - 1 if diff else None,
                    **({"note": note.group(1).strip()[:160]} if note else {})})
    session.update(session_id, task_learned=learned[-5:])


# What a rating means, said openly once per task, in every agent: Desktop's athos_find result, and the request's
# context in Claude Code and Codex. Never as a hidden order (2026-11-11: Claude refused one as a prompt injection).
POLICY = ("Ratings: the person can rate any step 1-5 stars in Athos's panel instead of being asked questions. When "
          "Athos reports one, learn from it by improving that way of working (its id and a note): 1-2 stars, add to "
          "that step what to avoid, from what you did there; 4-5, write into that step what worked, so it repeats; "
          "3, nothing. Then say in one short line what you changed.")


FRESH = 30 * 60          # a rating older than this, from another task, is not passed on


def take_pending(session_id: str) -> str:
    """The pending rating, once, in the next result the model reads: only in the task it was given in, or a task
    started soon after (a rating from an earlier chat reached an unrelated task, 2026-11-11)."""
    state = session.load(session_id)
    r = state.get(PENDING)
    if not r:
        return ""
    session.update(session_id, **{PENDING: None})
    same = r.get("task_id") and r.get("task_id") == state.get("task_id")
    if not same and time.time() - (r.get("t") or 0) > FRESH:
        return ""
    return instruction(r)


def history(piece: str | None, step: str | None, limit: int = 3) -> list[dict]:
    """Earlier stars at this same step (or page), newest first: context the panel shows when the task gets there."""
    from athos import eval as ev
    if not piece:
        return []
    out = [e for e in ev.events() if e.get("type") == "rating" and e.get("piece") == piece
           and (step is None or e.get("step") == step)]
    return [{"stars": e["stars"], "at": e.get("at"), "request": (e.get("request") or "")[:80]}
            for e in reversed(out[-limit:])]


def panel_info(session_id: str, view: dict) -> dict:
    """What the panel shows besides the trail: the step it is on, earlier stars there, the last rating given, and
    when the trail last moved (the panel animates on it)."""
    state = session.load(session_id)
    now = _now_step(view)
    moved = max([x.get("t", 0) for x in state.get("trail") or []], default=0)
    exists = bool(now.get("piece") and store.get(now["piece"]))
    return {"now": now, "earlier": history(now.get("piece"), now.get("step")) if exists else [],
            "last_rating": state.get("last_rating"), "moved": moved}
