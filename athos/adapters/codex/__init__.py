"""Codex: the same know-how, with no second store.

Two ways in, both reading the one store under `~/.athos`:

    athos codex install     adds Athos's hooks to Codex's hooks.json, so Codex gets the index at session start, the
                            matching pieces on each request, the capture at the end, and the evaluation records
                            (platform = codex). Codex asks the user to trust new hooks once, with /hooks.
    athos export --codex    writes each piece as a Codex skill (`~/.agents/skills/athos-<id>/SKILL.md`), which Codex
                            loads only when a request matches its description. A translation: nothing is lost, and
                            the store stays the only source.

Codex's session log ("rollout") keeps cumulative token counts; a task's tokens are the difference between the counts
at its end and at its start.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path

from athos import paths, store

EVENTS = {"SessionStart": "session-start", "UserPromptSubmit": "prompt", "PostToolUse": "tool", "Stop": "stop"}
MARK = "athos hook"
SKILL_PREFIX = "athos-"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def skills_dir() -> Path:
    return Path.home() / ".agents" / "skills"


# ------------------------------------------------------------------------------------------------ hooks
def shim_path() -> Path:
    return paths.home() / "bin" / "athos"


def write_shim(root: Path) -> Path:
    """A stable entry point for Codex's hooks: the plugin's own folder changes with every update, so the shim finds the
    newest installed Athos at run time and falls back to the copy that ran `athos codex install`."""
    shim = shim_path()
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text(f'''#!/usr/bin/env python3
"""Runs the newest installed Athos. Written by `athos codex install`."""
import glob, os, sys
cands = sorted(glob.glob(os.path.expanduser("~/.claude/plugins/cache/athos/athos/*/bin/athos")),
               key=lambda p: [int(x) if x.isdigit() else x for x in p.split("/")[-3].replace("-", ".").split(".")])
target = os.environ.get("ATHOS_ROOT") and os.path.join(os.environ["ATHOS_ROOT"], "bin", "athos")
target = target or (cands[-1] if cands else {str(root / "bin" / "athos")!r})
sys.argv[0] = target
sys.path.insert(0, os.path.dirname(os.path.dirname(target)))
from athos.cli import main
sys.exit(main())
''')
    shim.chmod(0o755)
    return shim


def _is_ours(handler: dict) -> bool:
    return MARK in str(handler.get("command", "")) and "--platform codex" in str(handler.get("command", ""))


def install(root: Path, hooks_file: Path | None = None) -> tuple[Path, Path | None]:
    """Add Athos's hooks to Codex's hooks.json, keeping every other hook. Idempotent. Returns the file and the backup
    made of the previous one (None when there was no file)."""
    hooks_file = hooks_file or codex_home() / "hooks.json"
    shim = write_shim(root)
    data, backup = {}, None
    if hooks_file.is_file():
        data = json.loads(hooks_file.read_text() or "{}")
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = hooks_file.with_name(f"hooks.json.bak-{stamp}")
        shutil.copy2(hooks_file, backup)
    data = _without_ours(data)
    hooks = data.setdefault("hooks", {})
    for event, name in EVENTS.items():
        hooks.setdefault(event, []).append(
            {"hooks": [{"type": "command", "command": f"python3 {shim} hook {name} --platform codex"}]})
    hooks_file.parent.mkdir(parents=True, exist_ok=True)
    hooks_file.write_text(json.dumps(data, indent=2) + "\n")
    return hooks_file, backup


def _without_ours(data: dict) -> dict:
    hooks = data.get("hooks", {})
    for event in list(hooks):
        groups = []
        for g in hooks[event]:
            kept = [h for h in g.get("hooks", []) if not _is_ours(h)]
            if kept:
                groups.append({**g, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    return data


def uninstall(hooks_file: Path | None = None) -> bool:
    hooks_file = hooks_file or codex_home() / "hooks.json"
    if not hooks_file.is_file():
        return False
    data = json.loads(hooks_file.read_text() or "{}")
    hooks_file.write_text(json.dumps(_without_ours(data), indent=2) + "\n")
    return True


# ------------------------------------------------------------------------------------------------ skills
def skill_text(p: store.Piece) -> str:
    """One piece as a Codex skill. The description is what Codex matches requests against: the title and when the
    piece applies. The body keeps the whole piece, frontmatter fields and history included."""
    desc = f"{p.title}. Use when: {p.when}".replace("\n", " ")
    return (f"---\nname: {SKILL_PREFIX}{p.id}\ndescription: {store._quote(desc)}\n---\n\n"
            f"<!-- Generated by `athos export --codex` from {p.path}. Edit the piece, not this file. -->\n\n"
            + store.render(p))


def export_skills(dest: Path | None = None) -> tuple[int, int]:
    """Write every piece as a skill and remove skills of pieces that no longer exist. Returns (written, removed)."""
    dest = dest or skills_dir()
    dest.mkdir(parents=True, exist_ok=True)
    pieces = store.all_pieces()
    keep = {f"{SKILL_PREFIX}{p.id}" for p in pieces}
    for p in pieces:
        d = dest / f"{SKILL_PREFIX}{p.id}"
        d.mkdir(exist_ok=True)
        (d / "SKILL.md").write_text(skill_text(p))
    removed = 0
    for d in dest.glob(f"{SKILL_PREFIX}*"):
        if d.is_dir() and d.name not in keep and (d / "SKILL.md").is_file() \
                and "athos export --codex" in (d / "SKILL.md").read_text():
            shutil.rmtree(d)
            removed += 1
    return len(pieces), removed


# ------------------------------------------------------------------------------------------------ tokens
def _open_rollout(path: str):
    if path.endswith(".zst") or (not os.path.exists(path) and os.path.exists(path + ".zst")):
        from compression import zstd
        return zstd.open(path if path.endswith(".zst") else path + ".zst", "rt", errors="ignore")
    return open(path, errors="ignore")


def _parse_ts(ts: str):
    try:
        return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def tokens_between(rollout: str | None, start: str, end: str) -> dict | None:
    """Tokens Codex used between two times: the cumulative counts at the last report before `end`, minus those at the
    last report before `start`. None when the log cannot be read or holds no report in the window."""
    if not rollout:
        return None
    t0, t1 = _parse_ts(start), _parse_ts(end)
    before, last = None, None
    try:
        fh = _open_rollout(rollout)
    except (OSError, ImportError):
        return None
    with fh:
        for line in fh:
            if '"token_count"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get("payload") or {}
            usage = ((p.get("info") or {}).get("total_token_usage")) if p.get("type") == "token_count" else None
            ts = _parse_ts(o.get("timestamp", ""))
            if not usage or ts is None:
                continue
            if t0 and ts < t0:
                before = usage
            elif not t1 or ts <= t1:
                last = usage
    if last is None:
        return None
    b = before or {}

    def d(k):
        return int(last.get(k) or 0) - int(b.get(k) or 0)
    cached = d("cached_input_tokens")
    out = {"input": d("input_tokens") - cached, "output": d("output_tokens"), "cache_read": cached,
           "cache_write": d("cache_write_input_tokens")}
    out["total"] = d("total_tokens") or sum(out.values())
    return out
