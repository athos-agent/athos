"""Where Athos keeps the user's know-how. Everything lives under one folder the user owns (default `~/.athos`,
overridable with `ATHOS_HOME`), never inside the plugin, so it survives updates and uninstalls."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("ATHOS_HOME") or Path.home() / ".athos")


def know_how() -> Path:
    return home() / "know-how"


def history() -> Path:
    return know_how() / ".history"


def selection_file() -> Path:
    return home() / "selection.json"


def sessions() -> Path:
    return home() / "sessions"


def events_file() -> Path:
    return home() / "events.jsonl"


def project_of(cwd: str | Path | None = None) -> str:
    """The project a directory belongs to: the git repository's folder name, or the directory's own name."""
    cwd = Path(cwd or os.getcwd())
    try:
        top = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    return Path(top).name if top else cwd.name
