"""Where pieces of know-how live on disk.

A piece is a plain markdown file, `<home>/know-how/<id>.md`, that a person can open and change by hand. It begins
with a frontmatter block between two `---` lines holding, in this order: `id`; `title`; `when` (the situation the
piece is for); `projects` as an inline list such as `[athos, docs]`; an optional `visibility` (`private`,
`project` or `general`, see `visibility`); the autonomous-learning fields, each written only when set (`status`:
`candidate`, `verified` or `retired`; `risk`: `normal` or `high`; `confidence`, a number from 0 to 1;
`last_verified`, a date; `learned_by`, the model that wrote it; `evidence`, an inline list of short `kind:detail`
items); the `created` and `last_used` dates; an
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
# Who may see a piece. `private`: only sessions in one of its projects, never in a repository marked public, and never
# named anywhere else (not in another project's index, log.md or hook output). `project`: its projects' sessions,
# and another project's when the request names one of them. `general`: may be named anywhere.
VISIBILITIES = ("private", "project", "general")
# Where a piece stands in autonomous learning (athos/grade.py). A piece with no status at all was written before it
# existed (or by the person): it is `legacy` and behaves as verified, so nothing that worked stops working.
STATUSES = ("candidate", "verified", "retired")
LEGACY = "legacy"
RISKS = ("normal", "high")


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
    visibility: str = ""                                     # as written; "" when the frontmatter has none
    status: str = ""                                         # candidate | verified | retired; "" = legacy
    risk: str = ""                                           # normal | high; "" = not classified yet
    confidence: str = ""                                     # as written, e.g. "0.6"; "" = none
    last_verified: str = ""                                  # YYYY-MM-DD
    learned_by: str = ""                                     # the model id that wrote it, for autonomous saves
    evidence: list[str] = field(default_factory=list)        # short `kind:detail` items, newest last

    @property
    def path(self) -> Path:
        return _file_for(self.id)


def visibility(p: Piece) -> str:
    """A piece's visibility: the one its frontmatter states, else `project` for a piece tagged with projects and
    `general` for an untagged one."""
    if p.visibility in VISIBILITIES:
        return p.visibility
    return "project" if p.projects else "general"


def private(p: Piece) -> bool:
    return visibility(p) == "private"


def status(p: Piece) -> str:
    """A piece's status: the one its frontmatter states, else `legacy` (a piece from before autonomous learning, or
    written by the person), which loads and behaves exactly as `verified`."""
    return p.status if p.status in STATUSES else LEGACY


def usable_as_verified(p: Piece) -> bool:
    """Verified, or legacy: what an apply model may be given."""
    return status(p) in ("verified", LEGACY)


def confidence(p: Piece) -> float | None:
    """The piece's confidence as a number in [0, 1], or None when it has none (legacy pieces)."""
    try:
        value = float(p.confidence)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, value))


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
        visibility=str(fields.get("visibility") or "").strip().lower(),
        status=str(fields.get("status") or "").strip().lower(),
        risk=str(fields.get("risk") or "").strip().lower(),
        confidence=str(fields.get("confidence") or "").strip(),
        last_verified=str(fields.get("last_verified") or "").strip(),
        learned_by=str(fields.get("learned_by") or "").strip(),
        evidence=_as_list(fields.get("evidence")),
    )


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


_LEARNING_KEYS = ("status", "risk", "confidence", "last_verified", "learned_by")


def _learning_lines(p: Piece) -> list[str]:
    """The autonomous-learning fields that are set, in a fixed order; none for a legacy piece, so its file is written
    back exactly as before."""
    lines = [f"{key}: {_quote(str(getattr(p, key)))}" for key in _LEARNING_KEYS if getattr(p, key)]
    if p.evidence:
        items = [re.sub(r"[,\[\]\n]", " ", e).strip() for e in p.evidence]
        lines.append("evidence: [" + ", ".join(i for i in items if i) + "]")
    return lines


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
        *([f"visibility: {p.visibility}"] if p.visibility else []),
        *_learning_lines(p),
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
    """Every piece in the store, ordered by filename, with what is kept beside the files (`_beside`)."""
    folder = paths.know_how()
    files = _piece_files(folder) if folder.is_dir() else []
    used, meta = _used(), _meta()
    return [_beside(parse(f.read_text()), used, meta) for f in files]


def get(piece_id: str) -> Piece | None:
    """The piece with this id, or None when there is no such file, with what is kept beside its file (`_beside`)."""
    target = _file_for(piece_id)
    if not target.is_file():
        return None
    return _beside(parse(target.read_text()), _used(), _meta())


def _beside(p: Piece, used: dict, meta: dict) -> Piece:
    """A piece as read, with what Athos keeps beside its file instead of in it: the last use (`last-used.json`, for
    every piece) and, for a learned piece, its bookkeeping (`piece-meta.json`: confidence, last verified, evidence).
    Using and grading a piece used to rewrite its file on every reuse: noise in a synced or git-tracked folder, and a
    lost update when the person's editor had it open. The file takes these values on its next real change."""
    day = used.get(p.id)
    if isinstance(day, str) and day > (p.last_used or ""):
        p.last_used = day
    if not legacy(p):
        for key, value in (meta.get(p.id) or {}).items():
            if key in _META_KEYS and value is not None:
                setattr(p, key, list(value) if key == "evidence" else str(value))
    return p


def _write(p: Piece) -> None:
    """Store a piece in its file as is (no archiving, no version bump), in one step: the file is replaced whole, so
    a hook, the verifier or the person's editor reading it at the same time sees the old piece or the new one. What
    was kept beside the file for it is in the file now, so it is cleared there."""
    paths.write_atomic(p.path, render(p))
    _clear_meta(p.id)


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
           piece_id: str | None = None, **learning) -> Piece:
    """Add a new piece at version 1. The id comes from `piece_id` (or the title) and never reuses an existing one.
    `learning` sets the autonomous-learning fields (status, risk, confidence, learned_by, evidence, visibility)."""
    origin = origin or dict(_UNKNOWN_ORIGIN)
    date = today()
    piece = Piece(id=_free_id(slugify(piece_id or title)), title=title, when=when, body=body,
                  projects=projects or [], created=date, last_used=date, origin=origin, version=1,
                  history=[_history_entry(1, origin, learning.pop("note", None) or "created")])
    for key, value in learning.items():
        if hasattr(piece, key) and value is not None:
            setattr(piece, key, value)
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
    retext = current.status == "verified" and ((title or current.title).strip() != current.title.strip()
                                               or (when or current.when).strip() != current.when.strip()
                                               or (current.body if body is None else body).strip()
                                               != current.body.strip())
    if retext:
        # Verified means verified for that text: a new title, when or body has not been checked by anyone yet.
        note = (note.strip() or "updated") + "; verified → candidate: the text changed since it was verified"
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
        visibility=current.visibility,
        **{key: getattr(current, key) for key in (*_LEARNING_KEYS, "evidence")},
    )
    if retext:
        improved.status = "candidate"
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
    # Who may see the piece is decided now, not by the version brought back: a `visibility: private` or a project
    # the person added by hand (which archives nothing) must survive a revert.
    restored.visibility = current.visibility
    restored.projects = list(current.projects)
    restored.version = current.version + 1
    restored.history = [f"v{restored.version} {today()}: reverted to v{target}", *current.history]
    if restored.status == "verified" and not _passed_for(restored):
        # The text brought back was verified as some other text, or never by the verifier: a candidate again.
        restored.status = "candidate"
        restored.history[0] += "; verified → candidate: no verifier passed this text"
    _write(restored)
    return restored


def _passed_for(p: Piece) -> bool:
    """Whether the verifier passed on this piece's exact text (its title, when and body)."""
    from athos import grade
    return grade.verifier_passed(p) is not None


def legacy(p: Piece) -> bool:
    """A piece with no status: the person's file (or one from before autonomous learning). Athos never rewrites it
    unless the person asks for a change to that piece (`update`, `revert`): using, grading, ageing and bookkeeping
    leave its file byte for byte as it is, and are recorded in events instead. A rewrite drops hand-written
    frontmatter keys and comments, and once demoted the person's pieces could never come back."""
    return status(p) == LEGACY


def set_status(piece_id: str, new: str, note: str, asked: bool = False) -> Piece | None:
    """Move a piece to another status as a new version: the outgoing file is archived first (so `athos revert` brings
    it back) and `note` says why in its history. Nothing is deleted: retiring a piece supersedes it. The last-used
    date is not moved; a status change is not a use. A legacy piece is left alone (None) unless the person `asked`."""
    if new not in STATUSES:
        raise ValueError(f"unknown status {new!r}")
    current = _require(piece_id)
    if legacy(current) and not asked:
        return None
    _archive(current)
    was = status(current)
    current.version += 1
    current.status = new
    current.history = [f"v{current.version} {today()} (athos, grade): {was} → {new}: {note.strip()}",
                       *current.history]
    _write(current)
    return current


_META_KEYS = ("confidence", "last_verified", "evidence", "risk", "learned_by")


def _meta_file() -> Path:
    return paths.home() / "piece-meta.json"


def _meta(strict: bool = False) -> dict:
    """What is kept beside learned pieces' files: {piece id: {field: value}}. One that cannot be read is {} to a
    reader and, with `strict` (before a change is written back), paths.StateUnreadable."""
    try:
        data = paths.read_state(_meta_file(), retries=2)
    except paths.StateUnreadable:
        if strict:
            raise
        return {}
    return data if isinstance(data, dict) else {}


def _clear_meta(piece_id: str) -> None:
    if piece_id not in _meta():
        return
    import json
    with paths.locked(_meta_file()):
        data = _meta(strict=True)
        if data.pop(piece_id, None) is not None:
            paths.write_atomic(_meta_file(), json.dumps(data, indent=1, sort_keys=True))


def set_meta(piece_id: str, **fields) -> Piece | None:
    """Change bookkeeping fields (confidence, last_verified, evidence, risk): not a new version, and not a write of the
    piece's file. They are kept beside it (`piece-meta.json`) and reach the file with its next status change or
    improvement. A legacy piece's bookkeeping is never kept at all. None for an unknown piece."""
    import json
    piece = get(piece_id)
    if piece is None or legacy(piece):
        return piece
    changes = {k: v for k, v in fields.items() if k in _META_KEYS and v is not None and getattr(piece, k) != v}
    if not changes:
        return piece
    with paths.locked(_meta_file()):
        data = _meta(strict=True)
        data[piece_id] = {**(data.get(piece_id) or {}), **changes}
        paths.write_atomic(_meta_file(), json.dumps(data, indent=1, sort_keys=True))
    for key, value in changes.items():
        setattr(piece, key, value)
    return piece


def _used_file() -> Path:
    return paths.home() / "last-used.json"


def _used() -> dict:
    try:
        data = paths.read_state(_used_file(), retries=2)
    except paths.StateUnreadable:
        return {}
    return data if isinstance(data, dict) else {}


def last_used(p: Piece) -> str:
    """When a piece was last used: the later of its file's `last_used` and the date `touch` recorded for it in
    `<home>/last-used.json`."""
    other = _used().get(p.id)
    return max(p.last_used or "", other) if isinstance(other, str) else (p.last_used or "")


def touch(piece_id: str) -> None:
    """Mark a piece as used today. This only moves its last-used date, kept in `<home>/last-used.json`: a use is
    not a change, so no piece's file is rewritten for it (a learned piece's file takes the date with its next real
    change)."""
    import json
    piece = get(piece_id)
    if piece is None or piece.last_used == today():
        return
    with paths.locked(_used_file()):
        used = _used()
        if used.get(piece_id) != today():
            used[piece_id] = today()
            paths.write_atomic(_used_file(), json.dumps(used, indent=1, sort_keys=True))


def export(dest: Path) -> int:
    """Copy the know-how folder, archive included, into `dest` and return the number of pieces copied."""
    source = paths.know_how()
    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)
    present = source.is_dir()
    if present:
        shutil.copytree(source, target, dirs_exist_ok=True)
    return len(_piece_files(source)) if present else 0
