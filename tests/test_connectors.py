import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from athos import connectors, load, mcp, session, store, trail
from tests.helpers import TempHome

BODY = ("## #data_out\n**When:** before opening the contract.\n**Do:** if it holds client data, run the task through "
        "[[connector:pii-guard]].\n\n## #summary\n**Do:** summarise it in five lines.\n")


class Ok(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_):
        pass


class ConnectorsTest(TempHome):
    def piece(self):
        return store.create("Review a contract", "review a lease contract", BODY, piece_id="contract")

    def up(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Ok)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/v1/status"

    def set_check(self, url):
        f = connectors.add("pii-guard")
        f.write_text(connectors.TEMPLATES["pii-guard"].replace("http://127.0.0.1:8787/v1/status", url))

    def test_a_piece_names_its_connector_and_athos_checks_it(self):
        p = self.piece()
        self.assertEqual(connectors.named_in([p]), ["pii-guard"])
        self.assertEqual(connectors.status([p])[0]["set_up"], False)          # not added yet
        self.set_check(self.up())
        s = connectors.status([p])[0]
        self.assertTrue(s["active"])
        self.assertIn("Keep every placeholder exactly as it is", connectors.model_text([s]))
        self.set_check("http://127.0.0.1:9/v1/status")                       # nothing listens there
        s = connectors.status([p])[0]
        self.assertFalse(s["active"])
        self.assertIn("don't process it", connectors.model_text([s]))

    def test_the_request_tells_the_model_and_the_panel_shows_it(self):
        self.piece()
        self.set_check(self.up())
        text = load.on_prompt({"session_id": "c1", "cwd": self.home, "prompt": "review this lease contract please"})
        self.assertIn("pii-guard is active", text)
        view = trail.view(session.load("c1"))
        self.assertEqual(view["connectors"][0]["name"], "pii-guard")
        self.assertTrue(view["connectors"][0]["active"])

    def test_desktop_find_carries_the_connector_too(self):
        self.piece()
        self.set_check("http://127.0.0.1:9/v1/status")
        text = mcp.call("athos_find", {"request": "review this lease contract please"})
        self.assertIn("pii-guard is not running", text)
        self.assertFalse(mcp.panel()["trail"]["connectors"][0]["active"])
