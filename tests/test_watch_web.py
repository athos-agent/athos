import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from athos import cli, session, store, watch_web
from tests.helpers import TempHome

BODY = "## #bump\n**When:** starting.\n**Do:** bump the version.\n\n## #tag\n**Do:** tag it.\n"


class WatchWebTest(TempHome):
    def serve(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), watch_web.handler_for(self.home))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def get(self, url):
        with urllib.request.urlopen(url) as r:
            return r.read().decode()

    def test_the_page_hosts_the_panel_and_follows_this_folders_session(self):
        store.create("Cut a release", "cut a release", BODY, piece_id="release")
        cli._remember_session({"session_id": "m1", "cwd": self.home})
        session.update("m1", task_id="t1", task_loaded=["release"], task_request="cut a release please",
                       trail=[{"kind": "step", "piece": "release", "step": "bump", "done": False}])
        base = self.serve()
        self.assertIn('src="/trail.html"', self.get(base + "/"))
        self.assertIn("ui/initialize", self.get(base + "/trail.html"))
        t = json.loads(self.get(base + "/trail"))["structuredContent"]["trail"]
        self.assertEqual([(s["id"], s["state"]) for s in t["pieces"][0]["steps"]], [("bump", "now"), ("tag", "ahead")])

    def test_with_no_session_the_page_waits(self):
        t = json.loads(self.get(self.serve() + "/trail"))["structuredContent"]["trail"]
        self.assertFalse(t["busy"])

    def test_every_agent_is_asked_to_answer_plainly(self):
        from athos import load
        p = store.create("Cut a release", "cut a release", BODY, piece_id="release")
        self.assertIn("Don't narrate tools", load.inject_text([p]))

    def test_the_trail_reads_in_a_terminal_too(self):
        from athos import watch
        store.create("Cut a release", "cut a release", BODY, piece_id="release")
        cli._remember_session({"session_id": "m2", "cwd": self.home})
        session.update("m2", task_id="t2", task_loaded=["release"], task_request="cut a release please",
                       trail=[{"kind": "step", "piece": "release", "step": "bump", "done": False}])
        text = watch.trail_frame(self.home, color=False)
        self.assertIn("I'm following «Cut a release».", text)
        self.assertIn("▶ Bump the version", text)
        self.assertIn("○ Tag it", text)
