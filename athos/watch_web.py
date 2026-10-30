"""`athos watch --web`: Athos's trail panel as a local page, beside any agent that has no room for it (Muse Code,
Codex, OpenCode in the terminal). The same page Claude Desktop draws (athos/mcp/trail.html), hosted here: it follows
the task of this folder's latest session, step by step. Served on 127.0.0.1 only; nothing leaves the machine.

The page's buttons can't type into a terminal agent, so [Change this step] and [Save] copy their request to the
clipboard for the person to paste."""

from __future__ import annotations

import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from athos import mcp

HOST_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Athos</title>
<style>
  :root { --bg: #f5f4ef; --fg: #1f1f1f; --dim: #6b6b6b; }
  @media (prefers-color-scheme: dark) { :root { --bg: #1f1e1d; --fg: #f0eee6; --dim: #a6a39a; } }
  html, body { margin: 0; background: var(--bg); color: var(--fg); font: 14px/1.5 -apple-system, system-ui, sans-serif; }
  main { max-width: 760px; margin: 24px auto; padding: 0 16px; }
  iframe { width: 100%; border: 0; border-radius: 12px; background: transparent; min-height: 120px; display: block;
    box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  #toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #1f1f1f; color: #fff;
    padding: 8px 14px; border-radius: 8px; font-size: 13px; opacity: 0; transition: opacity .2s; }
  #toast.on { opacity: 1; }
</style></head>
<body><main><iframe id="v" src="/trail.html" title="Athos"></iframe></main><div id="toast"></div>
<script>
// A minimal MCP Apps host for the trail panel: it answers the panel's handshake, serves athos_trail from this
// folder's session, and turns the panel's messages into the clipboard (a terminal agent can't receive them).
const v = document.getElementById('v');
const dark = matchMedia('(prefers-color-scheme: dark)').matches;
const reply = (id, result) => v.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
function toast(t) { const e = document.getElementById('toast'); e.textContent = t; e.classList.add('on');
  setTimeout(() => e.classList.remove('on'), 2600); }
window.addEventListener('message', async e => {
  const m = e.data; if (!m || m.jsonrpc !== '2.0') return;
  if (m.method === 'ui/initialize') reply(m.id, { protocolVersion: '2025-06-18', hostInfo: { name: 'athos-watch' },
    hostCapabilities: { serverTools: {} }, hostContext: { theme: dark ? 'dark' : 'light', displayMode: 'inline',
    availableDisplayModes: ['inline'] } });
  else if (m.method === 'tools/call') reply(m.id, await (await fetch('/trail')).json());
  else if (m.method === 'ui/message') {
    const text = m.params.content.text, es = /^Athos · (ajustar|guardar)/.test(text);
    try { await navigator.clipboard.writeText(text); toast(es ? 'Copiado: pegalo en tu agente' : 'Copied: paste it in your agent'); }
    catch (err) { toast((es ? 'Pegá en tu agente: ' : 'Paste in your agent: ') + text); }
    reply(m.id, {});
  } else if (m.method === 'ui/request-display-mode') reply(m.id, { mode: 'inline' });
  else if (m.method === 'ui/notifications/size-changed' && m.params.height) v.style.height = m.params.height + 'px';
});
</script></body></html>
"""


def session_for(cwd: str) -> str | None:
    """The latest session of an agent working in this folder (every agent's hooks record it)."""
    from athos import cli
    return cli._current_session(cwd).get("session_id")


def handler_for(cwd: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, body: str, ctype: str) -> None:
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/trail.html":
                return self._send(mcp.UI_HTML.read_text(), "text/html; charset=utf-8")
            if self.path == "/trail":
                sid = session_for(cwd)
                state = mcp.panel(sid) if sid else mcp.panel("__none__")
                return self._send(json.dumps({"structuredContent": state}, ensure_ascii=False), "application/json")
            if self.path in ("/", "/index.html"):
                return self._send(HOST_PAGE, "text/html; charset=utf-8")
            self.send_error(404)
    return Handler


def serve(cwd: str | None = None, port: int = 8711, open_browser: bool = True) -> int:
    cwd = os.path.realpath(cwd or os.getcwd())
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), handler_for(cwd))
            break
        except OSError:
            continue
    else:
        raise SystemExit("athos watch --web: no free port")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"athos · {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
