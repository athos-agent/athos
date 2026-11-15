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


class _MarkerSyntax(ValueError):
    """A marker line Athos cannot read."""


def _toml_value(raw: str):
    """One TOML value of the kinds a marker holds: a basic or literal string, or true/false; a trailing comment is
    dropped. _MarkerSyntax for anything else."""
    import json
    import re
    raw = raw.strip()
    m = re.match(r'^("(?:[^"\\]|\\.)*")\s*(?:#.*)?$', raw)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError as bad:
            raise _MarkerSyntax(raw) from bad
    m = re.match(r"^'([^']*)'\s*(?:#.*)?$", raw)
    if m:
        return m.group(1)
    m = re.match(r"^(true|false)\s*(?:#.*)?$", raw)
    if m:
        return m.group(1) == "true"
    raise _MarkerSyntax(raw)


def _loads_marker(text: str) -> dict:
    """The top-level `name` and `public` of a marker. With tomllib (Python 3.11+) the whole file is parsed; without
    it (the hooks may run under an older `python3`) only the lines before the first table, and only those two keys
    are read. _MarkerSyntax when the file is not valid TOML (or, without tomllib, one of those two lines is not)."""
    try:
        import tomllib
    except ImportError:
        tomllib = None
    if tomllib is not None:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as bad:
            raise _MarkerSyntax(str(bad)) from bad
    import re
    out: dict = {}
    for line in text.splitlines():
        if re.match(r"^\s*\[", line):
            break                                   # a table: its keys are not the marker's
        m = re.match(r"^\s*(name|public)\s*=(.*)$", line)
        if m:
            out[m.group(1)] = _toml_value(m.group(2))
    return out


def _read_marker(root: Path) -> dict:
    """`.athos.toml` at a repository's root, as written: `name = "<project>"` and `public = true|false`. Anything
    missing, unreadable or of the wrong type is left out, so a broken marker never stops a hook."""
    try:
        data = _loads_marker((root / MARKER).read_text())
    except (OSError, UnicodeDecodeError, _MarkerSyntax):
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


# Sites that host code: a repository with a remote on one of them may be public, and only the person can say.
CODE_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht", "gitea.com", "dev.azure.com",
              "ssh.dev.azure.com", "vs-ssh.visualstudio.com", "sourceforge.net", "huggingface.co")


def repo_root(cwd: str | Path | None = None) -> Path:
    """The root of the repository a folder is part of (its git top folder), or the folder itself outside any."""
    return _root(Path(cwd) if cwd else Path(os.getcwd()))


def _host_of(url: str) -> str:
    """The host of a git remote URL: https://host/…, ssh://user@host:port/…, user@host:path."""
    import re
    if "://" in url:
        m = re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]*@)?([^/:]+)", url, re.I)
    else:
        m = re.match(r"^(?:[^@/]+@)?([^/:]{2,}):", url)      # scp-like; "C:" on Windows is a drive, not a host
    return m.group(1).lower() if m else ""


def code_remotes(cwd: str | Path | None = None) -> list[str]:
    """The code-hosting sites (CODE_HOSTS, or a host named like one) the repository's remotes point at, read from the
    repository's own git configuration only: no network call, so it says where the code is pushed, never whether
    that copy is public."""
    folder = repo_root(cwd)
    cmd = ["git", "-C", str(folder), "config", "--get-regexp", r"^remote\..*\.(url|pushurl)$"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except _GIT_FAILURES:
        return []
    hosts = []
    for line in done.stdout.splitlines():
        host = _host_of(line.split(None, 1)[1].strip()) if " " in line else ""
        known = host in CODE_HOSTS or host.startswith(("github.", "gitlab.", "bitbucket.", "gitea.", "forgejo."))
        if known and host not in hosts:
            hosts.append(host)
    return hosts


def write_marker(cwd: str | Path | None, public: bool) -> tuple[Path, dict]:
    """Write `public = true|false` into the `.athos.toml` at the repository's root, creating it with the project's
    name when there is none, and keeping every other line of one that exists. Returns the file and the marker as it
    now reads."""
    import json
    root = repo_root(cwd)
    target = root / MARKER
    value = "true" if public else "false"
    try:
        lines = target.read_text().splitlines()
    except OSError:
        lines = []
    if not lines:
        lines = ["# Athos: this project's name, and whether the repository is public. In a public repository Athos",
                 "# loads and names only this project's own ways of working.",
                 f"name = {json.dumps(project_of(root), ensure_ascii=False)}", f"public = {value}"]
    else:
        import re
        at = [i for i, line in enumerate(lines) if re.match(r"^\s*public\s*=", line)]
        if at:
            lines[at[0]] = f"public = {value}"
        else:
            lines.append(f"public = {value}")
        if not any(re.match(r"^\s*name\s*=", line) for line in lines):
            lines.insert(0, f"name = {json.dumps(project_of(root), ensure_ascii=False)}")
    target.write_text("\n".join(lines) + "\n")
    return target, _read_marker(root)
