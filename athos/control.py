"""Control: which pieces may be loaded. The choice lives in `<home>/selection.json` and holds until changed:

    {"mode": "auto"}                                 the default: the pieces of the project the session runs in, the
                                                     untagged ones, and another project's only when the request names it
    {"mode": "all"}                                  every piece
    {"mode": "project", "project": "athos"}          pieces tagged with that project, plus untagged ones
    {"mode": "project"}                              the same, for whichever project the session runs in
    {"mode": "pieces", "pieces": ["a", "b"]}         only these pieces
    {"mode": "none"}                                 nothing (Athos stays quiet)
"""

from __future__ import annotations

import json
import re

from athos import paths, store

MODES = ("auto", "all", "project", "pieces", "none")


def get() -> dict:
    try:
        sel = json.loads(paths.selection_file().read_text())
        return sel if sel.get("mode") in MODES else {"mode": "auto"}
    except (OSError, ValueError, AttributeError):
        return {"mode": "auto"}


def set_selection(mode: str, values: list[str] | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    sel: dict = {"mode": mode}
    if mode == "project" and values:
        sel["project"] = values[0]
    if mode == "pieces":
        known = {p.id for p in store.all_pieces()}
        missing = [v for v in values or [] if v not in known]
        if not values or missing:
            raise ValueError("unknown pieces: " + ", ".join(missing) if missing else "name at least one piece")
        sel["pieces"] = list(values)
    f = paths.selection_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(sel))
    return sel


def describe(sel: dict | None = None) -> str:
    sel = sel or get()
    if sel["mode"] == "project":
        return f"project {sel.get('project', '(the current one)')}"
    if sel["mode"] == "pieces":
        return "pieces " + ", ".join(sel.get("pieces", []))
    if sel["mode"] == "auto":
        return "auto (this project's pieces, the untagged ones, and another project's when the request names it)"
    return sel["mode"]


def _named(project: str, prompt: str) -> bool:
    """Whether a request names a project: its folder name, or the name with spaces ("heat v2")."""
    text = " " + re.sub(r"[^a-z0-9áéíóúñü]+", " ", (prompt or "").lower()) + " "
    name = re.sub(r"[^a-z0-9áéíóúñü]+", " ", project.lower()).strip()
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


def filter_pieces(pieces: list[store.Piece], cwd: str | None = None, prompt: str = "") -> list[store.Piece]:
    sel = get()
    if sel["mode"] == "none":
        return []
    if sel["mode"] == "auto":
        return scope(pieces, cwd, prompt)
    if sel["mode"] == "pieces":
        keep = set(sel.get("pieces", []))
        return [p for p in pieces if p.id in keep]
    if sel["mode"] == "project":
        project = sel.get("project") or paths.project_of(cwd)
        return [p for p in pieces if not p.projects or project in p.projects]
    return pieces
