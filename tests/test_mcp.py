import io
import json

from athos import mcp, store
from tests.helpers import TempHome

BODY = "## #tag\n**When:** the version is bumped.\n**Do:** `git tag -a v0.3.0 -m 'greet 0.3.0'`.\n"


class McpTest(TempHome):
    def rpc(self, *msgs):
        out = io.StringIO()
        mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_handshake_list_and_find(self):
        store.create("Release the greet package", "releasing greet with a new option", BODY, piece_id="release")
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                     {"jsonrpc": "2.0", "method": "notifications/initialized"},
                     {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                     {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                      "params": {"name": "athos_find", "arguments": {"request": "release greet 0.3.0"}}})
        self.assertEqual([x["id"] for x in r], [1, 2, 3])                       # the notification gets no answer
        self.assertEqual(r[0]["result"]["serverInfo"]["name"], "athos")
        self.assertEqual({t["name"] for t in r[1]["result"]["tools"]},
                         {"athos_find", "athos_step", "athos_show", "athos_list", "athos_save"})
        self.assertIn("git tag -a v0.3.0", r[2]["result"]["content"][0]["text"])

    def test_save_and_errors(self):
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "athos_save", "arguments": {
                          "text": "---\ntitle: Tag a release\nwhen: tagging\n---\n" + BODY}}},
                     {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "athos_save", "arguments": {"text": "no frontmatter"}}},
                     {"jsonrpc": "2.0", "id": 3, "method": "nope"})
        self.assertEqual(r[0]["result"]["content"][0]["text"], "saved tag-a-release")
        self.assertTrue(r[1]["result"]["isError"])
        self.assertEqual(r[2]["error"]["code"], -32601)
        self.assertIsNotNone(store.get("tag-a-release"))


class McpAppTest(TempHome):
    """Claude Desktop's chat: athos_find opens the trail panel (MCP Apps); the agent moves it with athos_step."""

    def rpc(self, *msgs, apps=True):
        caps = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}} if apps else {}
        init = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": caps}}
        out = io.StringIO()
        mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in (init, *msgs))), out)
        return [json.loads(line) for line in out.getvalue().splitlines()][1:]

    def call(self, i, name, **args):
        return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}

    def test_the_panel_is_offered_only_to_hosts_that_draw_it(self):
        tools = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[0]["result"]["tools"]
        find = next(t for t in tools if t["name"] == "athos_find")
        self.assertEqual(find["_meta"]["ui"]["resourceUri"], "ui://athos/trail")
        self.assertEqual(next(t for t in tools if t["name"] == "athos_trail")["_meta"]["ui"]["visibility"], ["app"])
        plain = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, apps=False)[0]["result"]["tools"]
        self.assertNotIn("athos_trail", {t["name"] for t in plain})
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": "ui://athos/trail"}})
        c = r[0]["result"]["contents"][0]
        self.assertEqual(c["mimeType"], "text/html;profile=mcp-app")
        self.assertIn("ui/initialize", c["text"])

    def test_a_task_walks_its_piece_and_the_panel_sees_each_step(self):
        store.create("Release the greet package", "releasing greet with a new option",
                     BODY + "\n## #push-tag\n**Do:** push.\n", piece_id="release")
        r = self.rpc(self.call(1, "athos_find", request="release greet 0.3.0"),
                     self.call(2, "athos_step", step="release#tag"),
                     self.call(3, "athos_step", step="#push-tag"),
                     self.call(4, "athos_step", new="announce it"),
                     self.call(5, "athos_trail"),
                     self.call(6, "athos_step", step="nope"))
        first = r[0]["result"]["structuredContent"]["trail"]["pieces"][0]
        self.assertEqual([s["state"] for s in first["steps"]], ["ahead", "ahead"])
        t = r[4]["result"]["structuredContent"]["trail"]
        self.assertEqual([(s["id"], s["state"]) for s in t["pieces"][0]["steps"]], [("tag", "done"), ("push-tag", "now")])
        self.assertEqual(t["new"], ["announce it"])
        self.assertTrue(r[5]["result"]["isError"])
        self.assertNotIn("structuredContent", r[5]["result"])
        again = self.rpc(self.call(1, "athos_find", request="something unrelated"))[0]["result"]
        self.assertEqual(again["structuredContent"]["trail"]["pieces"], [])            # a new request, a new trail


class DesktopTest(TempHome):
    def test_the_bundle_runs_athos_mcp_and_carries_the_panel(self):
        import zipfile
        from pathlib import Path
        from athos import desktop
        out = desktop.pack(Path(self.home) / "athos.mcpb")
        with zipfile.ZipFile(out) as z:
            names = set(z.namelist())
            m = json.loads(z.read("manifest.json"))
        self.assertTrue({"bin/athos", "athos/mcp/__init__.py", "athos/mcp/trail.html"} <= names)
        self.assertFalse(any("__pycache__" in n for n in names))
        self.assertEqual(m["server"]["mcp_config"]["args"], ["${__dirname}/bin/athos", "mcp"])
        self.assertNotIn("athos_trail", {t["name"] for t in m["tools"]})

    def test_the_panel_speaks_the_language_the_person_writes_in(self):
        from athos import mcp as m
        m.call("athos_find", {"request": "quiero que revises este contrato de locación, por favor"})
        self.assertEqual(m.panel()["lang"], "es")

    def test_find_tells_the_model_which_steps_to_report(self):
        from athos import mcp as m
        store.create("Release the greet package", "releasing greet with a new option", BODY, piece_id="release")
        self.assertIn("athos_step with `step`", m.call("athos_find", {"request": "release greet 0.3.0"}))
        self.assertIn("release#tag", m.call("athos_find", {"request": "release greet 0.3.0"}))
