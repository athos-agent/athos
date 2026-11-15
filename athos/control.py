"""Which ways of working Athos is allowed to load.

The person picks a loading mode once and it sticks: it is saved as JSON in `<home>/selection.json`.

    {"mode": "auto"}                                 default: this project's pieces, the profile, and another
                                                     project's only when the request names it
    {"mode": "all"}                                  every piece (but a private one only in its own projects)
    {"mode": "project", "project": "athos"}          one named project's pieces plus the profile
    {"mode": "project"}                              likewise, for the project the session is running in
    {"mode": "pieces", "pieces": ["a", "b"]}         an explicit list of piece ids
    {"mode": "none"}                                 load nothing; Athos keeps quiet

The profile (`<home>/profile.json`, `athos profile`) is the short, explicit list of pieces that apply in every project:
how the person always works. A piece is not general just because it has no project: an untagged piece outside the
profile loads only where no folder is known (Claude Desktop's chat) or with `athos load all`.

Whatever the mode, a piece whose visibility is `private` (store.visibility) loads only in a session of one of its
own projects. In a repository whose `.athos.toml` says `public = true`, every piece that is not that project's is
treated as private: it never loads and is never named there, even when the request names its project, and a profile
piece only when the person allowed it in public repositories (`athos profile allow-public <id>`); a private piece of
that very project stays out too. Where no folder is known (Claude Desktop's chat) every piece stays in reach, as
before.
"""

from __future__ import annotations

import json
import re

from athos import paths, store

MODES = ("auto", "all", "project", "pieces", "none")

_DEFAULT_MODE = "auto"
PROFILE_MAX = 12          # the profile stays small: what applies everywhere is a handful of habits, not a store
_NOT_A_NAME_CHAR = re.compile(r"[^a-z0-9áéíóúñü]+")


def _fallback() -> dict:
    return {"mode": _DEFAULT_MODE}


def _read_saved() -> object:
    """Whatever JSON the selection file holds, or None when it is absent or not readable as JSON."""
    try:
        return json.loads(paths.selection_file().read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def get() -> dict:
    """The saved selection, or the default when the file is missing, unreadable or names an unknown mode."""
    saved = _read_saved()
    if isinstance(saved, dict) and saved.get("mode") in MODES:
        return saved
    return _fallback()


def _validated_piece_ids(requested: list[str] | None) -> list[str]:
    """Every requested id must name a piece in the store; an empty request is refused too."""
    if not requested:
        raise ValueError("name at least one piece")
    in_store = {piece.id for piece in store.all_pieces()}
    unknown = [pid for pid in requested if pid not in in_store]
    if unknown:
        raise ValueError("unknown pieces: " + ", ".join(unknown))
    return list(requested)


def _save(selection: dict) -> None:
    target = paths.selection_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(selection))


def _mode_options(mode: str, values: list[str] | None) -> dict:
    """The extra keys a mode stores next to `mode`: the piece list, or the pinned project when one was given."""
    if mode == "pieces":
        return {"pieces": _validated_piece_ids(values)}
    if mode == "project" and values:
        return {"project": values[0]}
    return {}


def set_selection(mode: str, values: list[str] | None = None) -> dict:
    """Validate and persist a new loading mode; returns what was saved. Raises ValueError and saves nothing on bad
    input, so the previous choice survives a typo."""
    unrecognised = mode not in MODES
    if unrecognised:
        raise ValueError(f"unknown loading mode {mode!r}; pick one of: {', '.join(MODES)}")
    selection: dict = {"mode": mode}
    selection.update(_mode_options(mode, values))
    _save(selection)
    return selection


def describe(sel: dict | None = None, lang: str = "en") -> str:
    """One human line for `athos load` and `athos list`: what is being loaded right now, in the person's language."""
    selection = sel or get()
    mode = selection["mode"]
    if lang == "es":
        labels = {
            "project": lambda: "proyecto " + selection.get("project", "(el actual)"),
            "pieces": lambda: "formas de trabajar " + ", ".join(selection.get("pieces", [])),
            "auto": lambda: "auto (las de este proyecto, tu perfil, y las de otro proyecto cuando el pedido lo "
                            "nombra)",
        }
    else:
        labels = {
            "project": lambda: "project " + selection.get("project", "(the current one)"),
            "pieces": lambda: "pieces " + ", ".join(selection.get("pieces", [])),
            "auto": lambda: "auto (this project's pieces, your profile, and another project's when the request "
                            "names it)",
        }
    return labels[mode]() if mode in labels else mode


# ------------------------------------------------------------------------------------------------ the profile
def _read_profile() -> dict:
    try:
        data = json.loads(paths.profile_file().read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def profile_ids() -> list[str]:
    """The ids in the profile, in the order they were added."""
    ids = _read_profile().get("pieces")
    return [str(i) for i in ids] if isinstance(ids, list) else []


def public_ids() -> list[str]:
    """The profile pieces the person allowed in public repositories (`athos profile allow-public`): by default none,
    so a public repository sees only its own pieces."""
    ids = _read_profile().get("public")
    wanted = set(profile_ids())
    return [str(i) for i in ids if str(i) in wanted] if isinstance(ids, list) else []


def _save_profile(ids: list[str], public: list[str] | None = None) -> None:
    target = paths.profile_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    allowed = [i for i in (public_ids() if public is None else public) if i in ids]
    target.write_text(json.dumps({"pieces": ids, **({"public": allowed} if allowed else {})}, indent=1) + "\n")


def profile_allow_public(ids: list[str], allow: bool = True) -> list[str]:
    """Allow (or, with `allow` False, no longer allow) profile pieces in repositories marked public. Returns the
    allowed ids. ValueError, and nothing saved, for an id that is not in the profile."""
    current = profile_ids()
    outside = [i for i in ids if i not in current]
    if outside and allow:
        raise ValueError("not in the profile: " + ", ".join(outside) + " (`athos profile add <id>` first)")
    allowed = public_ids()
    allowed = (allowed + [i for i in dict.fromkeys(ids) if i not in allowed]) if allow else \
        [i for i in allowed if i not in set(ids)]
    _save_profile(current, allowed)
    return allowed


def profile_add(ids: list[str], cap: bool = True) -> list[str]:
    """Put pieces in the profile; returns the profile. ValueError, and nothing saved, for an unknown or private piece
    or (with `cap`) when the profile would pass PROFILE_MAX: what applies everywhere must stay short."""
    byid = {p.id: p for p in store.all_pieces()}
    unknown = [i for i in ids if i not in byid]
    if unknown:
        raise ValueError("unknown pieces: " + ", ".join(unknown))
    if any(store.private(byid[i]) for i in ids):
        raise ValueError("a private piece stays in its own projects; it cannot join the profile")
    current = profile_ids()
    merged = current + [i for i in dict.fromkeys(ids) if i not in current]
    if cap and len(merged) > PROFILE_MAX:
        raise ValueError(f"the profile holds at most {PROFILE_MAX} pieces ({len(current)} now): keep it to what "
                         f"applies in every project, and tag the rest with their project")
    _save_profile(merged)
    return merged


def profile_pieces(pieces: list[store.Piece] | None = None) -> list[store.Piece]:
    """The pieces in the profile that exist and are not private: what may apply in every project, and so the only
    pieces written where every project's agent reads them (~/.agents/skills)."""
    wanted = set(profile_ids())
    return [p for p in (store.all_pieces() if pieces is None else pieces) if p.id in wanted and not store.private(p)]


def profile_remove(ids: list[str]) -> list[str]:
    current = profile_ids()
    kept = [i for i in current if i not in set(ids)]
    _save_profile(kept)                       # an id that leaves the profile is no longer allowed in public either
    return kept


# ------------------------------------------------------------------------------------------------ the scope
SHORT_NAME = 4             # a one-word project name this short counts only as a word of its own in the request


def named_projects(known, prompt: str) -> list[str]:
    """The projects among `known` a request names: by its name, or the name with spaces ("heat v2" for heat-v2).
    The longest name wins: a name found only inside a longer one that is also named does not count ("heat-v2" names
    heat-v2, not heat). A short one-word name ("api", "heat") counts only as a word of its own, not as part of a
    compound ("api.js", "heat-v2"). A project named like a common word is still named by that word ("the api")."""
    words = _NOT_A_NAME_CHAR.sub(" ", (prompt or "").lower()).split()
    raw = {tok.strip(".,;:!?()[]{}\"'`") for tok in (prompt or "").lower().split()}
    spans: dict[str, list[tuple[int, int]]] = {}
    for q in dict.fromkeys(known):
        name = _NOT_A_NAME_CHAR.sub(" ", str(q).lower()).split()
        if not name or (len(name) == 1 and len(name[0]) <= SHORT_NAME and str(q).lower() not in raw):
            continue
        k = len(name)
        hits = [(i, i + k) for i in range(len(words) - k + 1) if words[i:i + k] == name]
        if hits:
            spans[q] = hits

    def inside(a: tuple[int, int], b: tuple[int, int]) -> bool:
        return b[0] <= a[0] and a[1] <= b[1] and b[1] - b[0] > a[1] - a[0]
    return sorted(q for q, hits in spans.items()
                  if any(not any(inside(h, g) for r, gs in spans.items() if r != q for g in gs) for h in hits))


def _named(project: str, prompt: str) -> bool:
    """Whether a request names this project (`named_projects`, with no other project to compare with)."""
    return project in named_projects([project], prompt)


def may_see(piece: store.Piece, here: str | None, public: bool = False) -> bool:
    """Whether a session in project `here` (None: no folder known) may load or name this piece.

    No folder: always. In a repository marked public: only a piece of that project that is not private, or a profile
    piece the person allowed in public repositories; every other piece is treated as private there, whatever its own
    visibility, even when the request names its project (a public repository's session once carried another
    project's piece titles, 2026-11-15). Anywhere else: always, unless the piece is private and the session is not in
    one of its projects."""
    if here is None:
        return True
    if public:
        if store.private(piece):
            return False
        return here in piece.projects or piece.id in public_ids()
    if not store.private(piece):
        return True
    return here in piece.projects


NOT_HERE = ("no piece {id} here: this repository is marked public ({marker}), so only {project}'s own pieces are "
            "named or used in it. From a folder outside it, `athos show {id}` reads any piece.")


class Here:
    """What a command run in a folder may name, print, write or act on. Outside a repository marked public: every
    piece, as before. In one: only what may load there (`may_see`): this project's pieces that are not private, and the
    profile pieces the person allowed in public; an id that is not in the store is treated the same as one that may
    not be named, so the answer never says whether another project has it. Every command that prints piece ids or
    titles goes through it (`cli.main` gates any command that takes a piece id), so a new command cannot forget it."""

    def __init__(self, cwd: str | None = None):
        import os
        self.cwd = cwd or os.getcwd()
        self.project, mark = paths.locate(self.cwd)
        self.public = mark.get("public") is True
        self.marker = mark.get("file") or paths.MARKER
        self._byid: dict[str, store.Piece] | None = None

    def _pieces(self) -> dict[str, store.Piece]:
        if self._byid is None:
            self._byid = {p.id: p for p in store.all_pieces()}
        return self._byid

    def may_name(self, piece: store.Piece | str | None) -> bool:
        if not self.public:
            return True
        if isinstance(piece, str):
            piece = self._pieces().get(piece)
        return piece is not None and may_see(piece, self.project, True)

    def pieces(self, pieces: list[store.Piece]) -> list[store.Piece]:
        return [p for p in pieces if self.may_name(p)]

    def ids(self, ids) -> list[str]:
        return [i for i in ids if self.may_name(str(i))]

    def hidden_ids(self) -> list[str]:
        return [] if not self.public else [i for i, p in self._pieces().items() if not self.may_name(p)]

    def mentions_hidden(self, text: str) -> bool:
        """Whether a line names, as a whole word, a piece that may not be named here."""
        if not self.public:
            return False
        return any(re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text) for i in self.hidden_ids())

    def lines(self, lines) -> list[str]:
        return [str(x) for x in lines if not self.mentions_hidden(str(x))]

    def refuse(self, piece_id: str) -> str:
        return NOT_HERE.format(id=piece_id, marker=self.marker, project=self.project)


def here(cwd: str | None = None) -> Here:
    return Here(cwd)


def scope(pieces: list[store.Piece], cwd: str | None, prompt: str = "") -> list[store.Piece]:
    """One memory per project: the pieces of the project the session runs in, the profile, and another project's
    only when the request names it. No folder at all (Claude Desktop's chat) sees every piece. With every piece in one
    pool, work in one project loaded another project's pages (2026-10-31: 27 of 71 pages were one project's, and they
    loaded in others); a folder with no pieces of its own used to see all of them, and loaded other projects' pages
    on its first day."""
    if not cwd:
        return pieces
    return scope_project(pieces, paths.project_of(cwd), prompt, paths.is_public(cwd))


def scope_project(pieces: list[store.Piece], here: str, prompt: str = "", public: bool = False) -> list[store.Piece]:
    return _auto(pieces, here, prompt, public)[0]


def _auto(pieces: list[store.Piece], here: str, prompt: str,
          public: bool) -> tuple[list[store.Piece], str, list[str], int]:
    """The `auto` scope for a session in project `here`: (pieces, reason, other projects the request named, private
    pieces held back that would otherwise be in it)."""
    known = {q for p in pieces for q in p.projects}
    named = [q for q in named_projects(known | {here}, prompt) if q != here]
    profile = set(profile_ids())
    own = any(here in p.projects for p in pieces)
    reach = [p for p in pieces if here in p.projects or p.id in profile or set(named) & set(p.projects)]
    pool = [p for p in reach if may_see(p, here, public)]
    reason = ("auto:project" if own else "auto:no-own-pieces") + ("+named" if named else "")
    return pool, reason, named, len(reach) - len(pool)


def _in_project(pieces: list[store.Piece], project: str | None) -> list[store.Piece]:
    """A project's own pieces plus the profile."""
    profile = set(profile_ids())
    return [piece for piece in pieces if piece.id in profile or project in piece.projects]


def filter_pieces(pieces: list[store.Piece], cwd: str | None = None, prompt: str = "",
                  project: str | None = None) -> list[store.Piece]:
    """Apply the saved selection to the store's pieces for a session in `cwd` answering `prompt`. `project` names the
    session's project directly (a replay that has no folder on this machine); otherwise it is read from `cwd`."""
    return select(pieces, cwd, prompt, project)[0]


def select(pieces: list[store.Piece], cwd: str | None = None, prompt: str = "",
           project: str | None = None, public: bool | None = None) -> tuple[list[store.Piece], dict]:
    """`filter_pieces`, plus why that scope applied, for the audit log (`route` events): the mode, the project, a
    reason, the other projects the request named, whether a `.athos.toml` marker applied and says the repository is
    public, and how many private pieces were held back (a count, never which). The reasons:

        none / all / pieces / project       the saved mode decided
        auto:no-folder                      no folder (Claude Desktop's chat): every piece
        auto:project                        this project's pieces and the profile
        auto:no-own-pieces                  a project with no pieces of its own: the profile only
        auto:project+named                  ...and those of the other projects the request names
        auto:no-own-pieces+named            likewise, for a project with no pieces of its own
    """
    selection = get()
    mode = selection["mode"]
    found, mark = paths.locate(cwd) if cwd else (None, {})
    here = project or found
    public = bool(mark.get("public")) if public is None else public
    why = {"mode": mode, "project": here, "reason": mode, "named": [], "marker": bool(mark), "public": public}
    if mode == "auto" and here and public:
        # In a public repository another project is not named anywhere, not even in Athos's own log: only counted.
        pool, reason, named, held = _auto(pieces, here, prompt, public)
        return pool, {**why, "reason": reason, "named": [], "named_count": len(named), "private_held": held}

    def visible(chosen: list[store.Piece]) -> tuple[list[store.Piece], dict]:
        kept = [p for p in chosen if may_see(p, here, public)]
        return kept, {**why, "private_held": len(chosen) - len(kept)}

    if mode == "auto":
        if not here:
            return list(pieces), {**why, "reason": "auto:no-folder", "private_held": 0}
        pool, reason, named, held = _auto(pieces, here, prompt, public)
        return pool, {**why, "reason": reason, "named": named, "private_held": held}
    if mode == "none":
        return [], {**why, "private_held": 0}
    if mode == "project":
        chosen = selection.get("project") or here or paths.project_of(cwd)
        kept, info = visible(_in_project(pieces, chosen))
        return kept, {**info, "project": here or chosen}
    if mode == "pieces":
        wanted = set(selection.get("pieces", []))
        return visible([piece for piece in pieces if piece.id in wanted])
    return visible(list(pieces))                                 # "all": nothing is held back but private pieces
