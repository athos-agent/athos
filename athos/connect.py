"""Athos in the person's other agents, from one place.

Which of Codex, OpenCode and Muse Code are on this computer (their command on PATH, or their config folder), connecting
one (the same code as `athos codex install` and `athos opencode install`; Muse Code through its own plugin commands),
and which version of Athos each agent would run (`athos doctor`), so an agent left behind shows up in one line instead
of costing an hour (2026-10-31: OpenCode, Muse Code and the `athos` on PATH were still on 0.1.60).

Nothing here runs by itself: connecting is a click in Desktop's panel or a command the person types.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = (("codex", "Codex"), ("opencode", "OpenCode"), ("muse", "Muse Code"))
MARKETPLACE = "https://github.com/athos-agent/athos"
MUSE_STEPS = (["plugins", "marketplace", "add", "athos", MARKETPLACE], ["plugins", "install", "athos@athos"],
              ["plugins", "approve", "athos"])
TIMEOUT = 120               # a marketplace add clones the repository
LIST_TIMEOUT = 5

TEXT = {
    "en": {
        "codex": "Codex is connected. Next time you open Codex, type /hooks and approve Athos's hooks.",
        "opencode": "OpenCode is connected. Restart OpenCode to load Athos.",
        "muse": "Muse Code is connected. Restart Muse Code to load Athos.",
        "no_muse": "Muse Code's `muse` command isn't on this computer's PATH, so Athos can't connect it from here.",
        "muse_failed": "Muse Code didn't finish connecting (`muse {step}`): {err}",
        "behind": "Behind the newest Athos ({newest}): {who}. {what}",
        "fix": {"claude-code": "Claude Code: /plugin, then update athos.",
                "claude-desktop": "Claude Desktop: install the newest athos.mcpb.",
                "codex": "Codex: connect it again.", "opencode": "OpenCode: connect it again, then restart it.",
                "muse": "Muse Code: connect it again.",
                "path": "Terminal: run install.sh again (curl -fsSL "
                        "https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh)."},
    },
    "es": {
        "codex": "Codex quedó conectado. La próxima vez que abras Codex, escribí /hooks y aprobá los hooks de Athos.",
        "opencode": "OpenCode quedó conectado. Reiniciá OpenCode para que cargue Athos.",
        "muse": "Muse Code quedó conectado. Reiniciá Muse Code para que cargue Athos.",
        "no_muse": "El comando `muse` de Muse Code no está en el PATH de esta computadora: Athos no lo puede conectar "
                   "desde acá.",
        "muse_failed": "Muse Code no terminó de conectarse (`muse {step}`): {err}",
        "behind": "Atrasados respecto del Athos más nuevo ({newest}): {who}. {what}",
        "fix": {"claude-code": "Claude Code: /plugin y actualizá athos.",
                "claude-desktop": "Claude Desktop: instalá el athos.mcpb más nuevo.",
                "codex": "Codex: conectalo de nuevo.", "opencode": "OpenCode: conectalo de nuevo y reinicialo.",
                "muse": "Muse Code: conectalo de nuevo.",
                "path": "Terminal: corré install.sh de nuevo (curl -fsSL "
                        "https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh)."},
    },
}
LABELS = {"claude-code": "Claude Code", "claude-desktop": "Claude Desktop", "codex": "Codex", "opencode": "OpenCode",
          "muse": "Muse Code", "path": "athos (terminal)"}


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _home_of(agent: str) -> Path:
    from athos.adapters import codex, opencode
    return {"codex": codex.codex_home(), "opencode": opencode.plugins_dir().parent,
            "muse": _data_home() / "muse"}[agent]


def found(agent: str) -> bool:
    return bool(shutil.which(agent)) or _home_of(agent).is_dir()


def _muse_installed() -> dict:
    try:
        return json.loads((_data_home() / "muse" / "plugins" / "installed.json").read_text())["plugins"]["athos"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def connected(agent: str) -> bool:
    from athos.adapters import codex, opencode
    if agent == "codex":
        return codex.installed()
    if agent == "opencode":
        return (opencode.plugins_dir() / "athos.js").is_file()
    return bool(_muse_installed())


def agents() -> list[dict]:
    """The other agents on this computer and whether Athos is in them."""
    return [{"id": a, "name": name, "found": found(a), "connected": found(a) and connected(a)} for a, name in AGENTS]


def connect(agent: str, lang: str = "en", run=subprocess.run) -> str:
    """Put Athos in one agent, as the person's own command would, and say in one line what they still have to do."""
    T = TEXT["es" if lang == "es" else "en"]
    from athos.adapters import codex
    if agent == "codex":
        codex.install(ROOT)
        return T["codex"]
    if agent == "opencode":
        from athos.adapters import opencode
        opencode.install(codex.write_shim(ROOT))
        return T["opencode"]
    if agent != "muse":
        raise ValueError(f"unknown agent {agent!r}: codex, opencode or muse")
    muse = shutil.which("muse")
    if not muse:
        return T["no_muse"]
    for step in MUSE_STEPS:
        try:
            r = run([muse, *step], capture_output=True, text=True, timeout=TIMEOUT)
        except (OSError, subprocess.SubprocessError) as e:
            return T["muse_failed"].format(step=" ".join(step), err=str(e)[:200])
        err = ((r.stderr or "") + (r.stdout or "")).strip()
        # Adding the marketplace a second time is not a failure: the person is connecting again to update.
        if r.returncode != 0 and not (step[1] == "marketplace" and "already" in err.lower()):
            return T["muse_failed"].format(step=" ".join(step), err=err[-200:] or f"exit {r.returncode}")
    return T["muse"]


# ------------------------------------------------------------------------------------------------ versions
def parse_version(v: str | None) -> tuple:
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("v").split("."))
    except ValueError:
        return ()


def _root_version(root: Path) -> str | None:
    for f in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "manifest.json"):
        try:
            return json.loads((root / f).read_text())["version"]
        except (OSError, ValueError, KeyError):
            continue
    return None


def _claude_plugins() -> list[str]:
    return glob.glob(str(Path.home() / ".claude" / "plugins" / "cache" / "athos" / "athos" / "*" / "bin" / "athos"))


def _newest_claude_plugin() -> tuple[str | None, Path | None]:
    roots = [Path(p).parents[1] for p in _claude_plugins()]
    best = max(roots, key=lambda r: parse_version(r.name) or (0,), default=None)
    return (_root_version(best) or best.name, best) if best else (None, None)


def command_version(path: str | Path) -> str | None:
    """The Athos a command runs: the shim (newest Claude Code plugin, else the copy that wrote it), a launcher from
    install.sh (`exec python "<app>/bin/athos"`), or an `athos` inside an installation."""
    try:
        head = Path(path).read_text(errors="ignore")[:4000]
    except OSError:
        return None
    if "Runs the newest installed Athos" in head:
        v, _ = _newest_claude_plugin()
        m = re.search(r"cands\[-1\] if cands else (['\"])(.+?)\1", head)
        return v or (_root_version(Path(m.group(2)).parents[1]) if m else None)
    m = re.search(r'"([^"]+/bin/athos)"', head)
    target = Path(m.group(1)) if m else Path(os.path.realpath(path))
    return _root_version(target.parents[1])


def _codex_version() -> str | None:
    from athos.adapters import codex
    try:
        hooks = (codex.codex_home() / "hooks.json").read_text()
    except OSError:
        hooks = ""
    m = re.search(r"(\S+/bin/athos)\s+hook\s", hooks)
    if m:
        return command_version(m.group(1))
    roots = [Path(p).parent.parent for p in glob.glob(str(codex.codex_home() / "plugins" / "cache" / "*" / "athos" /
                                                          "*" / ".codex-plugin" / "plugin.json"))]
    vs = [v for v in (_root_version(r) for r in roots) if v]
    return max(vs, key=parse_version, default=None)


def _opencode_version() -> str | None:
    from athos.adapters import opencode
    try:
        js = (opencode.plugins_dir() / "athos.js").read_text()
    except OSError:
        return None
    m = re.search(r'const ATHOS = [^\n]*?"([^"]+)"', js)
    return command_version(m.group(1).replace('\\"', '"').replace("\\\\", "\\")) if m else None


def _muse_version(run=subprocess.run, ask: bool = True) -> str | None:
    v = _muse_installed().get("version")
    if v or not ask:
        return v
    muse = shutil.which("muse")
    if not muse:
        return None
    try:
        out = run([muse, "plugins", "list"], capture_output=True, text=True, timeout=LIST_TIMEOUT).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\bathos\b\S*\s+v?(\d+\.\d+\.\d+)", out)
    return m.group(1) if m else None


def _desktop_version() -> str | None:
    base = Path.home() / "Library" / "Application Support" / "Claude" / "Claude Extensions"
    vs = [v for v in (_root_version(Path(d)) for d in glob.glob(str(base / "*athos*"))) if v]
    return max(vs, key=parse_version, default=None)


def versions(run=subprocess.run, ask_muse: bool = True) -> dict:
    """Which Athos each agent would run, the newest one on this computer, and the agents behind it. `ask_muse`
    runs `muse plugins list` (short timeout) when Muse's own record of its plugins can't be read."""
    path = shutil.which("athos")
    rows = {"claude-code": _newest_claude_plugin()[0], "claude-desktop": _desktop_version(),
            "codex": _codex_version(), "opencode": _opencode_version(), "muse": _muse_version(run, ask_muse),
            "path": command_version(path) if path else None}
    rows = {k: v for k, v in rows.items() if v}
    mine = _root_version(ROOT)
    newest = max([*rows.values(), *([mine] if mine else [])], key=parse_version, default=None)
    behind = [k for k, v in rows.items() if newest and parse_version(v) < parse_version(newest)]
    return {"this": mine, "newest": newest, "agents": rows, "behind": behind}


def behind_line(v: dict, lang: str = "en") -> str:
    """One line for the panel and the status when an agent runs an older Athos: who, and what to do."""
    if not v.get("behind"):
        return ""
    T = TEXT["es" if lang == "es" else "en"]
    who = ", ".join(f"{LABELS[k]} {v['agents'][k]}" for k in v["behind"])
    return T["behind"].format(newest=v["newest"], who=who, what=" ".join(T["fix"][k] for k in v["behind"]))


def report(v: dict, lang: str = "en") -> str:
    """`athos doctor`: one line per agent, then what to do."""
    es = lang == "es"
    out = [f"{'Este Athos' if es else 'This Athos'}: {v['this'] or '?'} · "
           f"{'el más nuevo' if es else 'newest'}: {v['newest'] or '?'}"]
    for k, label in LABELS.items():
        ver = v["agents"].get(k)
        if ver:
            mark = ("atrasado" if es else "behind") if k in v["behind"] else "ok"
            out.append(f"  {label:<18} {ver:<10} {mark}")
    missing = [LABELS[k] for k in LABELS if k not in v["agents"]]
    if missing:
        out.append(("  sin Athos: " if es else "  no Athos found: ") + ", ".join(missing))
    line = behind_line(v, lang)
    return "\n".join(out + ([line] if line else []))
