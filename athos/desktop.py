"""`athos desktop`: Athos as a Claude Desktop extension (.mcpb), installed with a double click. It runs `athos mcp`
from the bundle against the person's own ~/.athos, so the regular chat gets the know-how and the trail panel without
editing claude_desktop_config.json."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    from athos import mcp
    version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    return {
        "manifest_version": "0.3",
        "name": "athos",
        "display_name": "Athos",
        "version": version,
        "description": "Your AI know-how. Free to move, fast to run.",
        "long_description": "Athos keeps how you work with AI as plain markdown you own (~/.athos), finds the part of "
                            "it each request needs, and shows the task's walk through it, step by step, in a panel "
                            "in the chat. Nothing leaves your machine.",
        "author": {"name": "Matías Molinas"},
        "repository": {"type": "git", "url": "https://github.com/athos-agent/athos"},
        "homepage": "https://github.com/athos-agent/athos",
        "license": "Apache-2.0",
        "server": {"type": "python", "entry_point": "bin/athos",
                   "mcp_config": {"command": "python3", "args": ["${__dirname}/bin/athos", "mcp"]}},
        "tools": [{"name": t["name"], "description": t["description"]} for t in mcp.TOOLS
                  if t["name"] != "athos_trail"],                      # the panel's own tool, not the model's
        "compatibility": {"platforms": ["darwin", "linux"], "runtimes": {"python": ">=3.9"}},
    }


def pack(dest: Path) -> Path:
    """The bundle: the manifest, the `athos` command and the package, no caches."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(), ensure_ascii=False, indent=2) + "\n")
        z.write(ROOT / "bin" / "athos", "bin/athos")
        for f in ["LICENSE", "NOTICE"]:
            if (ROOT / f).exists():
                z.write(ROOT / f, f)
        for f in sorted((ROOT / "athos").rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                z.write(f, str(f.relative_to(ROOT)))
    return dest
