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
                         {"athos_find", "athos_show", "athos_list", "athos_save"})
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
