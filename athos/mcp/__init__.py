"""`athos mcp`: the know-how as an MCP server over stdio, for apps that take MCP servers but not plugins (Claude
Desktop's chat, or any MCP client). No dependencies: newline-delimited JSON-RPC 2.0, the subset MCP tools need.

Tools: find the pieces for a request (and say where their walk goes), show one, list them, and save one (a new piece,
or a new version of an existing one), the same way Claude Code's capture does. Nothing leaves the machine: the server
reads and writes ~/.athos like the `athos` command.

In a host with MCP Apps (Claude Desktop's chat), athos_find also opens Athos's trail panel (`ui://athos/trail`): the
person's know-how the task walks, step by step, as the agent reports it with athos_step, refreshed by the panel through
the app-only athos_trail. A host without MCP Apps gets the same tools as text.

In Claude Desktop, add to claude_desktop_config.json (Settings → Developer → Edit Config):

    "mcpServers": {"athos": {"command": "/absolute/path/to/athos", "args": ["mcp"]}}
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from athos import capture, load, session, store, trail, wiki

PROTOCOL = "2025-06-18"
INSTRUCTIONS = ("The person's own know-how, kept by Athos as a wiki of pieces. Before each task, call athos_find with "
                "the request: follow the pieces it returns, statement by statement, and cite them as [[page#id]]. The "
                "person watches the task in Athos's panel: as you start each statement call athos_step with "
                "<piece-id>#<statement_id>; a step the task needs that no piece has, athos_step with `new` (a few "
                "words, in the person's language). Once per step, never per action, and say nothing about it. "
                "When a task taught something reusable, call athos_save once. A message from the panel that starts "
                "with \"Athos · save:\" or \"Athos · guardar:\" asks you to save the task that just ended, its new "
                "steps included (improve the piece it used: its id and a note); one that starts with "
                "\"Athos · adjust\" or \"Athos · ajustar\" names <piece>#<statement> and how it should change: improve "
                "that piece with athos_save (its id and a note), then go on. Answer those in one short line.")
UI_EXTENSION = "io.modelcontextprotocol/ui"
UI_MIME = "text/html;profile=mcp-app"
UI_URI = "ui://athos/trail"
UI_HTML = Path(__file__).with_name("trail.html")
SESSION = "claude-desktop"
# What the host said about itself in `initialize`: whether it draws MCP Apps.
CLIENT: dict = {}

TOOLS = [
    {"name": "athos_find", "description": "The person's know-how for a request: the matching pieces in full, with "
     "the trajectory each one starts (the pages its links lead to). Call it before starting a task.",
     "inputSchema": {"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"]},
     "_meta": {"ui": {"resourceUri": UI_URI}}},
    {"name": "athos_step", "description": "Tell the person which step of their know-how you are on now "
     "(`step`: <piece-id>#<statement_id>), or a step the task needs that their know-how doesn't have yet (`new`). "
     "Once per step, as you start it.",
     "inputSchema": {"type": "object", "properties": {"step": {"type": "string"}, "new": {"type": "string"}}}},
    {"name": "athos_trail", "description": "What Athos's panel draws: the current task's trail, the greeting, the "
     "person's language. Called by the panel only.",
     "inputSchema": {"type": "object", "properties": {}}, "_meta": {"ui": {"visibility": ["app"]}}},
    {"name": "athos_show", "description": "One piece of know-how, in full, by id.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "athos_list", "description": "Every piece: id, title and when it applies.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "athos_save", "description": "Save what a task taught as one piece, or improve an existing one (give "
     "its id and a note). The text is a frontmatter (title, when, and id + note to improve) and a body of statements "
     "(## #id with **When:** **Do:** **Because:** **Links:**).",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
]


def _piece_text(p: store.Piece) -> str:
    return f"# {p.title} (`{p.id}`, v{p.version})\nWhen: {p.when}\n\n{p.body}"


def draws_apps() -> bool:
    ui = ((CLIENT.get("capabilities") or {}).get("extensions") or {}).get(UI_EXTENSION) or {}
    return UI_MIME in (ui.get("mimeTypes") or [])


def tools() -> list[dict]:
    """The tools this host gets: the panel's own one only where the panel can be drawn."""
    return [t for t in TOOLS if t["name"] != "athos_trail" or draws_apps()]


def panel(session_id: str = SESSION) -> dict:
    """What the panel draws, as the structured result of the tools that move it."""
    from athos import start
    lang = start.lang()
    return {"lang": lang, "greeting": trail.greeting(lang), "pieces": len(store.all_pieces()),
            "trail": trail.view(session.load(session_id)),
            "save_prompt": capture.SAVE_PROMPT["es" if lang == "es" else "en"],
            "adjust_prefix": capture.ADJUST_PREFIX["es" if lang == "es" else "en"]}


def _new_task(session_id: str, request: str) -> None:
    """A request starts a task: its own trail. Not a measured task: a chat has no end of turn to time it by."""
    session.update(session_id, task_id=uuid.uuid4().hex[:12], task_loaded=[], task_why={}, trail=[],
                   platform="claude-desktop", task_request=request[:200])


def call(name: str, args: dict, session_id: str = SESSION) -> str:
    if name == "athos_find":
        from athos import start
        start.note_language(args.get("request", ""))         # the panel speaks the language the person writes in
        _new_task(session_id, args.get("request", ""))
        found = load.relevant(args.get("request", ""), load.enabled(None))
        if not found:
            return ("No know-how for this request yet. If the task takes several steps, report each with athos_step "
                    "`new`: they draft a new way of working.")
        session.update(session_id, task_why={p.id: load.why(args.get("request", ""), p) for p in found})
        pages = {p.id: p for p in store.all_pieces()}
        out = []
        for p in found:
            walk = wiki.walk(p.id, pages)
            out.append(_piece_text(p) + (f"\n\nTrajectory: {' → '.join(walk)}" if len(walk) > 1 else ""))
        load.mark_loaded(session_id, [p.id for p in found])
        return "\n\n---\n\n".join(out)
    if name == "athos_show":
        p = store.get(args.get("id", ""))
        if p:
            trail.note(session_id, {"kind": "read", "piece": p.id, "title": p.title})
        return _piece_text(p) if p else f"No piece {args.get('id')!r}."
    if name == "athos_step":
        try:
            return trail.step(session_id, args.get("step"), args.get("new"))
        except SystemExit as e:
            raise ValueError(str(e)) from None
    if name == "athos_trail":
        return json.dumps(panel(session_id), ensure_ascii=False)
    if name == "athos_list":
        return "\n".join(f"- `{p.id}` {p.title}. When: {p.when}" for p in store.all_pieces()) or "No pieces yet."
    if name == "athos_save":
        piece, diff = capture.save_text(args.get("text", ""), session_id)
        out = f"improved {piece.id} → v{piece.version}" if diff else f"saved {piece.id}"
        w = session.load(session_id).get("wiki") or {}
        if w.get("broken"):
            out += "\nLinks that lead nowhere (fix with another athos_save): " + "; ".join(w["broken"][:10])
        if w.get("overlaps"):
            out += ("\nOther pages say what to do at the same moment; check they agree and fix the wrong one: "
                    + "; ".join(w["overlaps"][:10]))
        return out
    raise KeyError(name)


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message in, its response out (None for notifications)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None
    try:
        if method == "initialize":
            CLIENT.clear()
            CLIENT.update(params)
            result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                      "capabilities": {"tools": {}, "resources": {}, "extensions": {UI_EXTENSION: {}}},
                      "serverInfo": {"name": "athos", "version": "1"}, "instructions": INSTRUCTIONS}
        elif method == "tools/list":
            result = {"tools": tools()}
        elif method == "resources/list":
            result = {"resources": [{"uri": UI_URI, "name": "Athos · trail", "mimeType": UI_MIME,
                                     "description": "The task's walk through the person's know-how, step by step"}]}
        elif method == "resources/read":
            if params.get("uri") != UI_URI:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32002, "message": "no such resource"}}
            result = {"contents": [{"uri": UI_URI, "mimeType": UI_MIME, "text": UI_HTML.read_text(),
                                    "_meta": {"ui": {"prefersBorder": True}}}]}
        elif method == "tools/call":
            name = params.get("name", "")
            try:
                text, err = call(name, params.get("arguments") or {}), False
            except (ValueError, LookupError) as e:
                text, err = f"{type(e).__name__}: {e}", True
            result = {"content": [{"type": "text", "text": text}], "isError": err}
            if name in ("athos_find", "athos_step", "athos_trail") and not err:
                result["structuredContent"] = panel()
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
    except Exception as e:  # noqa: BLE001 — the server answers, it never dies on one bad call
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)[:300]}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> int:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        out = handle(msg)
        if out is not None:
            stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0
