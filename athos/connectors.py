"""Connectors: something outside Athos that a way of working needs to be done well, kept as a readable file in
`~/.athos/connectors/<name>.md`, like the pieces.

    kind: gateway   the agent's model traffic goes through it (pii-guard: personal data masked before the model)
    kind: tool      an MCP server the agent calls
    kind: command   a local command line tool

A piece asks for one in its text, where the step needs it: `[[connector:pii-guard]]`. When such a piece is loaded,
Athos checks the connector (its `check` URL) and tells the model and the person whether it is active. Nothing is
started or wired without the person: `athos connector` prints how.
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from athos import paths, store

REF = re.compile(r"\[\[connector:([a-z0-9][a-z0-9-]*)\]\]")

# Ready to add with `athos connector add <name>`: the person still runs the service.
TEMPLATES = {
    "pii-guard": """---
name: pii-guard
kind: gateway
what: masks personal data (names, emails, IDs, faces) before the model and restores it in the answer
check: http://127.0.0.1:8787/v1/status
start: uvx --python 3.12 --from 'wattmind-pii-guard[ner] @ git+https://github.com/watt-mind/pii-guard' pii-guard up --upstream meta
source: https://github.com/watt-mind/pii-guard
wire:
  opencode: eval "$(pii-guard connect opencode --print)" && opencode
  codex: pii-guard connect codex --print
  muse-code: pii-guard connect muse --print
  claude-code: pii-guard connect claude --print
---
An OpenAI-compatible gateway on this computer (Apache-2.0, Watt Mind). Personal data reaches the model as placeholders
like [[PERSON_7f3a]] and comes back with the real values in the answer. Language packs: Hungarian, English, German,
Polish. It needs META_API_KEY (or another upstream key) in the terminal that starts it.
""",
}


@dataclass
class Connector:
    name: str
    kind: str = "gateway"
    what: str = ""
    check: str = ""
    start: str = ""
    source: str = ""
    wire: dict = field(default_factory=dict)
    notes: str = ""


def folder() -> Path:
    return paths.home() / "connectors"


def parse(text: str) -> Connector:
    data, body = store.parse_frontmatter(text)
    return Connector(name=str(data.get("name", "")), kind=str(data.get("kind", "gateway")), what=str(data.get("what", "")),
                     check=str(data.get("check", "")), start=str(data.get("start", "")), source=str(data.get("source", "")),
                     wire=dict(data.get("wire") or {}), notes=body.strip())


def get(name: str) -> Connector | None:
    f = folder() / f"{name}.md"
    if f.exists():
        return parse(f.read_text())
    return None


def all_connectors() -> list[Connector]:
    return [parse(f.read_text()) for f in sorted(folder().glob("*.md"))] if folder().exists() else []


def add(name: str) -> Path:
    if name not in TEMPLATES:
        raise SystemExit(f"athos connector: no template for {name!r} (known: {', '.join(TEMPLATES)}); write "
                         f"{folder() / (name + '.md')} yourself")
    f = folder() / f"{name}.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text(TEMPLATES[name])
    return f


def active(c: Connector, timeout: float = 1.0) -> bool:
    """Whether the connector answers its `check` URL (any non-error status). A connector without one counts as
    active: there is nothing to check."""
    if not c.check:
        return True
    try:
        with urllib.request.urlopen(c.check, timeout=timeout) as r:
            return r.status < 400
    except Exception:  # noqa: BLE001 — down, refused, timed out: not active
        return False


def named_in(pieces) -> list[str]:
    """The connectors these pieces ask for, in order of first mention."""
    out: list[str] = []
    for p in pieces:
        for name in REF.findall(p.body):
            if name not in out:
                out.append(name)
    return out


def status(pieces) -> list[dict]:
    """For each connector the pieces ask for: whether it is set up here and whether it answers."""
    out = []
    for name in named_in(pieces):
        c = get(name)
        out.append({"name": name, "what": c.what if c else "", "set_up": bool(c), "active": bool(c) and active(c),
                    "start": c.start if c else "", "kind": c.kind if c else ""})
    return out


def model_text(states: list[dict], cmd: str = "athos") -> str:
    """What the model is told about the connectors of this request."""
    lines = []
    for s in states:
        if s["active"] and s["kind"] == "gateway":
            lines.append(f"**{s['name']} is active** ({s['what']}): personal data in this request may reach you as "
                         f"placeholders like [[PERSON_7f3a]]. Keep every placeholder exactly as it is, never guess what "
                         f"it hides; it is restored in the answer the person reads.")
        elif s["active"]:
            lines.append(f"**{s['name']} is available** ({s['what']}): use it where the way of working says so.")
        else:
            why = "is not running" if s["set_up"] else f"is not set up (`{cmd} connector add {s['name']}`)"
            lines.append(f"**{s['name']} {why}.** If this request carries client personal data, don't process it: "
                         f"ask the person to start {s['name']} or to anonymise the data first.")
    return "\n".join(lines)
