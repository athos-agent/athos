"""`athos mcp`: the know-how as an MCP server over stdio, for apps that take MCP servers but not plugins (Claude
Desktop's chat, or any MCP client). No dependencies: newline-delimited JSON-RPC 2.0, the subset MCP tools need.

Tools: find the pieces for a request (and say where their walk goes), show one, list them, and save one (a new piece,
or a new version of an existing one), the same way Claude Code's capture does. Nothing leaves the machine: the server
reads and writes ~/.athos like the `athos` command.

In Claude Desktop, add to claude_desktop_config.json (Settings → Developer → Edit Config):

    "mcpServers": {"athos": {"command": "/absolute/path/to/athos", "args": ["mcp"]}}
"""

from __future__ import annotations

import json
import sys

from athos import capture, load, store, wiki

PROTOCOL = "2025-06-18"
INSTRUCTIONS = ("The person's own know-how, kept by Athos as a wiki of pieces. Before a task, call athos_find with "
                "the request: follow the pieces it returns, statement by statement, and cite them as [[page#id]]. "
                "When a task taught something reusable, call athos_save once.")

TOOLS = [
    {"name": "athos_find", "description": "The person's know-how for a request: the matching pieces in full, with "
     "the trajectory each one starts (the pages its links lead to). Call it before starting a task.",
     "inputSchema": {"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"]}},
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


def call(name: str, args: dict, session_id: str = "mcp") -> str:
    if name == "athos_find":
        found = load.relevant(args.get("request", ""), load.enabled(None))
        if not found:
            return "No know-how for this request yet."
        pages = {p.id: p for p in store.all_pieces()}
        out = []
        for p in found:
            trail = wiki.walk(p.id, pages)
            out.append(_piece_text(p) + (f"\n\nTrajectory: {' → '.join(trail)}" if len(trail) > 1 else ""))
        load.mark_loaded(session_id, [p.id for p in found])
        return "\n\n---\n\n".join(out)
    if name == "athos_show":
        p = store.get(args.get("id", ""))
        return _piece_text(p) if p else f"No piece {args.get('id')!r}."
    if name == "athos_list":
        return "\n".join(f"- `{p.id}` {p.title}. When: {p.when}" for p in store.all_pieces()) or "No pieces yet."
    if name == "athos_save":
        piece, diff = capture.save_text(args.get("text", ""), session_id)
        return f"improved {piece.id} → v{piece.version}" if diff else f"saved {piece.id}"
    raise KeyError(name)


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message in, its response out (None for notifications)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "athos", "version": "1"},
                      "instructions": INSTRUCTIONS}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                text, err = call(params.get("name", ""), params.get("arguments") or {}), False
            except (ValueError, LookupError) as e:
                text, err = f"{type(e).__name__}: {e}", True
            result = {"content": [{"type": "text", "text": text}], "isError": err}
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
