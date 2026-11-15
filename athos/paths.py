"""Locations of everything Athos stores for the user.

All of it sits in a single folder that belongs to the user: `~/.athos` unless `ATHOS_HOME` names another one. The
plugin folder never holds user data, so reinstalling or removing the plugin cannot lose any know-how.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_DEFAULT_DIRNAME = ".athos"
_GIT_FAILURES = (OSError, subprocess.SubprocessError)    # the command is missing, hung, or could not start


def home() -> Path:
    """The root of the user's Athos folder (`ATHOS_HOME` when set and non-empty)."""
    override = os.environ.get("ATHOS_HOME")
    if override:
        return Path(override)
    return Path.home() / _DEFAULT_DIRNAME


def _under_home(*parts: str) -> Path:
    return home().joinpath(*parts)


def know_how() -> Path:
    """Folder with one markdown file per piece of know-how."""
    return _under_home("know-how")


def history() -> Path:
    """Archive of earlier versions, kept inside the know-how folder."""
    return know_how().joinpath(".history")


def selection_file() -> Path:
    return _under_home("selection.json")


def sessions() -> Path:
    """Per-session state files (see `athos.session`)."""
    return _under_home("sessions")


def import_since() -> str | None:
    """When this store started taking other agents' past sessions (ISO time in `<home>/import-since`), if it was set.
    A new store takes all of them; a demo sets it so earlier rehearsals stay out."""
    try:
        return (home() / "import-since").read_text().strip() or None
    except OSError:
        return None


def events_file() -> Path:
    """Append-only log of what Athos did, one JSON object per line."""
    return _under_home("events.jsonl")


def _git_toplevel(folder: Path) -> str:
    """Root of the git work tree containing `folder`, or "" when there is none (or git is unavailable)."""
    cmd = ["git", "-C", str(folder), "rev-parse", "--show-toplevel"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except _GIT_FAILURES:
        return ""
    return done.stdout.strip()


MARKER = ".athos.toml"


def profile_file() -> Path:
    """The ids of the pieces that apply in every project (`athos profile`)."""
    return _under_home("profile.json")


def _root(folder: Path) -> Path:
    """The repository a folder is part of (its git top folder), or the folder itself outside any repository."""
    top = _git_toplevel(folder)
    return Path(top) if top else folder


def _read_marker(root: Path) -> dict:
    """`.athos.toml` at a repository's root, as written: `name = "<project>"` and `public = true|false`. Anything
    missing, unreadable or of the wrong type is left out, so a broken marker never stops a hook."""
    import tomllib
    try:
        data = tomllib.loads((root / MARKER).read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}
    out: dict = {"file": str(root / MARKER)}
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        out["name"] = name.strip()
    if isinstance(data.get("public"), bool):
        out["public"] = data["public"]
    return out


def marker(cwd: str | Path | None = None) -> dict:
    """The project marker of the repository a folder is part of: `{"file", "name"?, "public"?}`, or {} when there is
    none. It gives the project a stable name (a clone in a folder of another name is still the same project) and
    says whether the repository is public: then no private piece loads or is named there, and nothing taken from a
    request is stored."""
    folder = Path(cwd) if cwd else Path(os.getcwd())
    return _read_marker(_root(folder))


def locate(cwd: str | Path) -> tuple[str, dict]:
    """`project_of` and `marker` together, with one look for the repository."""
    root = _root(Path(cwd))
    mark = _read_marker(root)
    return mark.get("name") or root.name, mark


def is_public(cwd: str | Path | None) -> bool:
    """Whether a folder belongs to a repository whose marker says `public = true`. No folder: False."""
    return bool(cwd) and marker(cwd).get("public") is True


def project_of(cwd: str | Path | None = None) -> str:
    """Name used for the project a folder is part of.

    The `name` of the repository's `.athos.toml` when it has one; else, inside a git work tree, the name of the
    repository's top folder; anywhere else, the folder's own name. With no argument the folder the process runs in
    is used."""
    folder = Path(cwd) if cwd else Path(os.getcwd())
    root = _root(folder)
    return _read_marker(root).get("name") or root.name
