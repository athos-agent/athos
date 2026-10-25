"""The know-how store: one markdown file per piece, with a small frontmatter the user can read and edit.

    ---
    id: release-checklist
    title: Cut a release
    when: preparing a release of a Python package
    projects: [athos]
    created: 2026-10-26
    last_used: 2026-10-27
    origin:
      platform: claude-code
      model: claude-opus-5-5
    version: 2
    ---
    <steps, criteria, mistakes avoided>

    ## History
    - v2 2026-10-27 (claude-code, claude-opus-5-5): added the changelog step
    - v1 2026-10-26 (claude-code, claude-opus-5-5): created

Every change keeps the previous version under `.history/<id>/v<n>.md`, so nothing is overwritten silently.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from athos import paths


@dataclass
class Piece:
    id: str
    title: str
    when: str
    body: str = ""
    projects: list[str] = field(default_factory=list)
    created: str = ""
    last_used: str = ""
    origin: dict = field(default_factory=dict)
    version: int = 1
    history: list[str] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return paths.know_how() / f"{self.id}.md"


def today() -> str:
    return _dt.date.today().isoformat()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60].strip("-") or "piece"


# ------------------------------------------------------------------------------------------------ frontmatter
def _scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].replace('\\"', '"')
    return v


def _quote(v: str) -> str:
    if v != v.strip() or not v or any(c in v for c in ':#[]{},"'):
        return '"' + v.replace('"', '\\"') + '"'
    return v


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """`(fields, body)` for a document that starts with `---`; `({}, text)` otherwise. Understands the subset Athos
    writes: `key: value`, `key: [a, b]` and one level of nested `key:` / `  sub: value`."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    head, body = text[3:end].strip("\n"), text[end + 4:].lstrip("\n")
    data: dict = {}
    parent = None
    for line in head.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        indent, key, val = m.groups()
        if indent and parent is not None:
            data[parent][key] = _scalar(val)
            continue
        if val == "":
            data[key], parent = {}, key
        elif val.startswith("[") and val.endswith("]"):
            data[key], parent = [_scalar(x) for x in val[1:-1].split(",") if x.strip()], None
        else:
            data[key], parent = _scalar(val), None
    return data, body


def _split_history(body: str) -> tuple[str, list[str]]:
    m = re.search(r"^## History\s*$", body, re.M)
    if not m:
        return body.rstrip(), []
    lines = [ln.strip()[2:] for ln in body[m.end():].splitlines() if ln.strip().startswith("- ")]
    return body[:m.start()].rstrip(), lines


def parse(text: str) -> Piece:
    data, body = parse_frontmatter(text)
    body, hist = _split_history(body)
    projects = data.get("projects") or []
    return Piece(id=data.get("id", ""), title=data.get("title", ""), when=data.get("when", ""), body=body,
                 projects=projects if isinstance(projects, list) else [projects],
                 created=data.get("created", ""), last_used=data.get("last_used", ""),
                 origin=data.get("origin") if isinstance(data.get("origin"), dict) else {},
                 version=int(data.get("version") or 1), history=hist)


def render(p: Piece) -> str:
    out = ["---", f"id: {p.id}", f"title: {_quote(p.title)}", f"when: {_quote(p.when)}",
           f"projects: [{', '.join(p.projects)}]", f"created: {p.created}", f"last_used: {p.last_used}", "origin:"]
    out += [f"  {k}: {_quote(str(v))}" for k, v in p.origin.items()] or ["  platform: unknown"]
    out += [f"version: {p.version}", "---", "", p.body.rstrip(), "", "## History"]
    out += [f"- {h}" for h in p.history]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------ store
def all_pieces() -> list[Piece]:
    d = paths.know_how()
    if not d.is_dir():
        return []
    return [parse(f.read_text()) for f in sorted(d.glob("*.md"))]


def get(piece_id: str) -> Piece | None:
    f = paths.know_how() / f"{piece_id}.md"
    return parse(f.read_text()) if f.is_file() else None


def _write(p: Piece) -> None:
    p.path.parent.mkdir(parents=True, exist_ok=True)
    p.path.write_text(render(p))


def _origin_label(origin: dict) -> str:
    return ", ".join(str(origin.get(k, "unknown")) for k in ("platform", "model"))


def create(title: str, when: str, body: str, projects: list[str] | None = None, origin: dict | None = None,
           piece_id: str | None = None) -> Piece:
    pid = slugify(piece_id or title)
    base, n = pid, 2
    while (paths.know_how() / f"{pid}.md").exists():
        pid, n = f"{base}-{n}", n + 1
    origin = origin or {"platform": "unknown", "model": "unknown"}
    p = Piece(id=pid, title=title, when=when, body=body, projects=projects or [], created=today(),
              last_used=today(), origin=origin, version=1,
              history=[f"v1 {today()} ({_origin_label(origin)}): created"])
    _write(p)
    return p


def update(piece_id: str, note: str, body: str | None = None, title: str | None = None, when: str | None = None,
           origin: dict | None = None, projects: list[str] | None = None) -> tuple[Piece, str]:
    """Improve a piece: archive the current version, bump `version`, add a history line. Returns the new piece and a
    unified diff of the change, which callers show to the user."""
    old = get(piece_id)
    if old is None:
        raise KeyError(piece_id)
    arch = paths.history() / old.id
    arch.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old.path, arch / f"v{old.version}.md")
    origin = origin or old.origin
    new = Piece(id=old.id, title=title or old.title, when=when or old.when,
                body=body if body is not None else old.body,
                projects=sorted(set(old.projects) | set(projects or [])), created=old.created, last_used=today(),
                origin=origin, version=old.version + 1,
                history=[f"v{old.version + 1} {today()} ({_origin_label(origin)}): {note.strip() or 'updated'}"]
                + old.history)
    _write(new)
    diff = "".join(difflib.unified_diff(render(old).splitlines(True), render(new).splitlines(True),
                                        f"{old.id} v{old.version}", f"{old.id} v{new.version}"))
    return new, diff


def revert(piece_id: str) -> Piece:
    """Put back the previous version. The version being replaced is archived too, so a revert can be reverted."""
    cur = get(piece_id)
    if cur is None:
        raise KeyError(piece_id)
    arch = paths.history() / piece_id
    prev = arch / f"v{cur.version - 1}.md"
    if not prev.is_file():
        raise FileNotFoundError(f"no earlier version of {piece_id}")
    shutil.copy2(cur.path, arch / f"v{cur.version}.md")
    old = parse(prev.read_text())
    old.version = cur.version + 1
    old.history = [f"v{old.version} {today()}: reverted to v{cur.version - 1}"] + cur.history
    _write(old)
    return old


def touch(piece_id: str) -> None:
    """Record that a piece was used today, without counting it as a new version."""
    p = get(piece_id)
    if p and p.last_used != today():
        p.last_used = today()
        _write(p)


def export(dest: Path) -> int:
    """Copy the whole store (with its history) to `dest`. Returns how many pieces were exported."""
    src = paths.know_how()
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if not src.is_dir():
        return 0
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return len(list(src.glob("*.md")))
