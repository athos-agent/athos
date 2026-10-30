"""OpenCode: the same know-how, through an OpenCode plugin.

    athos opencode install     writes the plugin to ~/.config/opencode/plugins/athos.js (OpenCode loads it at start)
                               and Athos's sidebar to ~/.config/opencode/athos-sidebar/, listed in tui.json
    athos opencode uninstall   removes both

The plugin (`opencode/athos.js` in this repo) hands each OpenCode moment to the same `athos hook` Claude Code uses, as
platform `opencode`: the index of your know-how at a session's first message, the pieces that match each message in the
system prompt, tool calls counted, and the task recorded when the session goes idle, with OpenCode's own token counts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "opencode" / "athos.js"
# The sidebar ships compiled (OpenCode loads plugins without Solid's JSX transform): opencode/build-sidebar.mjs.
SIDEBAR = Path(__file__).resolve().parents[3] / "opencode" / "athos-sidebar.js"


def plugins_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opencode" / "plugins"


def _quoted(athos_cmd: Path) -> str:
    return str(athos_cmd).replace("\\", "\\\\").replace('"', '\\"')


def sidebar_dir() -> Path:
    # Beside plugins/, not in it: OpenCode's plugin discovery walks plugins/ and would load the sidebar as a server
    # plugin too. A TUI plugin is listed in tui.json instead.
    return plugins_dir().parent / "athos-sidebar"


def _tui_plugins(change) -> None:
    f = plugins_dir().parent / "tui.json"
    try:
        cfg = json.loads(f.read_text()) if f.exists() else {}
    except ValueError:
        return                                       # a tui.json we can't read is the person's: leave it
    entry = sidebar_dir().as_uri()
    plugins = [p for p in cfg.get("plugin", []) if p != entry]
    cfg["plugin"] = change(plugins, entry)
    if not cfg["plugin"]:
        cfg.pop("plugin")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cfg, indent=2) + "\n")


def install(athos_cmd: Path) -> Path:
    """Writes the plugin with the path of this athos command, so OpenCode finds it without PATH, and Athos's sidebar
    (the trail: the way of working followed, its steps ticked) as a TUI plugin listed in tui.json."""
    target = plugins_dir() / "athos.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SOURCE.read_text().replace("__ATHOS__", _quoted(athos_cmd)))
    if SIDEBAR.exists():
        d = sidebar_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.js").write_text(SIDEBAR.read_text().replace("__ATHOS__", _quoted(athos_cmd)))
        (d / "package.json").write_text(json.dumps({"name": "athos-sidebar", "type": "module", "main": "./index.js",
                                                     "peerDependencies": {"@opentui/solid": ">=0.5.8",
                                                                          "solid-js": ">=1.9.0"}}, indent=2) + "\n")
        _tui_plugins(lambda plugins, entry: plugins + [entry])
    return target


def uninstall() -> bool:
    target = plugins_dir() / "athos.js"
    found = target.exists()
    if found:
        target.unlink()
    d = sidebar_dir()
    if d.exists():
        for f in d.iterdir():
            f.unlink()
        d.rmdir()
        found = True
    _tui_plugins(lambda plugins, entry: plugins)
    return found
