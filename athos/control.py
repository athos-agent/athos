"""Which ways of working Athos is allowed to load.

The person picks a loading mode once and it sticks: it is saved as JSON in `<home>/selection.json`.

    {"mode": "auto"}                                 default: this project's pieces, the untagged ones, and another
                                                     project's only when the request names it
    {"mode": "all"}                                  no filtering at all
    {"mode": "project", "project": "athos"}          one named project's pieces plus the untagged ones
    {"mode": "project"}                              likewise, for the project the session is running in
    {"mode": "pieces", "pieces": ["a", "b"]}         an explicit list of piece ids
    {"mode": "none"}                                 load nothing; Athos keeps quiet
"""

from __future__ import annotations

import json
import re

from athos import paths, store

MODES = ("auto", "all", "project", "pieces", "none")

_DEFAULT_MODE = "auto"
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


def describe(sel: dict | None = None) -> str:
    """One human line for `athos load` and `athos list`: what is being loaded right now."""
    selection = sel or get()
    mode = selection["mode"]
    labels = {
        "project": lambda: "project " + selection.get("project", "(the current one)"),
        "pieces": lambda: "pieces " + ", ".join(selection.get("pieces", [])),
        "auto": lambda: "auto (this project's pieces, the untagged ones, and another project's when the request names it)",
    }
    return labels[mode]() if mode in labels else mode


def _named(project: str, prompt: str) -> bool:
    """Whether a request names a project: its folder name, or the name with spaces ("heat v2")."""
    text = " " + _NOT_A_NAME_CHAR.sub(" ", (prompt or "").lower()) + " "
    name = _NOT_A_NAME_CHAR.sub(" ", project.lower()).strip()
    return bool(name) and f" {name} " in text


def scope(pieces: list[store.Piece], cwd: str | None, prompt: str = "") -> list[store.Piece]:
    """One memory per project: the pieces of the project the session runs in, the untagged ones (general know-how),
    and another project's only when the request names it. A folder no piece belongs to, or no folder at all (Claude
    Desktop's chat), sees every piece: there is nothing to keep apart. With every piece in one pool, work in one
    project loaded another project's pages (2026-10-31: 27 of 71 pages were one project's, and they loaded in
    others)."""
    if not cwd:
        return pieces
    return scope_project(pieces, paths.project_of(cwd), prompt)


def scope_project(pieces: list[store.Piece], here: str, prompt: str = "") -> list[store.Piece]:
    known = {q for p in pieces for q in p.projects}
    if here not in known:
        return pieces
    named = {q for q in known if q != here and _named(q, prompt)}
    return [p for p in pieces if not p.projects or here in p.projects or named & set(p.projects)]


def _in_project(pieces: list[store.Piece], project: str | None) -> list[store.Piece]:
    """A project's own pieces plus the untagged, general ones."""
    return [piece for piece in pieces if not piece.projects or project in piece.projects]


def filter_pieces(pieces: list[store.Piece], cwd: str | None = None, prompt: str = "") -> list[store.Piece]:
    """Apply the saved selection to the store's pieces for a session in `cwd` answering `prompt`."""
    selection = get()
    mode = selection["mode"]
    if mode == "auto":
        return scope(pieces, cwd, prompt)
    if mode == "none":
        return []
    if mode == "project":
        return _in_project(pieces, selection.get("project") or paths.project_of(cwd))
    if mode == "pieces":
        wanted = set(selection.get("pieces", []))
        return [piece for piece in pieces if piece.id in wanted]
    return list(pieces)                                          # "all": nothing is held back
