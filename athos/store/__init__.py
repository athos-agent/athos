"""Where pieces of know-how live on disk.

A piece is a plain markdown file, `<home>/know-how/<id>.md`, that a person can open and change by hand. It begins
with a frontmatter block between two `---` lines holding, in this order: `id`; `title`; `when` (the situation the
piece is for); `projects` as an inline list such as `[athos, docs]`; the `created` and `last_used` dates; an
`origin` mapping whose indented `platform` and `model` say where it was written; and the `version` number. The
steps, criteria and mistakes to avoid follow as free markdown. Last comes a `## History` heading over a bullet
list of changes, newest first, each shaped like `v2 <date> (<platform>, <model>): <what changed>`.

`render` writes exactly this layout and `parse` reads it back. Changing a piece never loses the text it replaces:
the outgoing version is first copied to `.history/<id>/v<n>.md` inside the know-how folder.
"""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path

from athos import paths

INDEX_NAME = "Index.md"                 # the wiki writes its index next to the pieces; it is not a piece
HISTORY_HEADING = "## History"
_ID_MAX = 60
_UNKNOWN_ORIGIN = {"platform": "unknown", "model": "unknown"}
_NEEDS_QUOTES = set(':#[]{},"')
_KEY_LINE = re.compile(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$")
_HISTORY_LINE = re.compile(r"^## History\s*$", re.M)


@dataclass
class Piece:
    """One piece of know-how, as read from (or about to be written to) its markdown file."""

    id: str
    title: str
    when: str
    body: str = ""
    projects: list[str] = field(default_factory=list)
    created: str = ""
    last_used: str = ""
    origin: dict = field(default_factory=dict)
    version: int = 1
    history: list[str] = field(default_factory=list)       # newest first, without the leading "- "

    @property
    def path(self) -> Path:
        return _file_for(self.id)


def _file_for(piece_id: str) -> Path:
    return paths.know_how() / (piece_id + ".md")


def today() -> str:
    """Today's date as `YYYY-MM-DD`."""
    return _date.today().isoformat()


def slugify(text: str) -> str:
    """A filename-safe id: lowercase ASCII letters and digits joined by single dashes, at most 60 characters."""
    dashed = "-".join(re.findall(r"[a-z0-9]+", text.lower()))
    return dashed[:_ID_MAX].strip("-") or "piece"


# ---------------------------------------------------------------------------------------------------- frontmatter
def _scalar(raw: str) -> str:
    """A frontmatter value with surrounding blanks and one pair of matching quotes removed."""
    value = raw.strip()
    quoted = len(value) > 1 and value[0] in "\"'" and value[-1] == value[0]
    return value[1:-1].replace('\\"', '"') if quoted else value


def _quote(v: str) -> str:
    """`v` as a frontmatter value: wrapped in double quotes when it would not read back unchanged otherwise."""
    risky = not v or v.strip() != v or any(ch in _NEEDS_QUOTES for ch in v)
    escaped = v.replace('"', '\\"')
    return f'"{escaped}"' if risky else v


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """`(header, body)` when `text` opens with a `---` block that is closed again, else None."""
    if text[:3] != "---":
        return None
    close = text.find("\n---", 3)
    if close == -1:
        return None
    return text[3:close].strip("\n"), text[close + 4:].lstrip("\n")


def _key_lines(header: str):
    """`(indent, key, value)` for every `key: value` line of a frontmatter header; blanks and `#` comments and any
    other line are passed over."""
    for line in header.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            found = _KEY_LINE.match(line)
            if found is not None:
                yield found.groups()


def _header_fields(header: str) -> dict:
    fields: dict = {}
    mapping_key = None                  # the key whose nested `sub: value` lines we are reading, if any
    for indent, key, value in _key_lines(header):
        if indent and mapping_key is not None:
            fields[mapping_key][key] = _scalar(value)
        elif value == "":
            fields[key], mapping_key = {}, key
        elif value[:1] == "[" and value[-1:] == "]":
            fields[key], mapping_key = [_scalar(item) for item in value[1:-1].split(",") if item.strip()], None
        else:
            fields[key], mapping_key = _scalar(value), None
    return fields


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a document into `(fields, body)`; a document without frontmatter gives `({}, text)`.

    Only the shapes Athos itself writes are understood: `key: value`, inline lists `key: [a, b]`, and a mapping one
    level deep (`key:` followed by indented `sub: value` lines)."""
    parts = _split_frontmatter(text)
    if parts is None:
        return ({}, text)
    return _header_fields(parts[0]), parts[1]


def _body_and_changelog(body: str) -> tuple[str, list[str]]:
    """Separate the `## History` list from the rest of the body."""
    heading = _HISTORY_LINE.search(body)
    text_end = heading.start() if heading else len(body)
    changelog = body[heading.end():] if heading else ""
    entries = [item[2:] for item in map(str.strip, changelog.splitlines()) if item.startswith("- ")]
    return body[:text_end].rstrip(), entries


def parse(text: str) -> Piece:
    """Build a Piece from the text of its markdown file. Missing fields fall back to empty values."""
    fields, rest = parse_frontmatter(text)
    body, history = _body_and_changelog(rest)
    projects = fields.get("projects") or []
    if not isinstance(projects, list):
        projects = [projects]
    origin = fields.get("origin")
    return Piece(
        id=fields.get("id", ""),
        title=fields.get("title", ""),
        when=fields.get("when", ""),
        body=body,
        projects=projects,
        created=fields.get("created", ""),
        last_used=fields.get("last_used", ""),
        origin=origin if isinstance(origin, dict) else {},
        version=int(fields.get("version") or 1),
        history=history,
    )


def _origin_lines(origin: dict) -> list[str]:
    lines = [f"  {key}: {_quote(str(value))}" for key, value in origin.items()]
    return lines or ["  platform: unknown"]


def render(p: Piece) -> str:
    """The markdown file for a piece: frontmatter, body, then its history (the inverse of `parse`)."""
    header = [
        "---",
        f"id: {p.id}",
        f"title: {_quote(p.title)}",
        f"when: {_quote(p.when)}",
        "projects: [" + ", ".join(p.projects) + "]",
        f"created: {p.created}",
        f"last_used: {p.last_used}",
        "origin:",
        *_origin_lines(p.origin),
        f"version: {p.version}",
        "---",
    ]
    tail = ["", p.body.rstrip(), "", HISTORY_HEADING, *("- " + entry for entry in p.history)]
    return "\n".join(header + tail) + "\n"


# ---------------------------------------------------------------------------------------------------- the store
def _piece_files(folder: Path) -> list[Path]:
    return [f for f in sorted(folder.glob("*.md")) if f.name != INDEX_NAME]


def all_pieces() -> list[Piece]:
    """Every piece in the store, ordered by filename."""
    folder = paths.know_how()
    files = _piece_files(folder) if folder.is_dir() else []
    return [parse(f.read_text()) for f in files]


def get(piece_id: str) -> Piece | None:
    """The piece with this id, or None when there is no such file."""
    target = _file_for(piece_id)
    if not target.is_file():
        return None
    return parse(target.read_text())


def _write(p: Piece) -> None:
    """Store a piece in its file as is (no archiving, no version bump)."""
    target = p.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(p))


def _archive(p: Piece) -> Path:
    """Copy the file of `p`, as it is now, to `.history/<id>/v<version>.md`; returns the piece's archive folder."""
    folder = paths.history() / p.id
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p.path, folder / f"v{p.version}.md")
    return folder


def _where(origin: dict) -> str:
    """`platform, model` of an origin, each "unknown" when missing."""
    return ", ".join(str(origin.get(part, "unknown")) for part in ("platform", "model"))


def _history_entry(version: int, origin: dict, what: str) -> str:
    return f"v{version} {today()} ({_where(origin)}): {what}"


def _free_id(wanted: str) -> str:
    """`wanted`, or `wanted-2`, `wanted-3`... whichever is the first id not taken yet."""
    candidate, suffix = wanted, 2
    while _file_for(candidate).exists():
        candidate = f"{wanted}-{suffix}"
        suffix += 1
    return candidate


def _require(piece_id: str) -> Piece:
    found = get(piece_id)
    if found is None:
        raise KeyError(piece_id)
    return found


def create(title: str, when: str, body: str, projects: list[str] | None = None, origin: dict | None = None,
           piece_id: str | None = None) -> Piece:
    """Add a new piece at version 1. The id comes from `piece_id` (or the title) and never reuses an existing one."""
    origin = origin or dict(_UNKNOWN_ORIGIN)
    date = today()
    piece = Piece(id=_free_id(slugify(piece_id or title)), title=title, when=when, body=body,
                  projects=projects or [], created=date, last_used=date, origin=origin, version=1,
                  history=[_history_entry(1, origin, "created")])
    _write(piece)
    return piece


def update(piece_id: str, note: str, body: str | None = None, title: str | None = None, when: str | None = None,
           origin: dict | None = None, projects: list[str] | None = None) -> tuple[Piece, str]:
    """Write an improved version of a piece and return it with a unified diff against the previous one.

    The previous file is archived first; the version goes up by one and `note` becomes the newest history entry.
    Fields left as None keep their current value, and `projects` is added to the ones the piece already has."""
    current = _require(piece_id)
    _archive(current)
    origin = origin or current.origin
    version = current.version + 1
    improved = Piece(
        id=current.id,
        title=title or current.title,
        when=when or current.when,
        body=current.body if body is None else body,
        projects=sorted(set(current.projects).union(projects or [])),
        created=current.created,
        last_used=today(),
        origin=origin,
        version=version,
        history=[_history_entry(version, origin, note.strip() or "updated"), *current.history],
    )
    _write(improved)
    diff = difflib.unified_diff(render(current).splitlines(True), render(improved).splitlines(True),
                                f"{current.id} v{current.version}", f"{current.id} v{version}")
    return improved, "".join(diff)


def revert(piece_id: str, to: int | None = None) -> Piece:
    """Bring back an archived version (by default the one just before the current one) as a brand-new version.

    Nothing is removed: the version being replaced goes to the archive as well, so the revert itself can be undone.
    Raises KeyError for an unknown piece and FileNotFoundError when the requested version is not available."""
    current = _require(piece_id)
    target = current.version - 1 if to is None else int(to)
    source = paths.history() / piece_id / f"v{target}.md"
    if not (1 <= target < current.version and source.is_file()):
        raise FileNotFoundError(f"no version {target} of {piece_id} to go back to")
    _archive(current)
    restored = parse(source.read_text())
    restored.id = current.id
    restored.version = current.version + 1
    restored.history = [f"v{restored.version} {today()}: reverted to v{target}", *current.history]
    _write(restored)
    return restored


def touch(piece_id: str) -> None:
    """Mark a piece as used today. This only moves `last_used`; it is not a new version."""
    piece = get(piece_id)
    if piece is None or piece.last_used == today():
        return
    piece.last_used = today()
    _write(piece)


def export(dest: Path) -> int:
    """Copy the know-how folder, archive included, into `dest` and return the number of pieces copied."""
    source = paths.know_how()
    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)
    present = source.is_dir()
    if present:
        shutil.copytree(source, target, dirs_exist_ok=True)
    return len(_piece_files(source)) if present else 0
