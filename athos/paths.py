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


def _dot_git(folder: Path) -> tuple[Path | None, Path | None]:
    """Without running git: the nearest folder at or above `folder` that holds a `.git` (a folder, or the file a
    worktree or a submodule has instead), and, for a worktree, the main worktree it belongs to (read from the
    `gitdir:` line of its `.git` file: `<main>/.git/worktrees/<name>`)."""
    for d in (folder, *folder.parents):
        dot = d / ".git"
        if dot.is_dir():
            return d, None
        if dot.is_file():
            return d, _main_worktree(dot)
    return None, None


def _main_worktree(dot_git_file: Path) -> Path | None:
    try:
        line = dot_git_file.read_text(errors="ignore").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = Path(line[len("gitdir:"):].strip())
    if not gitdir.is_absolute():
        gitdir = dot_git_file.parent / gitdir
    gitdir = Path(os.path.normpath(gitdir))
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent
    return None                                          # a submodule, or a bare repository's worktree


def _top(folder: Path) -> tuple[Path | None, Path | None]:
    """The repository's top folder (git's answer, or, when git cannot run, the nearest `.git` above) and, in a
    worktree, its main worktree."""
    found = _git_toplevel(folder)
    if found:
        top = Path(found)
        dot = top / ".git"
        return top, (_main_worktree(dot) if dot.is_file() else None)
    return _dot_git(folder)


def _root(folder: Path) -> Path:
    """The repository a folder is part of (its git top folder), or the folder itself outside any repository."""
    return _scan(folder)["root"]


def _scan(folder: Path) -> dict:
    """Where a folder's project stands, failing closed: `root` (the folder that names the project), `mark` (the marker
    that speaks for it) and `public`.

    The marker is looked for in the folder and every folder above it, without relying on git. The one that names the
    project is at the repository's top; in a worktree that has none of its own, the main worktree's; outside any
    repository, the nearest one (its folder is then the project's). Any marker on the way up that says public (or
    cannot be read) makes the folder public: declaring a repository public can only restrict, so an outer public
    repository's nested folders and repositories are public too."""
    folder = Path(os.path.realpath(folder))          # git answers with real paths (/private/var, not /var)
    top, main = _top(folder)
    top = Path(os.path.realpath(top)) if top is not None else None
    main = Path(os.path.realpath(main)) if main is not None else None
    found = [(d, _read_marker(d)) for d in (folder, *folder.parents) if (d / MARKER).is_file()]
    if main is not None and (main / MARKER).is_file() and all(d != main for d, _ in found):
        found.append((main, _read_marker(main)))
    if top is not None:
        root = top
        own = next(((d, m) for d, m in found if d == top), None) or \
            next(((d, m) for d, m in found if main is not None and d == main), None)
    else:
        own = found[0] if found else None
        root = own[0] if own else folder
    mark = dict(own[1]) if own else {}
    if own:
        mark["at"] = str(own[0])
        if mark.get("name") and mark["name"] != own[0].name and accepted_name(own[0]) != mark["name"]:
            # Whoever wrote the repository wrote its marker: a clone could name itself after one of the person's
            # projects and get its pieces. A name other than the folder's own counts once the person accepted it.
            mark["name_ignored"] = mark.pop("name")
    loud = next(((d, m) for d, m in found if m.get("public") is True), None)
    if loud is not None:
        mark["public"] = True
        if not own or loud[0] != own[0]:
            mark["public_from"] = str(loud[0] / MARKER)
            mark.setdefault("file", str(loud[0] / MARKER))
    return {"root": root, "mark": mark, "named_at": own[0] if own else None}


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
    """`.athos.toml` in a folder, as written: `name = "<project>"` and `public = true|false`. A marker that is there
    but cannot be read (not valid TOML, not text, unreadable), or whose `public` is not true or false, reads as
    public, with `unreadable`: a repository someone tried to declare is taken at its most restrictive. A hook never
    stops on it."""
    target = root / MARKER
    out: dict = {"file": str(target)}
    try:
        data = _loads_marker(target.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, _MarkerSyntax):
        return {**out, "public": True, "unreadable": True}
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        out["name"] = name.strip()
    if "public" in data:
        if isinstance(data["public"], bool):
            out["public"] = data["public"]
        else:
            out.update(public=True, unreadable=True)
    return out


def write_atomic(target: Path, text: str) -> None:
    """Replace a file's content in one step: written to a temporary file beside it, then moved over it, so a reader
    sees the old content or the new one, never half of either."""
    import tempfile
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def accepted_names_file() -> Path:
    """The marker names the person accepted on this machine, by repository folder (`athos public name`). It lives
    under the Athos home, never in a repository."""
    return _under_home("marker-names.json")


def _accepted() -> dict:
    import json
    try:
        data = json.loads(accepted_names_file().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def accepted_name(root: Path) -> str | None:
    """The marker name the person accepted for this repository folder, if any."""
    found = _accepted().get(os.path.realpath(root))
    return found if isinstance(found, str) else None


def accept_name(cwd: str | Path | None = None) -> tuple[Path, str]:
    """The person accepts the name the marker of this folder's repository gives it (`athos public name`): from now on
    Athos calls the project so on this machine. Returns the marker's folder and the name. ValueError when there is
    no marker, or it names nothing other than its folder."""
    import json
    scan = _scan(Path(cwd) if cwd else Path(os.getcwd()))
    name, at = scan["mark"].get("name_ignored"), scan.get("named_at")
    if not name or at is None:
        raise ValueError("there is no marker name to accept here: the project already goes by "
                         f"{_named(scan)!r}")
    data = _accepted()
    data[os.path.realpath(at)] = name
    write_atomic(accepted_names_file(), json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    return at, name


def _named(scan: dict) -> str:
    """The project's name: the marker's `name`, else the root folder's name."""
    return scan["mark"].get("name") or scan["root"].name


def marker(cwd: str | Path | None = None) -> dict:
    """The project marker of the repository a folder is part of: `{"file", "name"?, "public"?, "unreadable"?,
    "public_from"?}`, or {} when there is none (`_scan` says which marker speaks for a folder). It gives the project a
    stable name (a clone in a folder of another name is still the same project) and says whether the repository is
    public: then no private piece loads or is named there, and nothing taken from a request is stored."""
    return _scan(Path(cwd) if cwd else Path(os.getcwd()))["mark"]


def locate(cwd: str | Path) -> tuple[str, dict]:
    """`project_of` and `marker` together, with one look for the repository."""
    scan = _scan(Path(cwd))
    return _named(scan), scan["mark"]


def is_public(cwd: str | Path | None) -> bool:
    """Whether a folder belongs to a repository declared public (`marker`). No folder: False."""
    return bool(cwd) and marker(cwd).get("public") is True


def project_of(cwd: str | Path | None = None) -> str:
    """Name used for the project a folder is part of.

    The `name` of the repository's `.athos.toml` when it has one; else, inside a git work tree, the name of the
    repository's top folder; anywhere else, the folder holding the nearest marker, or the folder's own name. With no
    argument the folder the process runs in is used."""
    return _named(_scan(Path(cwd) if cwd else Path(os.getcwd())))


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
