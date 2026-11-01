"""`athos mcp`: the know-how as an MCP server over stdio, for apps that take MCP servers but not plugins (Claude
Desktop's chat, or any MCP client). No dependencies: newline-delimited JSON-RPC 2.0, the subset MCP tools need.

Tools: find the pieces for a request (and say where their walk goes), show one, list them, and save one (a new piece,
or a new version of an existing one), the same way Claude Code's capture does. Nothing leaves the machine: the server
reads and writes ~/.athos like the `athos` command.

In a host with MCP Apps (Claude Desktop's chat), athos_find also opens Athos's trail panel (`ui://athos/trail`): the
person's know-how the task walks, step by step, as the agent reports it with athos_step, refreshed by the panel through
the app-only athos_trail. A host without MCP Apps gets the same tools as text. There, athos_library also opens the
person's library (`ui://athos/library`, athos/library.html): every way of working, its versions, what each model gave;
its two buttons go through the app-only athos_library_do.

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
# How the model talks to the person once Athos's panel shows the method: in the chat, only the answer. The person
# may be a lawyer or a journalist, not the author of the notes in the piece (2026-10-30, Claude Desktop: the answer
# narrated tools in English, cited "piece v7" and "checked live on 27/10" and pasted the piece's commands).
ANSWER = ("How to answer: the person sees Athos's panel above your answer, with the way of working you follow and "
          "its steps, so your answer is only the answer. Write in the person's language, plainly, as a colleague who "
          "already knows how they work: do the task or answer the question directly. Don't narrate tools or say "
          "you are reading something; don't mention Athos, pieces, ids, versions, or the dates, measurements and "
          "notes the piece keeps for you; give commands, paths or settings only when the person must act on them. "
          "Take from the piece only what this request needs.")
UI_EXTENSION = "io.modelcontextprotocol/ui"
UI_MIME = "text/html;profile=mcp-app"
UI_URI = "ui://athos/trail"
UI_HTML = Path(__file__).with_name("trail.html")
LIBRARY_URI = "ui://athos/library"
LIBRARY_HTML = Path(__file__).resolve().parents[1] / "library.html"
LIBRARY_META = "athos/library"
APP_ONLY = {"athos_trail", "athos_library_do"}           # called by Athos's pages, never by the model
APPS_ONLY = APP_ONLY | {"athos_library"}                 # offered only where a page can be drawn
SESSION = "claude-desktop"
PANEL_META = "athos/panel"
# What the host said about itself in `initialize`: whether it draws MCP Apps.
CLIENT: dict = {}

TOOLS = [
    {"name": "athos_find", "title": "Athos: your way of working",
     "description": "Call this FIRST, before any other tool, for every task or request the person makes. It returns "
     "the person's own saved way of doing this kind of task (their know-how: steps, criteria, checklists, rules "
     "they taught before, e.g. how they draft a letter, review a contract, ship a release), which you must follow, "
     "and opens Athos's panel where they watch the task step by step. Pass the request in their words.",
     "inputSchema": {"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"]},
     "_meta": {"ui": {"resourceUri": UI_URI}}},
    {"name": "athos_step", "description": "Tell the person which step of their know-how you are on now "
     "(`step`: <piece-id>#<statement_id>), or a step the task needs that their know-how doesn't have yet (`new`). "
     "Once per step, as you start it.",
     "inputSchema": {"type": "object", "properties": {"step": {"type": "string"}, "new": {"type": "string"}}}},
    {"name": "athos_trail", "description": "What Athos's panel draws: the current task's trail, the greeting, the "
     "person's language. Called by the panel only.",
     "inputSchema": {"type": "object", "properties": {}}, "_meta": {"ui": {"visibility": ["app"]}}},
    {"name": "athos_library", "title": "Athos: your library",
     "description": "Open the person's library in the chat: every way of working they have, how often each was used "
     "and how it went, in which agents and models, its versions (they can go back to one), and what each model gave "
     "them. Call it when they ask to see, browse or review their ways of working, know-how or library.",
     "inputSchema": {"type": "object", "properties": {}}, "_meta": {"ui": {"resourceUri": LIBRARY_URI}}},
    {"name": "athos_library_do", "description": "The library page's buttons: go back to a version (`revert`, id, "
     "version) or open a page's file in the person's editor (`open`, id). Called by the library page only, after "
     "the person confirms.",
     "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["revert", "open"]},
                                                      "id": {"type": "string"}, "version": {"type": "integer"}},
                     "required": ["action", "id"]},
     "_meta": {"ui": {"resourceUri": LIBRARY_URI, "visibility": ["app"]}}},
    {"name": "athos_show", "description": "One piece of know-how, in full, by id.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "athos_list", "description": "Every piece: id, title and when it applies.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "athos_save", "description": "Save what a task taught as one piece, or improve an existing one (give "
     "its id and a note). The text is a frontmatter (title, when, and id + note to improve) and a body of statements "
     "(## #id with **When:** **Do:** **Because:** **Links:**).",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "athos_merge", "description": "Merge colleagues' copies of one of the person's ways of working into one "
     "team version (\"merge my lease review with Ana's version in this folder\"). `id`: the person's piece; `paths`: "
     "the colleagues' exported files or folders (from `athos export --guild`). Without `apply` it only proposes and "
     "says what it would keep, take from whom, and drop; with `apply: true` (only once the person agreed) it saves "
     "the merge as a new version, the old one kept.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "string"}, "paths": {"type": "array", "items": {"type": "string"}},
         "as_id": {"type": "string", "description": "the id the colleagues' copies have, if it differs"},
         "apply": {"type": "boolean"}}, "required": ["id", "paths"]}},
    {"name": "athos_add", "description": "Add a way of working from Athos's public gallery (only from the athos-agent/"
     "athos repository) and the pages it calls, when the person asks for it, e.g. by pasting \"Athos · add from "
     "gallery: <id>\". Pages they already have are left as they are. `preview: true` only shows what would be added.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "description": "the gallery id or its "
                     "raw URL"}, "preview": {"type": "boolean"}}, "required": ["id"]}},
    # The panel's own buttons on a first use: a profession's example ways of working, and Athos in the person's
    # other agents. Each runs on the person's click, never on the model's.
    {"name": "athos_start", "description": "Add a profession's example ways of working (as `athos start`). Called "
     "by the panel only, on the person's click.",
     "inputSchema": {"type": "object", "properties": {"profile": {"type": "string"}, "lang": {"type": "string"}},
                     "required": ["profile"]}, "_meta": {"ui": {"visibility": ["app"]}}},
    {"name": "athos_connect", "description": "Put Athos in another agent on this computer (codex, opencode or muse), "
     "as `athos codex install` / `athos opencode install` / Muse's plugin commands. Called by the panel only, on the "
     "person's click.",
     "inputSchema": {"type": "object", "properties": {"agent": {"type": "string"}}, "required": ["agent"]},
     "_meta": {"ui": {"visibility": ["app"]}}},
]


def _piece_text(p: store.Piece) -> str:
    return f"# {p.title} (`{p.id}`, v{p.version})\nWhen: {p.when}\n\n{p.body}"


def draws_apps() -> bool:
    ui = ((CLIENT.get("capabilities") or {}).get("extensions") or {}).get(UI_EXTENSION) or {}
    return UI_MIME in (ui.get("mimeTypes") or [])


def app_only(tool: dict) -> bool:
    return ((tool.get("_meta") or {}).get("ui") or {}).get("visibility") == ["app"]


def tools() -> list[dict]:
    """The tools this host gets: the pages' own ones (and the library, which is a page) only where a page can be
    drawn."""
    return [t for t in TOOLS if not (app_only(t) or t["name"] in APPS_ONLY) or draws_apps()]


# The panel asks for its state every few seconds; which agents are here and their versions change only when the
# person installs something, so they are looked up once a minute (and again right after a click that changes them).
SETUP_TTL = 60
_SETUP: dict = {}


def setup(lang: str) -> dict:
    """What the panel offers besides the task: professions on a first use, the other agents to connect, and one
    line when an agent runs an older Athos."""
    import time
    from athos import connect, start
    if not _SETUP or time.time() - _SETUP.get("t", 0) > SETUP_TTL:
        try:
            _SETUP.update(t=time.time(), agents=[a for a in connect.agents() if a["found"]],
                          versions=connect.versions(ask_muse=False))
        except Exception as e:  # noqa: BLE001 — a broken agent config must not break the panel
            print(f"athos mcp: setup: {e}", file=sys.stderr)
            _SETUP.update(t=time.time(), agents=[], versions={})
    return {"professions": start.professions(lang), "agents": _SETUP["agents"],
            "behind": connect.behind_line(_SETUP["versions"], lang) if _SETUP["versions"] else ""}


def panel(session_id: str = SESSION) -> dict:
    """What the panel draws, as the structured result of the tools that move it."""
    from athos import start
    state = session.load(session_id)
    # The language of this request, not a preference seen elsewhere: a Spanish request got an English panel when
    # another agent had last seen English (2026-10-30).
    lang = (start.detect(state.get("task_request", "")) if not start.config().get("lang") else None) or start.lang()
    return {"lang": lang, "greeting": trail.greeting(lang), "pieces": len(store.all_pieces()),
            "trail": trail.view(state),
            "save_prompt": capture.SAVE_PROMPT["es" if lang == "es" else "en"],
            "adjust_prefix": capture.ADJUST_PREFIX["es" if lang == "es" else "en"], "setup": setup(lang)}


def _new_task(session_id: str, request: str) -> None:
    """A request starts a task: its own trail. Not a measured task: a chat has no end of turn to time it by."""
    session.update(session_id, task_id=uuid.uuid4().hex[:12], task_loaded=[], task_why={}, trail=[],
                   platform="claude-desktop", task_request=request[:200])


def call(name: str, args: dict, session_id: str = SESSION) -> str:
    if name == "athos_find":
        from athos import start
        start.note_language(args.get("request", ""))         # the panel speaks the language the person writes in
        from athos import gallery
        if ref := gallery.requested(args.get("request", "")):
            return (f"The person asked to add {ref!r} from Athos's gallery: call athos_add with id {ref!r} now, then "
                    "tell them in one short line, in their language, what was added.")
        _new_task(session_id, args.get("request", ""))
        found = load.relevant(args.get("request", ""), load.enabled(None))
        if not found:
            first = (" The person has no ways of working yet: Athos's panel offers them examples for their profession, "
                     "one click each." if not store.all_pieces() and draws_apps() else "")
            return ("No know-how for this request yet. If the task takes several steps, report each with athos_step "
                    "`new`: they draft a new way of working." + first)
        session.update(session_id, task_why={p.id: load.why(args.get("request", ""), p) for p in found})
        pages = {p.id: p for p in store.all_pieces()}
        out = []
        for p in found:
            walk = wiki.walk(p.id, pages)
            out.append(_piece_text(p) + (f"\n\nTrajectory: {' → '.join(walk)}" if len(walk) > 1 else ""))
        load.mark_loaded(session_id, [p.id for p in found])
        conn = load.note_connectors(session_id, found)
        # Said here, in the result the model reads, and not only in the server's instructions: Claude Desktop's chat
        # did not pass those on, and no step was reported (2026-10-30).
        ids = ", ".join(f"{p.id}#{st.id}" for p in found[:2] for st in wiki.statements(p))
        if conn:
            out.append(conn)
        # Composition reached Desktop's chat without the rule for walking it (found in a live check, 2026-10-31).
        if hand := load.handover(found, "athos_show"):
            out.append(hand)
        out.append(ANSWER + "\n\nAs you apply each statement, call athos_step with `step` set to it (once per "
                   f"statement, in the order you apply them, skipping those that don't apply): {ids}. A step the "
                   "task needs that none of them has: athos_step with `new`.")
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
    if name == "athos_library":
        from athos import library
        return library.summary(library.snapshot())
    if name == "athos_library_do":
        from athos import library
        try:
            return json.dumps(library.act(args.get("action", ""), args))
        except (PermissionError, FileNotFoundError, KeyError, TypeError) as e:
            raise ValueError(str(e)) from None
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
    if name == "athos_merge":
        # Deterministic only: the chat's own model can rewrite a statement afterwards with athos_save.
        from athos import guild
        pid = args.get("id", "")
        try:
            variants = guild.find_variants(list(args.get("paths") or []), args.get("as_id") or pid)
        except FileNotFoundError as e:
            raise LookupError(str(e)) from None
        if not variants:
            raise LookupError(f"no copy of {args.get('as_id') or pid} in those paths")
        r = guild.merge(pid, variants)
        out = guild.summary(r)
        if not r["changed"]:
            return out
        if args.get("apply"):
            piece, _ = guild.apply(r)
            return out + f"\n\nSaved as {piece.id} v{piece.version}; the previous version is kept."
        return out + f"\n\nProposal in {guild.write_proposal(r)}. Nothing changed yet: ask the person, then call " \
                     "athos_merge again with apply: true."
    if name == "athos_add":
        from athos import gallery, start
        try:
            r = gallery.add(args.get("id", ""), dry_run=bool(args.get("preview")))
        except OSError as e:
            raise LookupError(f"couldn't reach Athos's gallery ({e}); nothing was added") from None
        return gallery.summary(r, start.lang())
    if name == "athos_start":
        from athos import start
        r = start.from_panel(args.get("lang") or start.lang(), args.get("profile", ""))
        _SETUP.clear()
        return json.dumps(r, ensure_ascii=False)
    if name == "athos_connect":
        from athos import connect, start
        line = connect.connect(args.get("agent", ""), start.lang())
        _SETUP.clear()
        return line
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
            # Claude Desktop writes a server's stderr to its log (mcp-server-Athos.log): say what the host offered.
            print(f"athos mcp: client {json.dumps(params.get('clientInfo'))} capabilities "
                  f"{json.dumps(params.get('capabilities'))}; panel {'on' if draws_apps() else 'off'}", file=sys.stderr)
            result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                      "capabilities": {"tools": {}, "resources": {}, "extensions": {UI_EXTENSION: {}}},
                      "serverInfo": {"name": "athos", "version": "1"}, "instructions": INSTRUCTIONS}
        elif method == "tools/list":
            result = {"tools": tools()}
        elif method == "resources/list":
            result = {"resources": [{"uri": UI_URI, "name": "Athos · trail", "mimeType": UI_MIME,
                                     "description": "The task's walk through the person's know-how, step by step"},
                                    {"uri": LIBRARY_URI, "name": "Athos · library", "mimeType": UI_MIME,
                                     "description": "Every way of working the person has, its versions and results"}]}
        elif method == "resources/read":
            pages = {UI_URI: UI_HTML, LIBRARY_URI: LIBRARY_HTML}
            if params.get("uri") not in pages:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32002, "message": "no such resource"}}
            result = {"contents": [{"uri": params["uri"], "mimeType": UI_MIME, "text": pages[params["uri"]].read_text(),
                                    "_meta": {"ui": {"prefersBorder": True}}}]}
        elif method == "tools/call":
            name = params.get("name", "")
            try:
                text, err = call(name, params.get("arguments") or {}), False
            except (ValueError, LookupError) as e:
                text, err = f"{type(e).__name__}: {e}", True
            result = {"content": [{"type": "text", "text": text}], "isError": err}
            # The panel's state goes where the model doesn't read it: Claude Desktop gave the model
            # structuredContent instead of the text, so it saw steps cut short for the panel and missed what the
            # text asks of it. The panel reads _meta, and asks athos_trail (app-only) for the rest.
            if name == "athos_trail" and not err:
                result["structuredContent"] = panel()
            elif name in ("athos_find", "athos_step", "athos_start", "athos_connect") and not err:
                result["_meta"] = {PANEL_META: panel()}
            elif name == "athos_library" and not err:
                from athos import library                # the page's data, where the model doesn't read it
                result["_meta"] = {LIBRARY_META: library.snapshot()}
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
