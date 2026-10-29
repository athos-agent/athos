"""OpenCode: the same know-how, through an OpenCode plugin.

    athos opencode install     writes the plugin to ~/.config/opencode/plugins/athos.js (OpenCode loads it at start)
    athos opencode uninstall   removes it

The plugin (`opencode/athos.js` in this repo) hands each OpenCode moment to the same `athos hook` Claude Code uses, as
platform `opencode`: the index of your know-how at a session's first message, the pieces that match each message in the
system prompt, tool calls counted, and the task recorded when the session goes idle, with OpenCode's own token counts.
"""

from __future__ import annotations

import os
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "opencode" / "athos.js"


def plugins_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opencode" / "plugins"


def install(athos_cmd: Path) -> Path:
    """Writes the plugin with the path of this athos command, so OpenCode finds it without PATH."""
    target = plugins_dir() / "athos.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SOURCE.read_text().replace("__ATHOS__", str(athos_cmd).replace("\\", "\\\\").replace('"', '\\"')))
    return target


def uninstall() -> bool:
    target = plugins_dir() / "athos.js"
    if target.exists():
        target.unlink()
        return True
    return False
