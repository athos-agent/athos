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


# ------------------------------------------------------------------------------------------------ import
SKILL_USE = __import__("re").compile(r"athos-([a-z0-9][a-z0-9-]*)/SKILL\.md")
INJECTED = __import__("re").compile(r"<(environment_context|user_instructions|INSTRUCTIONS)>.*?</\1>", __import__("re").S)
HOOK_USE = __import__("re").compile(r"\(`([a-z0-9][a-z0-9-]*)`, v\d+\)")
TMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/")


def sessions_dir() -> Path:
    return codex_home() / "sessions"


def _rollout_tasks(path: Path) -> list[dict]:
    """The tasks of one Codex session: each turn from `task_started` to `task_complete`, with its model, request,
    duration and the Athos pieces it read (as skills, or as injected by the hooks)."""
    meta, model, tasks, cur, last_user = {}, "unknown", [], None, ""
    try:
        fh = _open_rollout(str(path))
    except (OSError, ImportError):
        return []
    with fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
            kind = (o.get("type"), p.get("type"))
            if kind[0] == "session_meta":
                meta = p
            elif kind[0] == "turn_context":
                model = p.get("model") or model
                if cur is not None:
                    cur["model"] = model
            elif kind == ("response_item", "message") and p.get("role") == "user":
                text = INJECTED.sub("", " ".join(c.get("text", "") for c in p.get("content") or []
                                                if isinstance(c, dict))).strip()
                if not text:
                    continue                                  # only the context Codex injects, not the person's words
                if cur is not None and not cur["request"]:
                    cur["request"] = text                     # Codex writes the request inside its turn
                else:
                    last_user = text
            elif kind == ("event_msg", "task_started"):
                cur = {"turn_id": p.get("turn_id"), "started": o.get("timestamp"), "model": model,
                       "request": last_user, "pieces": set()}
            elif kind == ("event_msg", "task_complete") and cur is not None:
                cur.update(ended=o.get("timestamp"), duration_s=round(int(p.get("duration_ms") or 0) / 1000, 1))
                tasks.append(cur)
                cur = None
            if cur is not None and ("athos-" in line or "`, v" in line):
                cur["pieces"] |= set(SKILL_USE.findall(line)) | set(HOOK_USE.findall(line))
    for t in tasks:
        t["session_id"], t["cwd"], t["path"] = meta.get("id", path.stem), meta.get("cwd", ""), str(path)
    return tasks


def import_sessions(root: Path | None = None, include_tmp: bool = False) -> dict:
    """Record Codex's past tasks in the evaluation log as platform codex, from its own session files. Idempotent:
    a turn is imported once, and sessions the hooks already recorded are skipped. Sessions run in temporary folders
    (tests) are left out unless asked."""
    from athos import eval as ev
    root = root or sessions_dir()
    known = {e.get("task_id") for e in ev.events()}
    hooked = {e.get("session_id") for e in ev.events() if e.get("type") == "task_start" and e.get("platform") == "codex"
              and not str(e.get("task_id", "")).startswith("cx-")}
    pieces = {p.id for p in store.all_pieces()}
    out = {"files": 0, "imported": 0, "skipped": 0}
    files = sorted(set(root.glob("**/rollout-*.jsonl")) | set(root.glob("**/rollout-*.jsonl.zst"))) if root.is_dir() else []
    for f in files:
        out["files"] += 1
        for t in _rollout_tasks(f):
            tid = f"cx-{t['turn_id']}"
            if tid in known or t["session_id"] in hooked or not t.get("ended") or \
                    (not include_tmp and t["cwd"].startswith(TMP_PREFIXES)):
                out["skipped"] += 1
                continue
            used = sorted(x for x in t["pieces"] if x in pieces)
            ev.append({"type": "task_start", "task_id": tid, "session_id": t["session_id"], "platform": "codex",
                       "model": t["model"], "project": Path(t["cwd"]).name if t["cwd"] else None, "at": t["started"],
                       **ev.request_fields(t["request"]), "source": "codex-import"})
            ev.append({"type": "task_end", "task_id": tid, "session_id": t["session_id"], "at": t["ended"],
                       "duration_s": t["duration_s"], "tokens": tokens_between(t["path"], t["started"], t["ended"]),
                       "model": t["model"], "pieces": used, "saved": []})
            known.add(tid)
            out["imported"] += 1
    return out
