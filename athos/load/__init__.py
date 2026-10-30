"""Load: only the know-how that matters for the request reaches the model.

At session start, a short index of the enabled pieces (id, title, when it applies). On every prompt, the full text
of the one or two pieces whose title and "when" match the request best, under a character cap. Never the whole store.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata

from athos import control, eval as ev, paths, session, store

INDEX_CAP = 4000
INJECT_CAP = 8000
TOP_K = 2
RUNNER_UP = 0.5      # a second piece loads only with at least half the best piece's score (one shared word is noise)
MIN_SCORE = 1.2
STEM = 5               # words match on their first letters, so "release" finds "releasing" and "releases"
ONE_WORD_DF = 1        # one shared word is enough only if no other piece's title has it

STOP = set("""a an the and or but if then else for to of in on at by with from into over this that these those it its
is are was were be been being do does did done have has had can could should would will shall may might must not no
yes you your we our i me my he she they them their there here what which who whom when where why how all any each
some such than too very just also only own same so as about after before again more most other up down out off
el la los las un una unos unas y o pero si entonces para por de del en con sin sobre este esta estos estas ese esa
eso es son fue ser hay que qué cual cuál cuando cuándo donde dónde como cómo porque muy más menos ya lo le les se su
sus mi mis tu tus al me te nos""".split())


def words(text: str) -> set[str]:
    """Whole words, for the exact match: file names and punctuation split ("contrato-servicios.md" is "contrato" and
    "servicios"), accents dropped ("locación" is "locacion")."""
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]{3,}", plain) if w not in STOP_PLAIN}


STOP_PLAIN = {unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode() for w in STOP}


def tokens(text: str) -> list[str]:
    return [w[:STEM] for w in re.findall(r"[a-záéíóúñü0-9_.-]{3,}", text.lower()) if w not in STOP]


def _plain(w: str) -> str:
    return w[:-1] if len(w) > 4 and w.endswith("s") else w


# Messages the agent itself receives (a background task finishing), not requests the person typed.
NOT_A_REQUEST = re.compile(r"^\s*<(task-notification|system-reminder)>")


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


def misfires_file():
    return paths.home() / "misfires.json"


def misfires() -> dict[str, list[list[str]]]:
    """Loads the person said did not apply ([Didn't apply]): per piece, the shared words that loaded it then."""
    try:
        return json.loads(misfires_file().read_text())
    except (OSError, ValueError):
        return {}


def why(prompt: str, piece: store.Piece) -> list[str]:
    """The request's words found in the piece's title and "when": what made it load, as the person can read it."""
    return sorted({_plain(w) for w in words(prompt)} & {_plain(w) for w in words(piece.title + " " + piece.when)})


def dismiss(piece_id: str, shared: list[str]) -> None:
    """The person said this load did not apply: the same words never load this piece again."""
    data = misfires()
    sets = data.setdefault(piece_id, [])
    if sorted(shared) not in sets:
        sets.append(sorted(shared))
    misfires_file().parent.mkdir(parents=True, exist_ok=True)
    misfires_file().write_text(json.dumps(data, indent=1, ensure_ascii=False))


def rank(prompt: str, pieces: list[store.Piece]) -> list[tuple[float, store.Piece]]:
    """Score each piece by the request's words found in its title and "when" (weighted by how rare the word is
    among the pieces), plus a little for words found in its body."""
    q = set(tokens(prompt))
    if not q or not pieces or NOT_A_REQUEST.match(prompt):
        return []
    qwords = {_plain(w) for w in words(prompt)}
    heads = [set(tokens(p.title + " " + p.when)) for p in pieces]
    head_words = [{_plain(w) for w in words(p.title + " " + p.when)} for p in pieces]
    title_words = [{_plain(w) for w in words(p.title)} for p in pieces]
    bodies = [set(tokens(p.body)) for p in pieces]
    n = len(pieces)

    def idf(w):
        df = sum(1 for h, b in zip(heads, bodies) if w in h or w in b)
        return math.log(1 + n / (1 + df)) + 1

    def enough(hw, tw):
        # Shared prefixes only add to the score ("checklist" starts like "check", "contrato" like "controls"): a
        # piece needs the very same words: two of them, or one of five letters or more that only its title has.
        same = qwords & hw
        return len(same) >= 2 or any(len(w) >= 5 and sum(1 for o in title_words if w in o) <= ONE_WORD_DF
                                     for w in same & tw)
    wrong = misfires()
    scored = []
    for p, h, hw, tw, b in zip(pieces, heads, head_words, title_words, bodies):
        shared = q & h
        s = sum(idf(w) for w in shared) + 0.25 * sum(idf(w) for w in (q & b) - h)
        # Words the person already said were not enough for this piece don't load it again.
        if any(set(qwords & hw) <= set(m) for m in wrong.get(p.id, [])):
            continue
        if shared and s >= MIN_SCORE and enough(hw, tw):
            scored.append((s, p))
    return sorted(scored, key=lambda t: (-t[0], t[1].id))


def relevant(prompt: str, pieces: list[store.Piece]) -> list[store.Piece]:
    out, size = [], 0
    ranked = rank(prompt, pieces)[:TOP_K]
    for score, p in ranked:
        if out and score < RUNNER_UP * ranked[0][0]:  # a second piece only when it matches nearly as well
            break
        text = store.render(p)
        if out and size + len(text) > INJECT_CAP:  # the best piece always loads whole; the cap limits a second one
            break
        out.append(p)
        size += len(text)
    return out


def inject_text(pieces: list[store.Piece]) -> str:
    if not pieces:
        return ""
    first = pieces[0].title
    parts = ["# Athos — know-how that matches this request\n\nThe user's own know-how for this kind of task. "
             "Follow it unless the request says otherwise.\n"]
    for p in pieces:
        parts.append(f"## {p.title} (`{p.id}`, v{p.version})\nWhen: {p.when}\n\n{p.body}\n")
    # The person watches the trail in Athos's pane (Claude Code) or `athos watch`: one call per step, not per action.
    parts.append(f"**As you go**, when you start one of these statements run `athos step <piece-id>#<statement_id>` "
                 f"(once per statement, not per action); if the task needs a step none of them has, run "
                 f"`athos step --new \"<the step, in a few words, in the person's language>\"`. Say nothing about it "
                 f"in your answer.\n")
    # The person may be a lawyer or a coach, not the author of the piece's notes (2026-10-30, Claude Desktop: answers
    # narrated tools, cited "piece v7" and pasted the piece's commands until told otherwise).
    parts.append("**How to answer**: plainly, in the person's language, as a colleague who already knows how they work: "
                 "do the task or answer the question directly. Don't narrate tools or say you are reading something; "
                 "after the first line, don't mention Athos, pieces, ids, versions, or the dates, measurements and notes "
                 "the piece keeps for you; give commands, paths or settings only when the person must act on them. "
                 "Take from the piece only what this request needs.\n")
    # Last, so it is the freshest instruction: the person sees which of their know-how is applied, in every agent.
    parts.append(f"**The first line of your reply** names the way of working you follow and how it applies to this "
                 f"request, in the person's language, in this form: `Athos · «{first}»: <how it applies here, in a few "
                 f"words>` (in Spanish the same, with the explanation in Spanish). If it does not fit this request, "
                 f"say so in that line and don't follow it.\n")
    return "\n".join(parts)


def mark_loaded(session_id: str, ids: list[str]) -> None:
    """Record pieces as used in a session: by automatic injection, or when Claude reads one with `athos show`."""
    if not ids:
        return
    state = session.load(session_id)
    state["loaded"] = sorted(set(state.get("loaded", [])) | set(ids))
    session.save(session_id, state)
    ev.note_loaded(session_id, ids)
    for pid in ids:
        store.touch(pid)


def on_prompt(event: dict) -> str:
    """UserPromptSubmit: the pieces that match the request, recorded as loaded in this session, with the words that
    loaded each one (the band shows them, and [Didn't apply] remembers them)."""
    prompt = event.get("prompt", "")
    found = relevant(prompt, enabled(event.get("cwd")))
    if found:
        session.update(event.get("session_id", "default"), task_why={p.id: why(prompt, p) for p in found})
    mark_loaded(event.get("session_id", "default"), [p.id for p in found])
    return inject_text(found)


def on_session_start(event: dict, cmd: str = "athos") -> str:
    sid = event.get("session_id", "default")
    model = event.get("model")
    if isinstance(model, dict):
        model = model.get("id") or model.get("display_name")
    if model:
        session.update(sid, model=str(model))
    from athos import capture
    text = index_text(enabled(event.get("cwd")), cmd)
    if text and capture.enabled():               # with the guide given here, the Stop hook only needs one line
        text += "\n\n" + capture.guide(cmd)
        session.update(sid, guide=True)
    return text
