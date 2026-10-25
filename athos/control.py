"""Control: which pieces may be loaded. The choice lives in `<home>/selection.json` and holds until changed:

    {"mode": "all"}                                  every piece (the default)
    {"mode": "project", "project": "athos"}          pieces tagged with that project, plus untagged ones
    {"mode": "project"}                              the same, for whichever project the session runs in
    {"mode": "pieces", "pieces": ["a", "b"]}         only these pieces
    {"mode": "none"}                                 nothing (Athos stays quiet)
"""

from __future__ import annotations

import json

from athos import paths, store

MODES = ("all", "project", "pieces", "none")


def get() -> dict:
    try:
        sel = json.loads(paths.selection_file().read_text())
        return sel if sel.get("mode") in MODES else {"mode": "all"}
    except (OSError, ValueError, AttributeError):
        return {"mode": "all"}


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
    return sel["mode"]


def filter_pieces(pieces: list[store.Piece], cwd: str | None = None) -> list[store.Piece]:
    sel = get()
    if sel["mode"] == "none":
        return []
    if sel["mode"] == "pieces":
        keep = set(sel.get("pieces", []))
        return [p for p in pieces if p.id in keep]
    if sel["mode"] == "project":
        project = sel.get("project") or paths.project_of(cwd)
        return [p for p in pieces if not p.projects or project in p.projects]
    return pieces
