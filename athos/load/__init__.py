"""The router: deciding which of the person's ways of working reach the model, and when.

Two moments matter. When a session opens, the model gets a compact catalogue of the pages it may use (id, title and
the "when" line), never their bodies. When the person sends a request, the page or two that fit it best are added in
full, within a size budget. The store as a whole is never pasted in.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata

from athos import control, eval as ev, paths, session, store

# Size budgets, in characters.
INDEX_CAP = 4000         # the session-start catalogue
INJECT_CAP = 8000        # the pages added to one request (the best page is exempt: it always comes whole)

# Lexical ranking.
TOP_K = 2                # at most this many pages are picked by score
RUNNER_UP = 0.5      # a second piece loads only with at least half the best piece's score (one shared word is noise)
MIN_SCORE = 1.2          # below this a page is not worth adding
STEM = 5                 # tokens are cut to this length, so "release", "releases" and "releasing" all meet
ONE_WORD_DF = 1        # one shared word is enough only if no other piece's title has it
# The meaning (`athos embed on`, load/embed.py), set with `athos bench route`:
SURE_SCORE = 8.0       # a lexical first piece this strong, alone at the top, needs no second opinion
MEANING_MIN = 0.20     # a piece found by meaning alone: the closest one, this far above its closeness to any request
MEANING_WEIGHT = 0.9   # its score, as a share of the words' best piece: it comes after what the words found

_ENGLISH_STOPWORDS = """
    a about after again all also an and any are as at be been before being but by can could did do does done down each
    else for from had has have he here how i if in into is it its just may me might more most must my no not of off on
    only or other our out over own same shall she should so some such than that the their them then there these they
    this those to too up very was we were what when where which who whom why will with would yes you your
"""
_SPANISH_STOPWORDS = """
    al como cómo con cual cuál cuando cuándo de del donde dónde el en entonces es esa ese eso esta este estas estos fue
    hay la las le les lo los me mis mi más menos muy nos o para pero por porque que qué se ser si sin sobre son su sus
    te tu tus un una unas unos y ya
"""
STOP = set(_ENGLISH_STOPWORDS.split()) | set(_SPANISH_STOPWORDS.split())


def _fold(text: str) -> str:
    """Lowercase-free accent folding: "locación" becomes "locacion"; characters with no ASCII form are dropped."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def words(text: str) -> set[str]:
    """Whole words, for the exact match: file names and punctuation split ("contrato-servicios.md" is "contrato" and
    "servicios"), accents dropped ("locación" is "locacion")."""
    plain = _fold(text.lower())
    return {w for w in re.findall(r"[a-z0-9]{3,}", plain) if w not in STOP_PLAIN}


STOP_PLAIN = {_fold(w) for w in STOP}

_TOKEN = re.compile(r"[a-záéíóúñü0-9_.-]{3,}")


def tokens(text: str) -> list[str]:
    """Stemmed tokens for scoring: each run of three or more word characters (dots, dashes and underscores kept, so
    file names stay whole), stopwords dropped, then cut to its first STEM letters."""
    found = _TOKEN.findall(text.lower())
    return [token[:STEM] for token in found if token not in STOP]


# Endings that only inflect a word (publish / published / publishing; publicar / publicado): "the same word" for the
# rule in rank(). "We got a tip … can we publish it?" missed the page "…before it is published" (2026-10-31).
ENDINGS = ("ings", "ing", "ed", "es", "s", "ados", "adas", "ado", "ada", "ar", "er", "ir")


def _plain(w: str) -> str:
    for e in ENDINGS:
        if w.endswith(e) and len(w) - len(e) >= 4:
            return w[:-len(e)]
    return w


def _base_words(text: str) -> set[str]:
    """`words`, each reduced to its uninflected form."""
    return {_plain(w) for w in words(text)}


def _head(piece: store.Piece) -> str:
    """The part of a page that says what it is for: its title and its "when"."""
    return piece.title + " " + piece.when


# The harness's own messages are not the person's requests: a subagent's report loaded an unrelated page (2026-10-31).
NOT_A_REQUEST = re.compile(r"^\s*<(task-notification|system-reminder|agent-message)[\s>]")


def enabled(cwd: str | None = None, prompt: str = "") -> list[store.Piece]:
    return control.filter_pieces(store.all_pieces(), cwd, prompt)


def project_note(project: str, pieces: list[store.Piece]) -> str:
    """What a project's know-how is about, in one line: the person's own words in `<home>/projects/<name>.md` when
    they wrote some, else its most used pages."""
    f = paths.home() / "projects" / f"{project}.md"
    try:
        own = next((l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")), "")
    except OSError:
        own = ""
    if own:
        return own
    top = sorted(pieces, key=lambda p: p.last_used, reverse=True)[:3]
    return "e.g. " + "; ".join(f"«{p.title}»" for p in top)


def other_projects(here: list[store.Piece]) -> list[str]:
    """The global memory is an index: one line per other project, so the model knows that know-how exists without
    it mixing into this project's requests."""
    ids = {p.id for p in here}
    by: dict[str, list[store.Piece]] = {}
    for p in store.all_pieces():
        if p.id not in ids:
            for q in p.projects:
                by.setdefault(q, []).append(p)
    return [f"- {q} ({len(ps)} way{'s' if len(ps) > 1 else ''} of working): {project_note(q, ps)}"
            for q, ps in sorted(by.items(), key=lambda kv: -len(kv[1]))]


def _most_recent_first(pieces: list[store.Piece]) -> list[store.Piece]:
    return sorted(pieces, key=lambda piece: piece.last_used, reverse=True)


def _catalogue(pieces: list[store.Piece], budget: int, cmd: str) -> list[str]:
    """One line per page, most recently used first, until `budget` characters are spent; then a single line says
    how many were left out and where to see them."""
    entries: list[str] = []
    for piece in _most_recent_first(pieces):
        entry = f"- `{piece.id}` — {piece.title}. When: {piece.when}"
        cost = len(entry) + 1
        if cost > budget:
            entries.append(f"- … and {len(pieces) - len(entries)} more (`{cmd} list`)")
            break
        entries.append(entry)
        budget -= cost
    return entries


def index_text(pieces: list[store.Piece], cmd: str = "athos", others: list[str] | None = None) -> str:
    """The session-start text: the catalogue of loadable pages, then a short list of other projects' know-how.
    Empty when there is nothing to load, so the hook adds nothing."""
    return _index_body(pieces, cmd, others) if pieces else ""


def _index_body(pieces: list[store.Piece], cmd: str, others: list[str] | None) -> str:
    intro = "\n".join((
        "# Athos — your know-how",
        "",
        "These pieces of the user's own know-how are available. When a request matches a piece's \"when\", follow "
        "it; the matching piece is usually added to the request automatically, and "
        f"`{cmd} show <id>` prints any of them.",
        "",
    ))
    body = _catalogue(pieces, INDEX_CAP - len(intro), cmd)
    if others:
        body.append("\nOther projects' know-how (loaded only when a request names the project; "
                    f"`{cmd} list` shows it):")
        body += others[:12]
    return intro + "\n".join(body)


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
    return sorted(_base_words(prompt) & _base_words(_head(piece)))


def dismiss(piece_id: str, shared: list[str]) -> None:
    """The person said this load did not apply: the same words never load this piece again."""
    data = misfires()
    sets = data.setdefault(piece_id, [])
    if sorted(shared) not in sets:
        sets.append(sorted(shared))
    misfires_file().parent.mkdir(parents=True, exist_ok=True)
    misfires_file().write_text(json.dumps(data, indent=1, ensure_ascii=False))


def _dismissed(request_words: set[str], head_words: set[str], earlier: list[list[str]]) -> bool:
    """Whether the words this request shares with a page were all part of a load the person turned down before."""
    overlap = request_words & head_words
    return any(overlap <= set(turned_down) for turned_down in earlier)


def _by_score(scored: list[tuple[float, store.Piece]]) -> list[tuple[float, store.Piece]]:
    """Best first; ties broken by page id so the order never depends on the store's."""
    return sorted(scored, key=lambda pair: (-pair[0], pair[1].id))


class _Pool:
    """What the ranking needs to know about every candidate page, computed once per request."""

    def __init__(self, pieces: list[store.Piece]):
        self.pieces = pieces
        self.head_tokens = [set(tokens(_head(piece))) for piece in pieces]
        self.body_tokens = [set(tokens(piece.body)) for piece in pieces]
        self.head_words = [_base_words(_head(piece)) for piece in pieces]
        self.title_words = [_base_words(piece.title) for piece in pieces]

    def weight(self, token: str) -> float:
        """Rarer tokens weigh more: a smoothed inverse document frequency over heads and bodies."""
        holders = sum(1 for head, body in zip(self.head_tokens, self.body_tokens) if token in head or token in body)
        return math.log(1 + len(self.pieces) / (1 + holders)) + 1

    def titles_with(self, word: str) -> int:
        return sum(1 for title in self.title_words if word in title)

    def same_words_enough(self, request_words: set[str], i: int) -> bool:
        # Shared prefixes only add to the score ("checklist" starts like "check", "contrato" like "controls"): a
        # piece needs the very same words: two of them, or one of five letters or more that only its title has.
        same = request_words & self.head_words[i]
        if len(same) >= 2:
            return True
        return any(len(w) >= 5 and self.titles_with(w) <= ONE_WORD_DF for w in same & self.title_words[i])


def rank(prompt: str, pieces: list[store.Piece]) -> list[tuple[float, store.Piece]]:
    """Every page that clears the bar, scored and best first.

    A page earns the weight of each request token found in its title or "when", and a quarter of that for tokens
    found only in its body. It is kept when it shares at least one head token, scores MIN_SCORE or more, shares
    real words (not just prefixes) with the request, and the person has not turned the same match down before."""
    asked = set(tokens(prompt))
    if not asked or not pieces or NOT_A_REQUEST.match(prompt):
        return []
    pool = _Pool(pieces)
    request_words = _base_words(prompt)
    turned_down = misfires()
    kept: list[tuple[float, store.Piece]] = []
    for i, piece in enumerate(pieces):
        head, body = pool.head_tokens[i], pool.body_tokens[i]
        in_head = asked & head
        only_in_body = (asked & body) - head
        score = sum(pool.weight(t) for t in in_head) + 0.25 * sum(pool.weight(t) for t in only_in_body)
        if _dismissed(request_words, pool.head_words[i], turned_down.get(piece.id, [])):
            continue
        if in_head and score >= MIN_SCORE and pool.same_words_enough(request_words, i):
            kept.append((score, piece))
    return _by_score(kept)


def sure(ranked: list[tuple[float, store.Piece]]) -> bool:
    """The lexical ranking needs no second opinion: a clear first piece, well ahead of any other."""
    return bool(ranked) and ranked[0][0] >= SURE_SCORE and (len(ranked) == 1 or ranked[1][0] < RUNNER_UP * ranked[0][0])


def rerank(prompt: str, pieces: list[store.Piece], ranked: list[tuple[float, store.Piece]],
           closeness: dict[str, float]) -> list[tuple[float, store.Piece]]:
    """Words and meaning together: what the words found stays, and the piece closest in meaning joins when it stands
    clearly out (a Spanish request and an English piece share no word). `closeness` is each piece's cosine to the
    request minus its usual cosine to any request (load/embed.py), so a piece close to everything doesn't win."""
    if not closeness:
        return ranked
    pid, best = max(closeness.items(), key=lambda t: (t[1], t[0]))
    p = next((p for p in pieces if p.id == pid), None)
    if p is None or best < MEANING_MIN or any(q.id == pid for _, q in ranked):
        return ranked
    if _dismissed(_base_words(prompt), _base_words(_head(p)), misfires().get(pid, [])):  # [Didn't apply] holds here too
        return ranked
    score = ranked[0][0] * MEANING_WEIGHT if ranked else MIN_SCORE
    return _by_score(ranked + [(score, p)])


def _within_budget(ranked: list[tuple[float, store.Piece]]) -> tuple[list[store.Piece], int]:
    """From the top of the ranking: the best page always, whatever its size; a runner-up only when it scores close
    to the best and still fits INJECT_CAP. Returns the pages and the characters they take."""
    chosen: list[store.Piece] = []
    used = 0
    for score, piece in ranked[:TOP_K]:
        if chosen and score < RUNNER_UP * ranked[0][0]:
            break
        size = len(store.render(piece))
        if chosen and used + size > INJECT_CAP:
            break
        chosen.append(piece)
        used += size
    return chosen, used


def relevant(prompt: str, pieces: list[store.Piece], meaning=None) -> list[store.Piece]:
    """The pieces to load for this request. `meaning(prompt, pieces) -> {id: closeness} | None` is the optional second
    opinion (`athos embed on`); None follows the person's setting, False is words only."""
    ranked = rank(prompt, pieces)
    if meaning is None:
        from athos.load import embed
        meaning = embed.scores if embed.enabled() else False
    if meaning and not sure(ranked) and words(prompt) and not NOT_A_REQUEST.match(prompt):
        ranked = rerank(prompt, pieces, ranked, meaning(prompt, pieces) or {})
    chosen, used = _within_budget(ranked)
    return chosen + _handed_over(chosen, used)


def _handed_over(loaded: list[store.Piece], used: int) -> list[store.Piece]:
    """The pages a loaded piece's steps hand over to (**Calls:** / **If:**), while they fit the budget: the model
    needs them at the step that calls them, not after a search. Each one is taken at most once."""
    extra: list[store.Piece] = []
    for piece in loaded:
        targets = dict.fromkeys(call["page"] for statement in _wiki().statements(piece) for call in statement.calls)
        for target_id in targets:
            target = store.get(target_id)
            if not target or target in loaded or target in extra:
                continue
            size = len(store.render(target))
            if used + size <= INJECT_CAP:
                extra.append(target)
                used += size
    return extra


def handover(pieces: list[store.Piece], show: str) -> str:
    """How a step that hands over to another page is walked, said only when a loaded piece has one. `show` is how this
    agent reads a page that didn't come along (a command, or Claude Desktop's athos_show tool)."""
    if not any(s.calls for p in pieces for s in _wiki().statements(p)):
        return ""
    return (f"**Steps that hand over**: a step with `**Calls:** [[<page>]]` is done by following that page's "
            f"statements (included here or {show}), then you come back to the next step; with "
            f"`**If:** <condition> → [[<page>]]` only when the condition holds for this case, and if it "
            f"doesn't, skip it and say why in one short clause.")


def _page_section(piece: store.Piece) -> str:
    """A loaded page as the model reads it: heading with id and version, its "when", then the body."""
    heading = f"## {piece.title} (`{piece.id}`, v{piece.version})"
    return "\n".join((heading, f"When: {piece.when}", "", piece.body, ""))


def inject_text(pieces: list[store.Piece], cmd: str = "athos") -> str:
    """The text added to a request: the matching pages, then how to report steps, how to answer, and the first line.
    Nothing at all when no page matched."""
    if not pieces:
        return ""
    preface = ("# Athos — know-how that matches this request\n\nThe user's own know-how for this kind of task. "
               "Follow it unless the request says otherwise.\n")
    return "\n".join([preface, *map(_page_section, pieces), *_instructions(pieces, cmd)])


def _instructions(pieces: list[store.Piece], cmd: str) -> list[str]:
    """What the model is told after the pages: how hand-overs work (when there are any), how to report each step,
    how to answer, and what the first line of the reply says."""
    first = pieces[0].title
    parts: list[str] = []
    # The person watches the trail in Athos's pane (Claude Code) or `athos watch`: one call per step, not per action.
    # Muse Code wrote a whole plan in one reply and reported one step (2026-10-30): a statement whose work is only part
    # of the answer is still a step.
    # Composition: a step may hand over to another way of working, always or only in some cases (2026-10-30).
    if hand := handover(pieces, f"`{cmd} show <page>`"):
        parts.append(hand + "\n")
    parts.append(f"**As you go**, when you start one of these statements run `{cmd} step <piece-id>#<statement_id>` "
                 f"(once per statement, as its own command right before that statement's work, never chained with "
                 f"other steps: the person watches them tick one by one). This holds when the work is only thinking "
                 f"or writing part of your answer: run the step for each statement before writing that part, even if "
                 f"the whole answer is one reply. If the task needs a step none of them has, run "
                 f"`{cmd} step --new \"<the step, in a few words, in the person's language>\"`. Say nothing about it "
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
    return parts


def _wiki():
    from athos import wiki
    return wiki


def mark_loaded(session_id: str, ids: list[str]) -> None:
    """Note that these pages were used in this session, whether the prompt hook added them or the model opened one
    with `athos show`: the session state, the eval log and each page's last-used time all learn it."""
    if not ids:
        return
    already = session.load(session_id).get("loaded", [])
    session.update(session_id, loaded=sorted({*already, *ids}))
    ev.note_loaded(session_id, ids=list(ids))
    for piece_id in ids:
        store.touch(piece_id)


def _session_of(event: dict) -> str:
    return event.get("session_id", "default")


def on_prompt(event: dict, cmd: str = "athos") -> str:
    """UserPromptSubmit: the pieces that match the request, recorded as loaded in this session, with the words that
    loaded each one (the band shows them, and [Didn't apply] remembers them)."""
    prompt = event.get("prompt", "")
    sid = _session_of(event)
    found = relevant(prompt, enabled(event.get("cwd"), prompt))
    if found:
        session.update(sid, task_why={p.id: why(prompt, p) for p in found})
    mark_loaded(sid, [piece.id for piece in found])
    text = inject_text(found, cmd)
    conn = note_connectors(sid, found, cmd)
    text += "\n" + conn + "\n" if conn else ""
    if found:                                    # a cheaper model proven on this piece: the person hears it once
        from athos import replay
        offer = replay.offer_text([p.id for p in found], cmd)
        text += "\n" + offer + "\n" if offer else ""
    return text


def note_connectors(session_id: str, pieces: list[store.Piece], cmd: str = "athos") -> str:
    """The connectors the loaded pieces ask for ([[connector:<name>]]): checked now, kept for the panel, and told
    to the model."""
    from athos import connectors
    states = connectors.status(pieces)
    session.update(session_id, task_connectors=states)
    for s in states:
        ev.append({"type": "connector", "session_id": session_id, "name": s["name"], "active": s["active"],
                   "at": ev._iso(ev.now())})
    return connectors.model_text(states, cmd)


def _model_name(event: dict) -> str | None:
    """The model the agent reports at session start: a plain string, or an object with an id or a display name."""
    reported = event.get("model")
    if isinstance(reported, dict):
        reported = reported.get("id") or reported.get("display_name")
    return str(reported) if reported else None


def on_session_start(event: dict, cmd: str = "athos") -> str:
    """SessionStart: remember the model, then give the catalogue, the project's recent tasks, the capture guide and
    any cheaper-model offer, in that order."""
    sid = _session_of(event)
    model = _model_name(event)
    if model is not None:
        session.update(sid, model=model)
    from athos import capture
    here = enabled(event.get("cwd"))
    text = index_text(here, cmd, other_projects(here))
    # Short-term memory: the project's recent tasks, next to its ways of working (the long-term memory).
    if event.get("cwd"):
        from athos import journal
        recent = journal.text(paths.project_of(event["cwd"]))
        if recent:
            text = (text + "\n\n" if text else "") + recent
    if text and capture.enabled():               # with the guide given here, the Stop hook only needs one line
        text += "\n\n" + capture.guide(cmd)
        session.update(sid, guide=True)
    from athos import replay
    offer = replay.offer_text(None, cmd)        # a cheaper model proven on a piece: told once, at the session's start
    if offer:
        text = (text + "\n\n" if text else "") + offer
    return text
