"""What the person teaches from Athos's panel in Claude Desktop's chat, on their own press: [Save as a way of working]
and [Change this step]. The chat's model never saves (autolearn.refuse_model_save refuses its athos_save, since the
model is not known there); these two buttons are the person's, so what they write is the person's own piece (no
status), the way the person's [Save] is in Claude Code. Nothing here composes text with a model: the steps the model
reported as new become the piece's statements, and the person's words go into the step they changed."""

from __future__ import annotations

import re
import time

from athos import capture, session, store, wiki

DO_LINE = re.compile(r"^\*\*Do:\*\*[^\n]*$", re.M)


def _quote(value: str) -> str:
    """A frontmatter value on one line, quoted."""
    flat = " ".join(str(value or "").split())
    return '"' + flat.replace('"', '\\"') + '"'


def _sentence(text: str) -> str:
    t = " ".join(str(text or "").split()).strip()
    if not t:
        return t
    t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?…" else t + "."


def _statement_ids(body: str) -> set[str]:
    return set(wiki.STATEMENT.findall(body or ""))


def _new_statements(steps: list[str], taken: set[str]) -> str:
    out = []
    for i, text in enumerate(steps, 1):
        base = store.slugify(text)[:40].strip("-") or f"step-{i}"
        sid, n = base, 2
        while sid in taken:
            sid, n = f"{base}-{n}", n + 1
        taken.add(sid)
        out.append(f"## #{sid}\n**Do:** {_sentence(text)}\n")
    return "\n".join(out)


def _title(request: str, lang: str) -> str:
    t = " ".join((request or "").split()).strip().rstrip(".?!:;, ")
    if not t:
        return "Forma de trabajar del chat" if lang == "es" else "Way of working from the chat"
    if len(t) > 80:
        t = t[:t.rfind(" ", 0, 78)].rstrip(",;:( ") or t[:78]
    return t[0].upper() + t[1:]


def _write(session_id: str, text: str, observe) -> tuple:
    """The person's save, with the chat's state `learning` (why `saving`) while it is written."""
    session.update(session_id, chat_saving=time.time())
    observe()
    try:
        return capture.save_text(text, session_id)
    finally:
        session.update(session_id, chat_saving=None)
        observe()


def saved_count(state: dict) -> int:
    """How many of this task's new steps the person already saved."""
    s = state.get("chat_saved") or {}
    return int(s.get("count") or 0) if s.get("task_id") == state.get("task_id") else 0


def save(session_id: str, view: dict, lang: str, observe=lambda: None) -> dict:
    """[Save as a way of working]: the task's new steps, not saved yet, as the person's own piece. When the task
    follows a piece (`view` names it: only pieces that may be named in the chat), they are added to it as a new
    version; otherwise they make a new piece titled by the request."""
    state = session.load(session_id)
    done = saved_count(state)
    new = list(view.get("new") or [])[done:]
    if not new:
        raise ValueError("nothing new to save: the task reported no steps your know-how lacks")
    followed = next((store.get(p["id"]) for p in view.get("pieces") or [] if store.get(p["id"])), None)
    note = ("pasos nuevos desde el chat: " if lang == "es" else "new steps from the chat: ") + "; ".join(new)
    if followed is not None:
        body = followed.body.rstrip() + "\n\n" + _new_statements(new, _statement_ids(followed.body))
        text = f"---\nid: {followed.id}\nnote: {_quote(note[:200])}\n---\n{body}"
    else:
        request = state.get("task_request") or ""
        body = _new_statements(new, set())
        text = (f"---\ntitle: {_quote(_title(request, lang))}\nwhen: {_quote(request[:200] or _title(request, lang))}"
                f"\nnote: {_quote(note[:200])}\n---\n{body}")
    piece, diff = _write(session_id, text, observe)
    from athos import rating
    rating.note_learned(session_id, piece, bool(diff), text)
    session.update(session_id, chat_saved={"task_id": state.get("task_id"), "id": piece.id, "title": piece.title,
                                           "version": piece.version, "count": done + len(new)})
    return {"ok": True, "id": piece.id, "title": piece.title, "version": piece.version, "improved": bool(diff),
            "steps": len(new)}


def adjust(session_id: str, ref: str, words: str, may_name, lang: str, observe=lambda: None) -> dict:
    """[Change this step]: the person's words go into that step (its **Do:**), as a new version of the piece."""
    pid, _, sid = (ref or "").partition("#")
    words = " ".join(str(words or "").split())
    p = store.get(pid) if pid and may_name(pid) else None
    if p is None or not sid or not words:
        raise ValueError(f"no step {ref!r} to change")
    if sid not in {s.id for s in wiki.statements(p)}:
        raise ValueError(f"no step {ref!r} to change")
    heads = list(wiki.STATEMENT.finditer(p.body))
    if not heads:                                             # a page without statements: one implicit step
        body = p.body.rstrip() + "\n\n" + _sentence(words) + "\n"
    else:
        k = next(k for k, h in enumerate(heads) if h.group(1) == sid)
        start, end = heads[k].end(), heads[k + 1].start() if k + 1 < len(heads) else len(p.body)
        section = p.body[start:end]
        m = DO_LINE.search(section)
        section = (section[:m.end()] + " " + _sentence(words) + section[m.end():] if m
                   else section.rstrip("\n") + f"\n**Do:** {_sentence(words)}\n" + ("\n" if end < len(p.body) else ""))
        body = p.body[:start] + section + p.body[end:]
    note = ("cambiado desde el chat: " if lang == "es" else "changed from the chat: ") + f"#{sid}: {words}"
    text = f"---\nid: {p.id}\nnote: {_quote(note[:200])}\n---\n{body}"
    piece, diff = _write(session_id, text, observe)
    from athos import rating
    rating.note_learned(session_id, piece, bool(diff), text)
    return {"ok": True, "id": piece.id, "title": piece.title, "version": piece.version, "step": sid}
