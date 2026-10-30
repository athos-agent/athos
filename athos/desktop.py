"""`athos desktop`: Athos as a Claude Desktop extension (.mcpb), installed with a double click. It runs `athos mcp`
from the bundle against the person's own ~/.athos, so the regular chat gets the know-how and the trail panel without
editing claude_desktop_config.json."""

from __future__ import annotations

import json
import re
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


# ------------------------------------------------------------------------------------------------ the skill
# Claude Desktop's chat keeps connector tools out of sight until the model searches for one, and a request like
# "revisá este contrato" makes it search for nothing (2026-10-30: Athos was connected and never called). Skills are
# listed in every conversation by name and description, so a skill that names the person's tasks brings Athos in.
SKILL_NAME = "athos-know-how"
DESCRIPTION_LIMIT = 1024
DANGLING = set("a an the of for to in into on with and or by from its their your my "
               "el la los las un una de del al con en y o por para según sin su sus tu tus mi mis".split())


def skill_description(pieces) -> str:
    """What makes Claude load the skill: the person's own tasks, most recently used first, as many as fit."""
    head = ("The person's own ways of working, kept by Athos. Use it first, before answering, whenever the request is "
            "one of their tasks: ")
    tail = ". Also for any task of several steps they may have taught before."
    names: list[str] = []
    for p in sorted(pieces, key=lambda p: p.last_used or p.created or "", reverse=True):
        # Short titles fit more tasks: no parentheses, at most a few words.
        t = re.sub(r"\s*«[^»]*»", "", re.sub(r"\s*\([^)]*\)", "", p.title)).strip().rstrip(".")
        if len(t) > 48:
            words = t[:t.rfind(" ", 0, 48)].split()
            while words and words[-1].lower() in DANGLING:     # never end on "for a", "según el", "con mis"
                words.pop()
            t = " ".join(words)
        if t in names:
            continue
        if len(head) + len("; ".join(names + [t])) + len(tail) > DESCRIPTION_LIMIT:
            continue
        names.append(t)
    return head + "; ".join(names) + tail


def skill_text(pieces) -> str:
    desc = skill_description(pieces).replace('"', "'")
    return f'''---
name: {SKILL_NAME}
description: "{desc}"
---

# The person's ways of working (Athos)

The person keeps how they like each kind of task done (their steps, criteria and checklists) in Athos, on their own
computer. Athos is connected to this chat as the **Athos** connector.

1. Before answering, call the Athos tool `athos_find` with the person's request, in their words. If the tool is not
   loaded yet, search the tools for "athos". It returns the person's way of working for this request and opens a
   panel where they watch the task, step by step.
2. Follow what it returns, and do exactly what its result asks: report each step with `athos_step` as you apply it,
   and answer the way it says.
3. If Athos finds nothing, or is not connected, answer as you would, and say nothing about Athos.
'''


def pack_skill(dest: Path) -> Path:
    """The skill as a .zip to upload once in Claude Desktop (Customize → Skills); built again when the know-how grows."""
    from athos import store
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{SKILL_NAME}/SKILL.md", skill_text(store.all_pieces()))
    return dest
