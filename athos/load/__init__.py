"""The router: deciding which of the person's ways of working reach the model, and when.

Two moments matter. When a session opens, the model gets a compact catalogue of the pages it may use (id, title and
the "when" line), never their bodies. When the person sends a request, the page or two that fit it best are added in
full, within a size budget. The store as a whole is never pasted in.
"""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata

from athos import control, eval as ev, paths, session, store

# Size budgets, in characters.
INDEX_CAP = 4000         # the session-start catalogue
INJECT_CAP = 8000        # everything added to one request; a page that does not fit is cut, and the cut is recorded
# Pull instead of push: a frontier model gets a short index of the pieces in reach and opens the one it needs.
PULL_LINES = 6           # at most this many pieces in the index
PULL_WHEN = 160          # each one's "when", cut at a word to about this many characters
PULL_CAP = 1200          # the whole index, header included

# Lexical ranking.
TOP_K = 2                # at most this many pages are picked by score
RUNNER_UP = 0.5      # a second piece loads only with at least half the best piece's score (one shared word is noise)
MIN_SCORE = 1.2          # below this a page is not worth adding
STEM = 5                 # tokens are cut to this length, so "release", "releases" and "releasing" all meet
ONE_WORD_DF = 1        # one shared word is enough only if no other piece's title has it
# The margin (set with `athos bench route`, the per-project from-store run and a private replay of one session whose
# requests all needed nothing): a score alone grows with the request's length, so a long pasted text shares words with
# almost any page. A page also needs this share of its head's words (title and "when") in the request...
HEAD_SHARE_MIN = 0.05
# ...and its head's words must be this share of the request's own words, so a request cannot win on volume.
REQUEST_SHARE_MIN = 0.07
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

# The wrappers the harness puts around text it sends as a prompt. A prompt that opens with one, or carries one early
# on (a subagent's report that begins with a system reminder), is not the person's: it loads nothing, and the special
# paths (save, adjust, gallery, share) never act on it.
HARNESS_TAGS = {"task-notification", "system-reminder", "agent-message", "teammate-message", "local-command-stdout",
                "local-command-stderr", "local-command-caveat", "command-name", "command-message", "command-args",
                "user-prompt-submit-hook", "bash-input", "bash-stdout", "bash-stderr"}
_LEADING_TAG = re.compile(r"^\s*</?([A-Za-z][\w:-]*)[\s>/]")      # a closing tag too: the tail of a cut wrapper
_HARNESS_INSIDE = re.compile(r"</?(" + "|".join(sorted(map(re.escape, HARNESS_TAGS))) + r")[\s>/]", re.I)
_HARNESS_WHOLE = re.compile(r"<(" + "|".join(sorted(map(re.escape, HARNESS_TAGS))) + r")[\s>][\s\S]*?</\1\s*>", re.I)


def origin_of(text: str, opens_with_trigger: bool = False) -> tuple[bool | None, str | None]:
    """Whether a prompt reads as the person's own text: (True, None) for plain text; (False, tag) when it opens with,
    or carries anywhere, a wrapper the harness uses (in any case: a long plain report with a wrapper after its first
    400 characters once read as the person's); (None, tag) when it opens with some other tag (pasted markup, or a
    wrapper not known yet). `opens_with_trigger`: the text opens with a special path's own words ("Athos · save:"),
    so a wrapper tag it merely mentions does not make it the harness's; a whole wrapped element still does. A heuristic
    for the audit: the hook is not told who wrote the prompt."""
    lead = _LEADING_TAG.match(text or "")
    tag = lead.group(1).lower() if lead else None
    if tag in HARNESS_TAGS:
        return False, tag
    if opens_with_trigger and tag is None:
        # Opening with the path's own words: the person's, unless a whole wrapper (an opening tag and its closing
        # one) came with it; a tag the person merely mentions ("when you see <system-reminder>") is not one.
        whole = _HARNESS_WHOLE.search(text or "")
        return (False, whole.group(1).lower()) if whole else (True, None)
    inside = _HARNESS_INSIDE.search(text or "")
    if inside:
        return False, inside.group(1).lower()
    return (None, tag) if tag else (True, None)


def from_person(text: str) -> bool:
    """The special paths (save, adjust, gallery, share) act only on text that reads plainly as the person's."""
    return origin_of(text)[0] is True


ORIGIN_CHECKS = ("verify", "strict", "heuristic")


def origin_check() -> str:
    """How a special path decides while the transcript has no entry for the prompt yet (config `origin_check`):
    `verify` (the default) acts on the text and checks the transcript at the next tool or stop hook, undoing what it
    can if the harness wrote it; `strict` does not act; `heuristic` acts on the text and never looks again."""
    from athos import start
    chosen = start.config().get("origin_check")
    return chosen if chosen in ORIGIN_CHECKS else "verify"


def trigger_origin(event: dict, which: str | None = None) -> dict:
    """Whether a special path (save, adjust, gallery, share) may act on a prompt, from two signals: the wrappers the
    text carries (`origin_of`) and, when the hook gives a transcript path, the transcript's entry for the prompt
    (`session.prompt_origin`). When both are there they must agree. Claude Code writes that entry only after the prompt
    hook has run, so it is usually missing at prompt time: then `origin_check` decides (`verify`: act on the text and
    check later; `strict`: hold back; `heuristic`: the text alone). `signal` says which way it went: `heuristic` (no
    transcript path: Codex, Muse Code, OpenCode), `both`, `disagree`, `missing:verify`, `missing` (strict) or
    `missing:heuristic`."""
    prompt = event.get("prompt", "") or ""
    from athos import capture
    prefixed = (which == "save" and capture.is_save_prompt(prompt)) or \
        (which == "adjust" and capture.is_adjust_prompt(prompt))
    person, wrapper = origin_of(prompt, opens_with_trigger=prefixed)
    out = {"from_person": person, "wrapper": wrapper, "transcript": None, "signal": "heuristic"}
    path = event.get("transcript_path")
    if not path:
        return out
    seen = session.prompt_origin(path, event.get("prompt_id"))     # a fingerprint only when verifying, later
    out["transcript"] = seen
    if seen is None:
        mode = origin_check()
        if mode == "strict":
            out.update(signal="missing", from_person=None if person else person)
        else:
            out["signal"] = f"missing:{mode}"
        return out
    if (seen == "person") == (person is True):
        out["signal"] = "both"
    else:
        out.update(signal="disagree", from_person=False if person else person)
    return out


def not_a_request(text: str) -> bool:
    """The router loads nothing for text the harness wrote (a notification, a subagent's report)."""
    return bool(NOT_A_REQUEST.match(text or "")) or origin_of(text)[0] is False


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
    top = sorted(pieces, key=store.last_used, reverse=True)[:3]
    return "e.g. " + "; ".join(f"«{p.title}»" for p in top)


def other_projects(here: list[store.Piece], public: bool = False) -> list[str]:
    """What the session may know of the rest of the store: how many pieces other projects hold, and in how many
    projects, never their titles or names (another project's name or a private piece's title once reached a public
    repository's session). Empty when there is nothing else. In a public repository they never load, and it says so."""
    ids = {p.id for p in here}
    others = [p for p in store.all_pieces() if p.id not in ids and p.projects]
    projects = {q for p in others for q in p.projects}
    if not others:
        return []
    line = (f"- {len(others)} way{'s' if len(others) != 1 else ''} of working in {len(projects)} other "
            f"project{'s' if len(projects) != 1 else ''}")
    return [line + (" (never loaded here: this repository is marked public)" if public else "")]


def _most_recent_first(pieces: list[store.Piece]) -> list[store.Piece]:
    return sorted(pieces, key=store.last_used, reverse=True)


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
        public = any("marked public" in o for o in others)
        body.append("\nOther projects' know-how" + (":" if public else " (loaded only when a request names the project):"))
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
    return _rank_traced(prompt, pieces)[0]


def _rank_traced(prompt: str, pieces: list[store.Piece]) -> tuple[list[tuple[float, store.Piece]], list[dict]]:
    """`rank`, plus every piece that scored at all, with why it was kept or not (for the `route` audit event). The
    shared words are counted, never listed: they are the request's own words."""
    asked = set(tokens(prompt))
    if not asked or not pieces or not_a_request(prompt):
        return [], []
    pool = _Pool(pieces)
    request_words = _base_words(prompt)
    turned_down = misfires()
    kept: list[tuple[float, store.Piece]] = []
    seen: list[dict] = []
    for i, piece in enumerate(pieces):
        head, body = pool.head_tokens[i], pool.body_tokens[i]
        in_head = asked & head
        only_in_body = (asked & body) - head
        score = sum(pool.weight(t) for t in in_head) + 0.25 * sum(pool.weight(t) for t in only_in_body)
        score *= _confidence_factor(piece)      # 1 for every piece without a confidence (all legacy pieces)
        shared = len(request_words & pool.head_words[i])
        head_share = shared / max(1, len(pool.head_words[i]))
        request_share = shared / max(1, len(request_words))
        if _dismissed(request_words, pool.head_words[i], turned_down.get(piece.id, [])):
            reason = "dismissed"
        elif not in_head:
            reason = "no_head_match"
        elif score < MIN_SCORE:
            reason = "below_min_score"
        elif not pool.same_words_enough(request_words, i):
            reason = "prefixes_only"
        elif head_share < HEAD_SHARE_MIN:
            reason = "head_share_low"
        elif request_share < REQUEST_SHARE_MIN:
            reason = "request_share_low"
        else:
            reason = "ranked"
            kept.append((score, piece))
        if score > 0:
            seen.append({"piece": piece.id, "score": round(score, 2), "shared": shared,
                         "head_share": round(head_share, 3), "request_share": round(request_share, 3),
                         "projects": list(piece.projects), "kept": False, "reason": reason})
    return _by_score(kept), seen


def _confidence_factor(piece: store.Piece) -> float:
    from athos import grade
    return grade.router_factor(piece)


def usable(pieces: list[store.Piece], tier: str, project: str | None = None) -> list[store.Piece]:
    """What a model of this tier may be given (autonomous learning, athos/grade.py): never a retired piece; to an apply
    model (or one of unknown tier) only verified and legacy pieces, plus its project's candidates when
    `autolearn.apply_candidates` is on. A frontier model may be offered candidates: its clean reuses verify them."""
    from athos import autolearn, tiers
    out = [p for p in pieces if store.status(p) != "retired"]
    if tier == tiers.FRONTIER:
        return out
    allow = bool(autolearn.settings().get("apply_candidates"))
    return [p for p in out if store.usable_as_verified(p)
            or (allow and p.status == "candidate" and project and project in p.projects)]


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
    return decide(prompt, pieces, meaning)[0]


CANDIDATES = 5          # the route event keeps this many candidates


def thresholds() -> dict:
    """The numbers the router decided with, as the route event records them."""
    return {"min_score": MIN_SCORE, "head_share_min": HEAD_SHARE_MIN, "request_share_min": REQUEST_SHARE_MIN,
            "runner_up": RUNNER_UP, "top_k": TOP_K, "one_word_df": ONE_WORD_DF, "stem": STEM, "inject_cap": INJECT_CAP}


def decide(prompt: str, pieces: list[store.Piece], meaning=None) -> tuple[list[store.Piece], dict]:
    """`relevant`, plus how it got there: the best candidates (each with its score, the number of words it shares
    with the request, its projects, whether it loaded and why), what was chosen, what came along through a hand-over,
    and whether meaning was asked."""
    ranked, seen = _rank_traced(prompt, pieces)
    if meaning is None:
        from athos.load import embed
        meaning = embed.scores if embed.enabled() else False
    asked_meaning = bool(meaning and not sure(ranked) and words(prompt) and not not_a_request(prompt))
    if asked_meaning:
        before = {p.id for _, p in ranked}
        ranked = rerank(prompt, pieces, ranked, meaning(prompt, pieces) or {})
        for score, p in ranked:
            if p.id not in before:
                seen = [c for c in seen if c["piece"] != p.id]
                seen.append({"piece": p.id, "score": round(score, 2), "shared": 0, "projects": list(p.projects),
                             "kept": False, "reason": "meaning"})
    chosen, used = _within_budget(ranked)
    extra = _handed_over(chosen, used, pieces)
    _budget_reasons(ranked, chosen, seen)
    picked = {p.id for p in chosen}
    top = [c for c in seen if c["piece"] in picked] + sorted(
        (c for c in seen if c["piece"] not in picked), key=lambda c: (-c["score"], c["piece"]))
    trace = {"candidates": top[:max(CANDIDATES, len(picked))], "scored": len(seen),
             "chosen": [p.id for p in chosen], "handed_over": [p.id for p in extra], "meaning": asked_meaning}
    return chosen + extra, trace


def _budget_reasons(ranked: list[tuple[float, store.Piece]], chosen: list[store.Piece], seen: list[dict]) -> None:
    """Why each ranked piece did or didn't make it past `_within_budget`, written into its candidate entry."""
    picked = {p.id for p in chosen}
    best = ranked[0][0] if ranked else 0.0
    why: dict[str, str] = {}
    for pos, (score, p) in enumerate(ranked):
        if p.id in picked:
            why[p.id] = "chosen"
        elif pos >= TOP_K:
            why[p.id] = "beyond_top_k"
        elif score < RUNNER_UP * best:
            why[p.id] = "runner_up_too_weak"
        else:
            why[p.id] = "over_budget"
    for c in seen:
        if c["piece"] in why:
            c["reason"] = why[c["piece"]]
            c["kept"] = c["piece"] in picked


def _handed_over(loaded: list[store.Piece], used: int, pool: list[store.Piece]) -> list[store.Piece]:
    """The pages a loaded piece's steps hand over to (**Calls:** / **If:**), while they fit the budget: the model
    needs them at the step that calls them, not after a search. Each one is taken at most once, and only from `pool`,
    the pieces this session may be given: a hand-over once brought any page of the store, another project's private
    one included, past the scope, the public marker and what the model's tier may use."""
    extra: list[store.Piece] = []
    reach = {p.id: p for p in pool}
    for piece in loaded:
        targets = dict.fromkeys(call["page"] for statement in _wiki().statements(piece) for call in statement.calls)
        for target_id in targets:
            target = reach.get(target_id)
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


def _page_section(piece: store.Piece, apply: bool = False) -> str:
    """A loaded page as the model reads it: heading with id and version, its "when", then the body. To an apply model
    a learned page (candidate or verified) comes as a short checklist with its Check lines (`_checklist`), and any
    page's risky steps carry an instruction to ask the person first (`_ask_first`)."""
    heading = f"## {piece.title} (`{piece.id}`, v{piece.version})"
    if apply and piece.status in ("candidate", "verified") and _wiki().is_wiki(piece):
        return _checklist(piece)
    return "\n".join((heading, f"When: {piece.when}", "", _ask_first(piece) if apply else piece.body, ""))


RISK_WORDS = {"publish": "publishes", "merge": "merges", "deploy": "deploys", "delete": "deletes",
              "force_push": "force-pushes", "production": "touches production"}
ASK_FIRST = "**Ask first:** this step {what}: ask the person and do it only on their clear yes."
CHECKLIST_HEAD = ("Steps, in order. After each one, run its Check and go on only when it holds; if a Check fails, stop "
                  "and say which one failed.")


def _risk_words(kinds: list[str]) -> str:
    words = [RISK_WORDS.get(k, k) for k in kinds]
    return ", ".join(words[:-1]) + (" and " if len(words) > 1 else "") + words[-1]


def _ask_first(piece: store.Piece) -> str:
    """The page's body with an Ask-first line after the Do of each risky step (athos/autolearn.py: publishes, merges,
    deploys, deletes, force-pushes or touches production); a page without statements gets one line on top."""
    from athos import autolearn
    risky = autolearn.risky_steps(piece)
    if not risky:
        return piece.body
    if not _wiki().is_wiki(piece):
        return ASK_FIRST.format(what=_risk_words(risky["steps"])).replace("this step", "some of these steps") + \
            "\n\n" + piece.body
    out, current = [], None
    for line in piece.body.splitlines():
        head = re.match(r"^## #([a-z0-9][a-z0-9_-]*)\s*$", line)
        if head:
            current = head.group(1)
        out.append(line)
        if current in risky and line.startswith("**Do:**"):
            out.append(ASK_FIRST.format(what=_risk_words(risky[current])))
    return "\n".join(out)


def _checklist(piece: store.Piece) -> str:
    """A learned page for an apply model: each step's When and Do, its Check, its hand-overs and, for a risky step, the
    instruction to ask first; without the reasons, links or history."""
    from athos import autolearn
    risky = autolearn.risky_steps(piece)
    lines = [f"## {piece.title} (`{piece.id}`, v{piece.version})", f"When: {piece.when}", "", CHECKLIST_HEAD]
    for n, st in enumerate(_wiki().statements(piece), 1):
        lines.append(f"{n}. #{st.id} — " + " · ".join(f"{k}: {v}" for k, v in (("When", st.when), ("Do", st.do)) if v))
        if st.check:
            lines.append(f"   Check: {st.check}")
        raw = _raw_statement(piece, st.id)
        lines += ["   " + ln for ln in raw.splitlines() if ln.startswith(("**Calls:**", "**If:**"))]
        if st.id in risky:
            lines.append("   " + ASK_FIRST.format(what=_risk_words(risky[st.id])))
    return "\n".join(lines) + "\n"


PREFACE = ("# Athos — know-how that matches this request\n\nThe user's own know-how for this kind of task. "
           "Follow it unless the request says otherwise.\n")
CUT_NOTE = "\n… (cut to fit; `{cmd} show {id}` prints the whole page)\n"
STEPS_NOTE = ("\n… (only each step's When, Do and Check, to fit: `{cmd} show {id}` prints the whole page, with the reasons, "
              "links and history)\n")
STEPS_CUT_NOTE = ("\n… (only each step's When, Do and Check, to fit, and {n} more step(s) left out: {ids}. `{cmd} show {id}` "
                  "prints the whole page)\n")


def inject_text(pieces: list[store.Piece], cmd: str = "athos", cap: int | None = None) -> str:
    """The text added to a request: the matching pages, then how hand-overs work and how to answer. Nothing at all
    when no page matched. Never longer than `cap` (INJECT_CAP by default): see `fit`."""
    return fit(pieces, cmd, cap)[0]


def fit(pieces: list[store.Piece], cmd: str = "athos", cap: int | None = None) -> tuple[str, list[str], list[str]]:
    """`inject_text`, plus the pages cut to fit and the pages left out for lack of room. The notes come first in the
    budget; then each page whole while it fits. The first that doesn't is given as its steps (`_steps_section`):
    each statement's When and Do, and its hand-overs, without the reasons and links, which are what a step is
    followed by; whole when that fits, else as many whole steps as fit, naming the ones left out. A page without
    statements is cut at a line. Either way a note says how to read the rest, and any page after it is left out. A
    26 KB page once came whole with every request (2026-11-14); cut at a line, a long page lost its last steps
    whole (2026-11-15). The pages given only as steps are in `fit_steps`."""
    return _fit(pieces, cmd, cap)[:3]


def fit_steps(pieces: list[store.Piece], cmd: str = "athos", cap: int | None = None) -> list[str]:
    """The pages `fit` gave as their steps only (When and Do), because whole they did not fit."""
    return _fit(pieces, cmd, cap)[3]


def _fit(pieces: list[store.Piece], cmd: str = "athos", cap: int | None = None,
         apply: bool = False) -> tuple[str, list[str], list[str], list[str]]:
    if not pieces:
        return "", [], [], []
    cap = INJECT_CAP if cap is None else cap
    notes = _instructions(pieces, cmd)
    room = cap - len(PREFACE) - sum(len(n) + 1 for n in notes) - 1
    sections: list[str] = []
    cut: list[str] = []
    left: list[str] = []
    steps: list[str] = []
    for piece in pieces:
        section = _page_section(piece, apply)
        if cut or left or steps or room <= 0:
            left.append(piece.id)
            continue
        if len(section) + 1 <= room:
            sections.append(section)
            room -= len(section) + 1
            continue
        short, whole = _steps_section(piece, room - 1, cmd, apply)
        if short:
            sections.append(short)
            (steps if whole else cut).append(piece.id)
            room = 0                              # a page after it is left out, as after a cut
            continue
        note = CUT_NOTE.format(cmd=cmd, id=piece.id)
        keep = section[:max(0, room - len(note) - 1)]
        keep = keep[:keep.rfind("\n")] if "\n" in keep else ""
        if not keep.strip():
            left.append(piece.id)
            continue
        sections.append(keep + note)
        cut.append(piece.id)
        room = 0
    if not sections:
        return "", cut, left, steps
    return "\n".join([PREFACE, *sections, *notes]), cut, left, steps


def _steps_section(piece: store.Piece, room: int, cmd: str, apply: bool = False) -> tuple[str, bool]:
    """A page as its steps only, within `room` characters: the heading and "when", then each statement's id, When,
    Do, Check and hand-overs (Calls, If), without Because, Links or the page's history. Returns the text ("" for a page
    without statements, or when not even one step fits) and whether every step fit."""
    wiki = _wiki()
    if not wiki.is_wiki(piece):
        return "", False
    head = "\n".join((f"## {piece.title} (`{piece.id}`, v{piece.version})", f"When: {piece.when}", ""))
    from athos import autolearn
    risky = autolearn.risky_steps(piece) if apply else {}
    blocks = []
    for st in wiki.statements(piece):
        lines = [f"### #{st.id}"]
        lines += [f"**{k}:** {v}" for k, v in (("When", st.when), ("Do", st.do)) if v]
        raw = _raw_statement(piece, st.id)
        # A step's Check stays with it: it is how an apply model knows the step went right without judging it.
        lines += [ln for ln in raw.splitlines() if ln.startswith(("**Check:**", "**Calls:**", "**If:**"))]
        if apply and st.id in risky:
            lines.append(ASK_FIRST.format(what=_risk_words(risky[st.id])))
        blocks.append((st.id, "\n".join(lines) + "\n"))
    whole_note = STEPS_NOTE.format(cmd=cmd, id=piece.id)
    text = head + "\n".join(b for _, b in blocks)
    if len(text) + len(whole_note) <= room:
        return text + whole_note, True
    kept, used = [], len(head)
    for n, (_sid, block) in enumerate(blocks):
        # Keeping this step leaves the ones after it out: that is the note to make room for (the note naming this
        # step too was measured instead, and a page could pass the cap by a few dozen characters).
        rest = [i for i, _ in blocks[n + 1:]]
        if not rest:
            break                                 # every step whole did not fit with its note (checked above)
        note = STEPS_CUT_NOTE.format(cmd=cmd, id=piece.id, n=len(rest), ids=_ids_line(rest))
        if used + len(block) + 1 + len(note) > room:
            break
        kept.append(block)
        used += len(block) + 1
    if not kept:
        return "", False
    rest = [i for i, _ in blocks[len(kept):]]
    note = STEPS_CUT_NOTE.format(cmd=cmd, id=piece.id, n=len(rest), ids=_ids_line(rest))
    return head + "\n".join(kept) + note, False


def _ids_line(ids: list[str], limit: int = 8) -> str:
    shown = ", ".join(f"#{i}" for i in ids[:limit])
    return shown + (f" and {len(ids) - limit} more" if len(ids) > limit else "")


def _raw_statement(piece: store.Piece, sid: str) -> str:
    """The text of one statement of a page, as written."""
    m = re.search(rf"^## #{re.escape(sid)}\s*$(.*?)(?=^## #|\Z)", piece.body, re.M | re.S)
    return m.group(1) if m else ""


def _instructions(pieces: list[store.Piece], cmd: str) -> list[str]:
    """What the model is told after the pages: how hand-overs work (when there are any) and how to answer. Nothing
    asks it for visible work: no opening line naming the page, no step commands (a private page's title ended up
    written in replies, and the step reports cost turns no panel used, 2026-11-14)."""
    parts: list[str] = []
    # Composition: a step may hand over to another way of working, always or only in some cases (2026-10-30).
    if hand := handover(pieces, f"`{cmd} show <page>`"):
        parts.append(hand + "\n")
    # The person may be a lawyer or a coach, not the author of the piece's notes (2026-10-30, Claude Desktop: answers
    # narrated tools, cited "piece v7" and pasted the piece's commands until told otherwise).
    parts.append("**How to answer**: plainly, in the person's language, as a colleague who already knows how they work: "
                 "do the task or answer the question directly. Don't narrate tools or say you are reading something; "
                 "don't mention Athos, pieces, ids, versions, or the dates, measurements and notes the piece keeps for "
                 "you; give commands, paths or settings only when the person must act on them. Take from the piece "
                 "only what this request needs, and if it doesn't fit this request, leave it aside without saying "
                 "so.\n")
    return parts


def _wiki():
    from athos import wiki
    return wiki


def mark_loaded(session_id: str, ids: list[str]) -> None:
    """Note that these pages were used in this session, whether the prompt hook added them or the tool hook saw the
    model open one with `athos show`: the session state, the eval log and each page's last-used time all learn it.
    `athos show` itself writes nothing unless asked (`--use`)."""
    if not ids:
        return
    already = session.load(session_id).get("loaded", [])
    session.update(session_id, loaded=sorted({*already, *ids}))
    ev.note_loaded(session_id, ids=list(ids))
    for piece_id in ids:
        store.touch(piece_id)


def note_opened(session_id: str, piece: store.Piece, via: str, cwd: str | None = None) -> None:
    """The model opened a piece itself (the tool hook saw `athos show <id>`): it is used for the open task, credited
    after the routed ones for an edit, and written down as a `piece_opened` event, with whether the frontier index of
    this request offered it."""
    state = session.load(session_id)
    offered = piece.id in (state.get("task_offered") or [])
    already = piece.id in (state.get("task_loaded") or [])
    mark_loaded(session_id, [piece.id])
    route = list(state.get("task_route") or [])
    opened = list(state.get("task_opened") or [])
    session.update(session_id, task_route=route + ([piece.id] if piece.id not in route else []),
                   task_opened=opened + ([piece.id] if piece.id not in opened else []))
    project = state.get("project") or (paths.project_of(cwd) if cwd else None)
    public = bool(state.get("public"))
    tags = [q for q in piece.projects if q == project] if public else list(piece.projects)   # no other name there
    ev.audit({"type": "piece_opened", "session_id": session_id, "task_id": state.get("task_id"), "piece": piece.id,
              "projects": tags, "via": via, "offered": offered, "again": already, "project": project},
             line=f"opened {loggable([piece], project, public)} ({via})" + (" · offered in the index" if offered else ""),
             project=project)


def _session_of(event: dict) -> str:
    return event.get("session_id", "default")


_PENDING: dict[str, tuple] = {}     # a route event held until the prompt hook knows everything it hands the model


def on_prompt(event: dict, cmd: str = "athos", defer: bool = False) -> str:
    """UserPromptSubmit: what the router found for the request, delivered the way the model answering it takes it
    best (`deliver`): an apply model gets the pieces (recorded as loaded, with the words that loaded each one, which
    the band shows and [Didn't apply] remembers); a frontier model gets a short index of the pieces in reach, and a
    piece counts as used only once the model opens it (`note_opened`). The `route` event is written at once, or, with
    `defer`, when the caller has added its own text and calls `finish_route` with the total."""
    from athos import tiers
    prompt = event.get("prompt", "")
    sid = _session_of(event)
    started = time.perf_counter()
    everything = store.all_pieces()
    tier = tiers.tier_of(session.load(sid).get("model"))     # the model resolved for this request (eval.task_start)
    pool, scope = control.select(everything, event.get("cwd"), prompt)
    pool = usable(pool, tier, scope.get("project"))          # an apply model: verified and legacy pieces only
    found, trace = decide(prompt, pool)
    scope, offer = settle_ambiguous(scope, everything, tier, cmd)
    ms = (time.perf_counter() - started) * 1000
    notes = index_notes(found, trace, pool, sid, event.get("cwd"), cmd) if tier == tiers.FRONTIER and found else None
    d = deliver(found, trace, pool, tier, cmd, notes=notes, offer=offer)
    extra = ""
    parts: dict[str, int] = {}
    if d["delivery"] == "piece":
        conn = note_connectors(sid, found, cmd)
        extra += "\n" + conn + "\n" if conn else ""
        parts["connectors"] = len(conn or "")
        from athos import indicator, replay      # a cheaper model proven on this piece: the person hears it once
        offer = "" if indicator.minimal() else replay.offer_text([p.id for p in found], cmd)
        extra += "\n" + offer + "\n" if offer else ""
        parts["offer"] = len(offer or "")
        if extra:
            d = deliver(found, trace, pool, tier, cmd, INJECT_CAP - len(extra), notes=notes, offer=offer)
    body, cut, left = d["text"], d["cut"], d["left_out"]
    shown = [p for p in found if p.id not in left] if d["delivery"] == "piece" else []
    if shown:
        # In a public repository nothing taken from a request is kept, not even the words that loaded a page.
        session.update(sid, task_why={p.id: [] if scope.get("public") else why(prompt, p) for p in shown})
        session.update(sid, task_route=[p.id for p in shown])     # best first: the edit detector credits the first
    if d["delivery"]:
        session.update(sid, task_delivery=d["delivery"], task_offered=d["offered"])
    mark_loaded(sid, [piece.id for piece in shown])
    text = body + extra if body else ""
    parts = {("index" if d["delivery"] == "index" else "pieces"): len(body),
             **{k: v for k, v in parts.items() if v and body}}
    trace = {**trace, "cut": cut, "left_out": left, "steps_only": d["steps_only"],
             "injected_parts": {k: v for k, v in parts.items() if v},
             "delivery": d["delivery"], "offered": d["offered"], "piece_chars": d["piece_chars"],
             "index_chars": d["index_chars"]}
    args = (sid, prompt, scope, trace, shown if d["delivery"] != "index" else [], len(everything), len(pool),
            len(text), ms)
    if defer:
        _PENDING[sid] = args
    else:
        _write_route(args, len(text), {})
    return text


def settle_ambiguous(scope: dict, everything: list[store.Piece], tier: str,
                     cmd: str = "athos") -> tuple[dict, str]:
    """An ambiguous mention of another project (its name is a common word and the request gave no cue, see
    control.decide_named) brings none of its pieces into scope. On a frontier model, outside a public repository, it
    becomes one index line saying the request may mean that project and how many pieces it has, so the model decides
    (`offered`); otherwise it is `rejected`. Returns the scope with `named_how` settled and `offered_projects`, and
    the line ("" when nothing is offered)."""
    from athos import tiers
    how = dict(scope.get("named_how") or {})
    here, public = scope.get("project"), bool(scope.get("public"))
    offered: list[tuple[str, int]] = []
    for q in scope.get("ambiguous") or []:
        n = sum(1 for p in everything if q in p.projects and control.may_see(p, here, public)
                and store.status(p) != "retired")
        if tier == tiers.FRONTIER and not public and n:
            offered.append((q, n))
            how[q] = "offered"
        else:
            how[q] = "rejected"
    out = {**scope, "offered_projects": [q for q, _n in offered]}
    if "named_how" in scope:
        out["named_how"] = how
    if not offered:
        return out, ""
    names = " or ".join(f"`{q}` ({n} way{'s' if n != 1 else ''} of working)" for q, n in offered)
    first = offered[0][0]
    return out, (f"- The request may also mean the project {names}, not loaded since its name is a common word; if "
                 f"it does, `{cmd} list --project {first}` lists them and `{cmd} show <id>` reads one.")


def deliver(found: list[store.Piece], trace: dict, pool: list[store.Piece], tier: str, cmd: str = "athos",
            cap: int | None = None, notes: dict[str, str] | None = None, offer: str = "") -> dict:
    """How the router's choice reaches the model. Nothing when nothing was chosen. To an apply model (and any model of
    unknown tier) the pieces themselves (`fit`): it follows better than it picks. To a frontier model an index of the
    pieces in reach (`pull_index`): it picks well, and opens the one it needs with `athos show`, so a wrong choice of
    the router costs a few lines instead of a page (a page of up to 26 KB came with every request, 2026-11-14). Both
    sizes are measured either way (`piece_chars`, `index_chars`) for the route event and the bench. `offer`: the one
    line about another project the request may mean (`settle_ambiguous`), added to a frontier model's index, and its
    whole index when nothing was chosen."""
    from athos import tiers
    if not found:
        if offer and tier == tiers.FRONTIER:
            text = PULL_HEAD.format(cmd=cmd) + offer + "\n"
            return {"delivery": "index", "text": text, "cut": [], "left_out": [], "steps_only": [], "offered": [],
                    "piece_chars": 0, "index_chars": len(text)}
        return {"delivery": None, "text": "", "cut": [], "left_out": [], "steps_only": [], "offered": [],
                "piece_chars": 0, "index_chars": 0}
    body, cut, left, steps = _fit(found, cmd, cap, apply=tier != tiers.FRONTIER)
    room = len(offer) + 1 if offer and tier == tiers.FRONTIER else 0
    index, offered = pull_index(found, trace, pool, cmd, notes=notes, cap=PULL_CAP - room)
    if room and index:
        index += offer + "\n"
    if tier == tiers.FRONTIER:
        return {"delivery": "index", "text": index, "cut": [], "left_out": [], "steps_only": [], "offered": offered,
                "piece_chars": len(body), "index_chars": len(index)}
    return {"delivery": "piece", "text": body, "cut": cut, "left_out": left, "steps_only": steps, "offered": [],
            "piece_chars": len(body), "index_chars": len(index)}


def index_notes(found: list[store.Piece], trace: dict, pool: list[store.Piece], sid: str, cwd: str | None,
                cmd: str = "athos") -> dict[str, str]:
    """A few words after a piece in a frontier model's index: a candidate not verified yet, or one of this project the
    verifier rejected (to open and improve), a piece that failed on an apply model and needs review, one set aside for
    the person, or one whose files or commands are no longer found here (`grade.reverify`)."""
    from athos import grade
    _text, offered = pull_index(found, trace, pool, cmd)
    byid = {p.id: p for p in [*pool, *found]}
    project = (session.load(sid).get("project") if sid else None) or (paths.project_of(cwd) if cwd else None)
    review = grade.reviews()
    out = {}
    for pid in offered:
        p = byid.get(pid)
        if p is None:
            continue
        words = []
        rejected = grade.rejection(p) if p.status == "candidate" and project and project in p.projects else None
        if rejected and not rejected["set_aside"]:
            # One short marker; the verifier's reasons come with `athos show`, in this project only.
            words.append(f"candidate, not accepted by the verifier: open it with `{cmd} show {pid}` and improve it "
                         f"if this task shows how")
        elif p.status == "candidate":
            words.append("candidate, not verified yet")
        if (review.get(pid) or {}).get("kind") == "set_aside":
            words.append("set aside for the person: don't rewrite it")
        elif pid in review:
            words.append("needs review: it failed on an apply model")
        stale = grade.reverify_cached(p, sid, cwd)
        if stale:
            words.append(f"may be stale: {stale}")
        if words:
            out[pid] = "; ".join(words)
    return out


PULL_HEAD = ("# Athos — know-how that may fit this request\n\n"
             "The user's own ways of working closest to this request, best first. If one applies, read it with "
             "`{cmd} show <id>` and follow it; if none does, ignore this list and don't mention it.\n")


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit - 1)
    return text[:cut if cut > limit // 2 else limit - 1].rstrip(",;:(- ") + "…"


def pull_index(found: list[store.Piece], trace: dict, pool: list[store.Piece], cmd: str = "athos",
               lines: int = PULL_LINES, cap: int = PULL_CAP,
               notes: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """The index a frontier model gets instead of the pieces: the router's choice first (and the pages it hands over
    to), then the other candidates it scored, then the rest of the pieces in reach for this request (the scope the
    hooks apply: this project's and the profile, never a piece the session may not see), most recently used first;
    one line each with id, title and "when", at most `lines` lines and `cap` characters. Returns the text and the ids
    it lists."""
    byid = {p.id: p for p in pool}                     # only what the session may see: never the store at large
    order = [p.id for p in found] + [c["piece"] for c in trace.get("candidates") or []] + \
        [p.id for p in _most_recent_first(pool)]
    picked = [byid.get(pid) for pid in dict.fromkeys(order)]
    head = PULL_HEAD.format(cmd=cmd)
    out, ids, used = [head], [], len(head) + 1         # each line costs its own length and a newline
    for p in picked:
        if p is None or len(ids) >= lines:
            continue
        line = f"- `{p.id}` — {_short(p.title, 100)}. When: {_short(p.when, PULL_WHEN)}"
        if (notes or {}).get(p.id):
            line += f" ({notes[p.id]})"
        if used + len(line) + 1 > cap:
            break
        out.append(line)
        ids.append(p.id)
        used += len(line) + 1
    extra = _often_with(found, byid, ids) if ids else None
    if extra and used + len(extra[1]) + 1 <= cap:
        out.append(extra[1])
        ids.append(extra[0])
    return ("\n".join(out) + "\n", ids) if ids else ("", [])


def _often_with(found: list[store.Piece], byid: dict, listed: list[str]) -> tuple[str, str] | None:
    """At most one more index line, when `memory.associations_line` is on: the piece most often used in the same task
    as the router's first choice, among the pieces in reach and not listed yet (memory.partner)."""
    from athos import memory
    if not found or not memory.settings().get("associations_line"):
        return None
    try:
        hit = memory.partner(found[0].id, set(byid), set(listed))
    except Exception:  # noqa: BLE001 — the index never fails for an extra line
        return None
    if not hit:
        return None
    p = byid[hit[0]]
    return p.id, (f"- often used with `{found[0].id}` ({hit[1]} tasks): `{p.id}` — {_short(p.title, 100)}. When: "
                  f"{_short(p.when, PULL_WHEN)}")


def finish_route(sid: str, total: int, added: dict[str, int] | None = None) -> None:
    """Write the route event `on_prompt(defer=True)` held, with `injected_total`: every character the prompt hook
    handed the model, the router's text and whatever the caller added after it (`added`, by kind: an edit notice, a
    share request, a rating). The router's own share stays in `injected_chars`."""
    args = _PENDING.pop(sid, None)
    if args is not None:
        _write_route(args, total, added or {})


def _write_route(args: tuple, total: int, added: dict[str, int]) -> None:
    sid, prompt, scope, trace, shown, in_store, in_scope, injected, ms = args
    trace = {**trace, "injected_parts": {**trace.get("injected_parts", {}), **{k: v for k, v in added.items() if v}}}
    try:
        note_route(sid, prompt, scope, trace, shown, in_store, in_scope, injected, ms, total=total)
    except Exception as problem:  # noqa: BLE001 — the audit never costs the person the load
        ev.hook_error("prompt", "load.note_route", problem, sid)


def note_route(sid: str, prompt: str, scope: dict, trace: dict, found: list[store.Piece], in_store: int,
               in_scope: int, injected: int, ms: float, total: int | None = None) -> None:
    """The `route` audit event for one request, and its log.md line. Neither keeps any of the request's words.
    `injected` is the router's own text; `total` everything the prompt hook handed the model (the router's text by
    default)."""
    total = injected if total is None else total
    from athos import tiers
    person, wrapper = origin_of(prompt)
    project = scope.get("project")
    kind = "empty" if not prompt.strip() else "harness" if person is False else "person"
    state = session.load(sid)
    tier = tiers.describe(state.get("model"), piece_in_reach=bool(found or trace.get("chosen")))
    printed = ev.request_print(prompt)
    if scope.get("public"):
        printed.pop("request_sha")               # a public repository: not even a fingerprint of the request
        # nor another project's name: a profile piece allowed there keeps only this project among its tags
        trace = {**trace, "candidates": [{**c, "projects": [q for q in c.get("projects") or [] if q == project]}
                                         for c in trace.get("candidates") or []]}
    ev.audit({"type": "route", "session_id": sid, "task_id": state.get("task_id"),
              "model": state.get("model"), "model_source": state.get("model_source"),
              "model_observed": session.observed(state), **tier, "mode": scope.get("mode"), "project": project,
              "scope_reason": scope.get("reason"),
              "named_projects": scope.get("named", []), "marker": bool(scope.get("marker")),
              **({"named_count": scope["named_count"]} if "named_count" in scope else {}),
              # How each mentioned project was decided (cue, distinctive, offered, rejected), never the words that
              # mentioned it; in a public repository only counted.
              **({"named_how": scope["named_how"]} if "named_how" in scope else {}),
              **({"named_how_count": scope["named_how_count"]} if "named_how_count" in scope else {}),
              "offered_projects": scope.get("offered_projects", []),
              "public": bool(scope.get("public")), "private_held": scope.get("private_held", 0),
              "store_pieces": in_store, "in_scope": in_scope,
              **printed, "request_kind": kind, "wrapper": wrapper, **trace,
              "thresholds": thresholds(), "injected_chars": injected, "injected_total": total, "ms": round(ms, 1)},
             line=(_offer_line(scope, trace.get("offered") or [], injected, total)
                   if trace.get("delivery") == "index" and kind == "person"
                   else _route_line(kind, scope, found, injected, total)), project=project)
    session.update(sid, collaborates=tier["collaborates"], **({"project": project} if project else {}))


def _route_line(kind: str, scope: dict, found: list[store.Piece], injected: int, total: int | None = None) -> str:
    """What log.md says about a request: what loaded (by id only when the piece is this project's or general), the
    characters added (and the hook's total when other text came along) and the scope's reason."""
    reason = f"scope {scope.get('reason')}"
    more = f" · {total} chars in all" if total is not None and total != injected else ""
    if kind != "person":
        return f"none · not the person's request ({kind}){more} · {reason}"
    if not found:
        return f"none{more} · {reason}"
    marker = " · public repository" if scope.get("public") else ""
    return f"loaded {loggable(found, scope.get('project'), bool(scope.get('public')))} · {injected} chars{more} · " \
           f"{reason}{marker}"


def _offer_line(scope: dict, offered: list[str], injected: int, total: int | None) -> str:
    """log.md for a frontier request: the pieces its index offered (named as `loggable` allows), not loaded."""
    byid = {p.id: p for p in store.all_pieces()}
    listed = loggable([byid[i] for i in offered if i in byid], scope.get("project"), bool(scope.get("public")))
    more = f" · {total} chars in all" if total is not None and total != injected else ""
    marker = " · public repository" if scope.get("public") else ""
    projects = scope.get("offered_projects") or []
    also = f" · may mean project {', '.join(projects)}" if projects else ""
    return f"index of {len(offered)} ({listed}){also} · {injected} chars{more} · scope {scope.get('reason')}{marker}"


def nameable(piece: store.Piece, project: str | None, public: bool = False) -> bool:
    """Whether a line about a session in `project` may name this piece: it is this project's, or general and not
    private. A private piece is named only in its own projects. In a public repository only what may load there
    (control.may_see): that project's pieces and the profile pieces allowed in public."""
    if public:
        return bool(project) and control.may_see(piece, project, True)
    if project and project in piece.projects:
        return True
    return not piece.projects and not store.private(piece)


def loggable(pieces: list[store.Piece], project: str | None, public: bool = False) -> str:
    """Pieces as log.md may name them: by id when `nameable`, else only counted."""
    own = [p.id for p in pieces if nameable(p, project, public)]
    other = len(pieces) - len(own)
    parts = own + ([f"{other} piece(s) of another project"] if other else [])
    return ", ".join(parts)


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


SESSION_PARTS: dict[str, dict[str, int]] = {}     # what each part of the session-start text cost, by session


def on_session_start(event: dict, cmd: str = "athos", platform: str = "claude-code") -> str:
    """SessionStart: remember the model, then give the catalogue, the project's recent tasks, the capture guide and
    any cheaper-model offer, in that order. The characters of each part are kept in SESSION_PARTS for the `context`
    audit event (`note_session_context`)."""
    sid = _session_of(event)
    model = _model_name(event)
    source, more = ("event" if model else "unknown"), {}
    if model is not None:
        # What the host reports now beats an older reply in a resumed session's transcript (eval.resolve_model).
        session.update(sid, model=model, model_reported=model, model_reported_at=ev._iso(ev.now()),
                       model_source="event", model_observed=True)
    elif platform == "claude-code" and not session.observed(session.load(sid)):
        # Claude Code's headless SessionStart names no model, and its transcript does not exist yet: the person's
        # configured default is a guess, enough to pick the guide, never to save (autolearn.save_mode).
        guess, how, where = session.configured_model(event.get("cwd"))
        if guess:
            model, source, more = guess, how, {"guessed_from": where}
            session.update(sid, model=guess, model_source=how, model_observed=False)
    project = paths.project_of(event["cwd"]) if event.get("cwd") else None
    ev.note_model(sid, None, model, source, None, project, stage="session_start", **more)
    from athos import capture, tiers
    here = usable(enabled(event.get("cwd")), tiers.tier_of(session.load(sid).get("model")), project)
    public = paths.is_public(event.get("cwd"))
    text = index_text(here, cmd, other_projects(here, public))
    parts = {"index": len(text)}
    # Short-term memory: the project's recent tasks, next to its ways of working (the long-term memory).
    if event.get("cwd"):
        from athos import journal
        recent = journal.text(project, public)
        if recent:
            text = (text + "\n\n" if text else "") + recent
            parts["journal"] = len(recent)
    # With the guide given here, the Stop hook only needs one line. With nothing in reach it is the whole opening: an
    # empty store, or a project with no pieces of its own (since these no longer see every other project's), whose
    # first tasks can be saved as its first ways of working (2026-11-01: a first run opened with nothing, so the
    # first task's trail stayed empty). "none" keeps Athos quiet.
    first_run = not text and control.get()["mode"] != "none"
    from athos import autolearn
    mode = autolearn.session_mode(sid)
    # An apply model never saves, so it gets no capture guide; a frontier one with autonomous learning gets its own.
    from athos import indicator
    quiet = indicator.minimal()
    if (text or first_run) and capture.enabled() and mode != autolearn.APPLY:
        auto = autolearn.autonomous(sid)
        guide = capture.guide(cmd, auto=auto, ask=autolearn.ask_mode(), minimal=quiet)
        text = (text + "\n\n" if text else "") + guide
        parts["guide"] = len(guide)
        session.update(sid, guide="auto" if auto else True)
    elif (text or first_run) and capture.enabled():
        # Held back only because the model is (or is guessed) an apply one: should it turn out to be a frontier model,
        # the guide comes later, once, out of the person's sight (cli._guide_after_correction).
        session.update(sid, guide="withheld")
    from athos import replay
    # A cheaper model proven on a piece in reach here: told once, at the session's start (never another project's).
    # The model says it in its reply, so the person reads it: only in the classic interface.
    offer = "" if quiet else replay.offer_text(None if not event.get("cwd") else [p.id for p in here], cmd)
    if offer:
        text = (text + "\n\n" if text else "") + offer
        parts["offer"] = len(offer)
    if text:                                    # where Athos's own decisions are written down, for an agent to audit
        hint = audit_hint(sid, cmd)
        text += "\n\n" + hint
        parts["audit_hint"] = len(hint)
    SESSION_PARTS[sid] = {k: v for k, v in parts.items() if v}
    return text


def note_session_context(sid: str, project: str | None, total: int, added: dict[str, int] | None = None) -> None:
    """The `context` audit event of a session start: every character the hook handed the model (`injected_total`)
    and what each part cost (`injected_parts`: index, journal, guide, offer, audit_hint, and what the caller added,
    such as the overnight review's offer)."""
    parts = {**SESSION_PARTS.pop(sid, {}), **{k: v for k, v in (added or {}).items() if v}}
    ev.audit({"type": "context", "hook": "session_start", "session_id": sid, "project": project,
              "injected_total": total, "injected_parts": parts, "index_cap": INDEX_CAP},
             line=f"session start · {total} chars" if total else None, project=project)


def audit_hint(sid: str, cmd: str = "athos") -> str:
    """One line for the model: where the audit log is and the command that summarizes this session."""
    from pathlib import Path
    where, home = str(ev.log_file()), str(Path.home())
    if where.startswith(home + "/"):
        where = "~" + where[len(home):]
    return (f"Athos logs what it decides (loads and why, edits it attributes, triggers, errors) in `{where}`; "
            f"`{cmd} audit --session {sid}` summarizes this session.")
