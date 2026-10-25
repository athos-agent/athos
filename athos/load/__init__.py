"""Load: only the know-how that matters for the request reaches the model.

At session start, a short index of the enabled pieces (id, title, when it applies). On every prompt, the full text
of the one or two pieces whose title and "when" match the request best, under a character cap. Never the whole store.
"""

from __future__ import annotations

import math
import re

from athos import control, session, store

INDEX_CAP = 4000
INJECT_CAP = 8000
TOP_K = 2
MIN_SCORE = 2.0

STOP = set("""a an the and or but if then else for to of in on at by with from into over this that these those it its
is are was were be been being do does did done have has had can could should would will shall may might must not no
yes you your we our i me my he she they them their there here what which who whom when where why how all any each
some such than too very just also only own same so as about after before again more most other up down out off
el la los las un una unos unas y o pero si entonces para por de del en con sin sobre este esta estos estas ese esa
eso es son fue ser hay que qué cual cuál cuando cuándo donde dónde como cómo porque muy más menos ya lo le les se su
sus mi mis tu tus al me te nos""".split())


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-záéíóúñü0-9_.-]{3,}", text.lower()) if w not in STOP]


def enabled(cwd: str | None = None) -> list[store.Piece]:
    return control.filter_pieces(store.all_pieces(), cwd)


def index_text(pieces: list[store.Piece], cmd: str = "athos") -> str:
    if not pieces:
        return ""
    head = ("# Athos — your know-how\n\nThese pieces of the user's own know-how are available. When a request "
            "matches a piece's \"when\", follow it; the matching piece is usually added to the request "
            f"automatically, and `{cmd} show <id>` prints any of them.\n")
    lines, size = [], len(head)
    for p in sorted(pieces, key=lambda p: p.last_used, reverse=True):
        line = f"- `{p.id}` — {p.title}. When: {p.when}"
        if size + len(line) + 1 > INDEX_CAP:
            lines.append(f"- … and {len(pieces) - len(lines)} more (`{cmd} list`)")
            break
        lines.append(line)
        size += len(line) + 1
    return head + "\n".join(lines)


def rank(prompt: str, pieces: list[store.Piece]) -> list[tuple[float, store.Piece]]:
    """Score each piece by the request's words found in its title and "when" (weighted by how rare the word is
    among the pieces), plus a little for words found in its body."""
    q = set(tokens(prompt))
    if not q or not pieces:
        return []
    heads = [set(tokens(p.title + " " + p.when)) for p in pieces]
    bodies = [set(tokens(p.body)) for p in pieces]
    n = len(pieces)

    def idf(w):
        df = sum(1 for h, b in zip(heads, bodies) if w in h or w in b)
        return math.log(1 + n / (1 + df)) + 1
    scored = []
    for p, h, b in zip(pieces, heads, bodies):
        s = sum(idf(w) for w in q & h) + 0.25 * sum(idf(w) for w in (q & b) - h)
        if len(q & h) >= 1 and s >= MIN_SCORE:
            scored.append((s, p))
    return sorted(scored, key=lambda t: (-t[0], t[1].id))


def relevant(prompt: str, pieces: list[store.Piece]) -> list[store.Piece]:
    out, size = [], 0
    for _, p in rank(prompt, pieces)[:TOP_K]:
        text = store.render(p)
        if size + len(text) > INJECT_CAP:
            break
        out.append(p)
        size += len(text)
    return out


def inject_text(pieces: list[store.Piece]) -> str:
    if not pieces:
        return ""
    parts = ["# Athos — know-how that matches this request\n\nThe user's own know-how for this kind of task. "
             "Follow it unless the request says otherwise.\n"]
    for p in pieces:
        parts.append(f"## {p.title} (`{p.id}`, v{p.version})\nWhen: {p.when}\n\n{p.body}\n")
    return "\n".join(parts)


def on_prompt(event: dict) -> str:
    """UserPromptSubmit: the pieces that match the request, recorded as loaded in this session."""
    sid = event.get("session_id", "default")
    found = relevant(event.get("prompt", ""), enabled(event.get("cwd")))
    if found:
        state = session.load(sid)
        state["loaded"] = sorted(set(state.get("loaded", [])) | {p.id for p in found})
        session.save(sid, state)
        for p in found:
            store.touch(p.id)
    return inject_text(found)


def on_session_start(event: dict, cmd: str = "athos") -> str:
    sid = event.get("session_id", "default")
    model = event.get("model")
    if isinstance(model, dict):
        model = model.get("id") or model.get("display_name")
    if model:
        session.update(sid, model=str(model))
    return index_text(enabled(event.get("cwd")), cmd)
