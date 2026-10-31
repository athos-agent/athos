"""`athos library`: every way of working the person has, at a glance, as one local page. The list (what each one is
for, how often it was used and how it went, in which agents and models, its last improvement), one page opened (its
steps with their branches, its versions, [Go back to this version], [Open in editor]) and what each agent and model
gave the person. The same page is Claude Desktop's `ui://athos/library` (an MCP App, athos/mcp).

Served on 127.0.0.1 only; nothing leaves the machine. The two actions that change something (go back to a version,
open the file) are POSTs that need this run's random token, which only the page served here carries, and every
request must name this server as its Host, so another site open in the browser can neither call them nor read the
know-how (a page elsewhere can't read the token; a DNS-rebound name fails the Host check)."""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from athos import eval as ev, paths, store, trail, wiki

HTML = Path(__file__).with_name("library.html")
LABELS = {**dict(ev.AGENTS), "claude-desktop": "Claude Desktop", "local": "local model", "meta": "Meta Model API"}
HISTORY_LINE = re.compile(r"^v(\d+)\s+(\S+)(?:\s+\(([^)]*)\))?:\s*(.*)$")


def _history(p: store.Piece) -> list[dict]:
    """The piece's versions, newest first, from its `## History`; a version can be gone back to when it is older
    than the current one and its copy is kept in `.history/`."""
    arch = paths.history() / p.id
    kept = {f.name for f in arch.glob("v*.md")} if arch.is_dir() else set()
    out = []
    for line in p.history:
        m = HISTORY_LINE.match(line)
        if not m:
            continue
        n = int(m.group(1))
        out.append({"version": n, "date": m.group(2), "by": m.group(3) or "", "note": m.group(4),
                    "current": n == p.version, "can_go_back": n < p.version and f"v{n}.md" in kept})
    return out


def _steps(p: store.Piece, pages: dict[str, store.Piece], stmts: dict[str, list]) -> list[dict]:
    """The steps as the panel draws them (athos/trail.py `view`): a step that hands over to another page with
    **Calls:** / **If:** shows that page's steps right under it, marked ↳, the first one with the If's condition."""
    def row(s, depth=0):
        d = {"id": s.id, "label": trail.label(s.when, s.do, s.id), "when": s.when[:200], "do": s.do[:400],
             "because": s.because[:300], "depth": depth}
        return {**d, "piece": s.page} if depth else d

    out = []
    for s in stmts[p.id]:
        out.append(row(s))
        for c in s.calls:
            if c["page"] not in pages or c["page"] == p.id:
                continue
            subs = stmts[c["page"]]
            if c["statement"]:
                subs = subs[next((i for i, x in enumerate(subs) if x.id == c["statement"]), 0):]
            for i, sub in enumerate(subs):
                r = row(sub, 1)
                if i == 0 and c["if"]:
                    r["if"] = c["if"]
                out.append(r)
    return out


def snapshot() -> dict:
    """Everything the library page shows, from the store and the event log, read once. Used by the local page and
    by Claude Desktop's athos_library."""
    from athos import start
    pieces = store.all_pieces()
    pages = {p.id: p for p in pieces}
    stmts = {p.id: wiki.statements(p) for p in pieces}
    tasks = ev.tasks()

    # One pass over the tasks: per piece, how often it was used, how it went, where and on what.
    rec: dict[str, dict] = {}
    for t in tasks:
        for pid in t.get("pieces") or []:
            r = rec.setdefault(pid, {"uses": 0, "ok": 0, "corrected": 0, "failed": 0, "agents": set(),
                                     "models": set(), "last": ""})
            r["uses"] += 1
            if t["result"] in ("ok", "corrected", "failed"):
                r[t["result"]] += 1
            if t.get("platform"):
                r["agents"].add(LABELS.get(t["platform"], t["platform"]))
            if t.get("model") and t["model"] != "unknown":
                r["models"].add(t["model"])
            r["last"] = max(r["last"], (t.get("ended") or "")[:10])

    # Who hands over to whom: a page another page's **Calls:** / **If:** leads to is reached through it.
    reached: dict[str, list[dict]] = {}
    for p in pieces:
        for s in stmts[p.id]:
            for c in s.calls:
                if c["page"] in pages and c["page"] != p.id and \
                        not any(x["id"] == p.id for x in reached.get(c["page"], [])):
                    reached.setdefault(c["page"], []).append({"id": p.id, "title": p.title, "if": c["if"]})

    rows = []
    for p in pieces:
        r = rec.get(p.id) or {"uses": 0, "ok": 0, "corrected": 0, "failed": 0, "agents": set(), "models": set(),
                              "last": ""}
        hist = _history(p)
        rows.append({"id": p.id, "title": p.title, "when": p.when, "version": p.version,
                     "uses": r["uses"], "ok": r["ok"], "corrected": r["corrected"], "failed": r["failed"],
                     "agents": sorted(r["agents"]), "models": sorted(r["models"]),
                     "last_used": max(r["last"], p.last_used or ""), "created": p.created,
                     "last_change": hist[0] if hist else None, "history": hist,
                     "reached_from": reached.get(p.id, []), "steps": _steps(p, pages, stmts),
                     "file": str(p.path)})
    rows.sort(key=lambda x: (x["last_used"], x["uses"]), reverse=True)

    # What each agent and model gave: the rows `athos report` computes, from the same tasks.
    gave = []
    for (platform, model) in sorted({(t.get("platform", "unknown"), t.get("model", "unknown")) for t in tasks}):
        mt = [t for t in tasks if (t.get("platform", "unknown"), t.get("model", "unknown")) == (platform, model)]
        marked = [t for t in mt if t["result"] != "unevaluated"]
        gave.append({"agent": LABELS.get(platform, platform), "model": model, "tasks": len(mt),
                     "with_know_how": sum(1 for t in mt if t["pieces"]), "marked": len(marked),
                     "ok": sum(1 for t in marked if t["result"] == "ok"),
                     "success_rate": (sum(1 for t in marked if t["result"] == "ok") / len(marked)) if marked else None,
                     "mean_duration_s": ev._mean([t.get("duration_s") for t in mt]),
                     "mean_tokens": ev._mean([ev._tok(t) for t in mt])})
    gave.sort(key=lambda g: g["tasks"], reverse=True)
    return {"lang": start.lang(), "home": str(paths.know_how()), "pieces": rows, "gave": gave,
            "tasks": len(tasks), "marked": sum(1 for t in tasks if t["result"] != "unevaluated")}


def summary(snap: dict) -> str:
    """What the model reads when the library opens in the chat: a line, not the data (the page has that)."""
    n = len(snap["pieces"])
    return (f"The person's library is open in the panel: {n} way{'s' if n != 1 else ''} of working, "
            f"{snap['tasks']} task(s) recorded. Don't repeat it; answer only what they ask about it.")


# ------------------------------------------------------------------------------------------------ actions
def go_back(piece_id: str, version: int) -> store.Piece:
    """[Go back to this version]: that version comes back as a new one; the history keeps every version."""
    return store.revert(piece_id, int(version))


def _under_know_how(path: Path) -> bool:
    root = paths.know_how().resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return path.suffix == ".md" and path.resolve().is_file()


def opener(path: str) -> None:
    """Open a file with the system's default app. Replaced in tests."""
    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_in_editor(piece_id: str) -> Path:
    """[Open in editor]: the piece's markdown file, and only a file inside the know-how folder."""
    path = paths.know_how() / f"{piece_id}.md"
    if not piece_id or not _under_know_how(path):
        raise PermissionError(f"not a page of your know-how: {piece_id!r}")
    opener(str(path.resolve()))
    return path


def act(action: str, args: dict) -> dict:
    """One action from the page (here or in Claude Desktop): `revert` (id, version) or `open` (id)."""
    if action == "revert":
        p = go_back(str(args.get("id", "")), args.get("version"))
        return {"ok": True, "id": p.id, "version": p.version}
    if action == "open":
        open_in_editor(str(args.get("id", "")))
        return {"ok": True}
    raise ValueError(f"unknown action {action!r}")


# ------------------------------------------------------------------------------------------------ the local page
def handler_for(token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, code: int, body: str, ctype: str = "application/json") -> None:
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self) -> bool:
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._send(403, '{"error": "wrong host"}')
            if self.path in ("/", "/index.html"):
                return self._send(200, HTML.read_text().replace("__ATHOS_TOKEN__", token), "text/html; charset=utf-8")
            if self.path == "/api/library":
                return self._send(200, json.dumps(snapshot(), ensure_ascii=False))
            self._send(404, '{"error": "not found"}')

        def do_POST(self):  # noqa: N802
            if not self._host_ok() or not secrets.compare_digest(self.headers.get("X-Athos-Token", ""), token):
                return self._send(403, '{"error": "refused"}')
            action = {"/api/revert": "revert", "/api/open": "open"}.get(self.path)
            if not action:
                return self._send(404, '{"error": "not found"}')
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 10_000)
                args = json.loads(self.rfile.read(n) or b"{}")
                return self._send(200, json.dumps(act(action, args if isinstance(args, dict) else {})))
            except PermissionError as e:
                return self._send(403, json.dumps({"error": str(e)}))
            except (KeyError, FileNotFoundError, ValueError, TypeError) as e:
                return self._send(400, json.dumps({"error": str(e)}))
    return Handler


def serve(port: int = 8712, open_browser: bool = True) -> int:
    token = secrets.token_urlsafe(24)                    # a new one each run
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), handler_for(token))
            break
        except OSError:
            continue
    else:
        raise SystemExit("athos library: no free port")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"athos library · {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
