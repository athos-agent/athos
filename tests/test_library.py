import io
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from athos import eval as ev, library, mcp, paths, store
from tests.helpers import TempHome

REVIEW = ("## #read\n**When:** the contract is open.\n**Do:** Read it whole before commenting.\n\n"
          "## #data\n**Do:** Check what personal data it handles.\n"
          "**If:** it processes personal data → [[data-clause]]\n\n"
          "## #sum\n**Do:** Summarise in five lines.\n**Calls:** [[house-style#tone]]\n")
CLAUSE = "## #draft\n**Do:** Draft the data protection clause.\n\n## #check\n**Do:** Check the retention period.\n"
STYLE = "## #intro\n**Do:** Open with the client's name.\n\n## #tone\n**Do:** Keep a plain, formal tone.\n"


def task(tid, platform, model, pieces, result=None):
    ev.append({"type": "task_start", "task_id": tid, "platform": platform, "model": model, "at": "2026-10-30T10:00:00"})
    ev.append({"type": "task_end", "task_id": tid, "at": "2026-10-30T10:01:00", "duration_s": 60,
               "tokens": {"total": 1000}, "model": model, "pieces": pieces, "saved": []})
    if result:
        ev.append({"type": "mark", "task_id": tid, "result": result})


class LibraryTest(TempHome):
    def setUp(self):
        super().setUp()
        store.create("Review a services contract", "reviewing a services contract", REVIEW, piece_id="review")
        store.create("Data protection clause", "a contract processes personal data", CLAUSE, piece_id="data-clause")
        store.create("House style", "writing for a client", STYLE, piece_id="house-style")
        store.update("review", "added the data protection branch")
        task("t1", "claude-code", "claude-opus-5-5", ["review"], "ok")
        task("t2", "claude-code", "claude-opus-5-5", ["review"], "corrected")
        task("t3", "codex", "gpt-6.1-sol", ["review"], "failed")
        task("t4", "codex", "gpt-6.1-sol", [])

    def test_snapshot_lists_each_way_of_working_with_how_it_went(self):
        s = library.snapshot()
        by = {p["id"]: p for p in s["pieces"]}
        r = by["review"]
        self.assertEqual((r["uses"], r["ok"], r["corrected"], r["failed"]), (3, 1, 1, 1))
        self.assertEqual(r["agents"], ["Claude Code", "Codex"])
        self.assertEqual(r["models"], ["claude-opus-5-5", "gpt-6.1-sol"])
        self.assertEqual((r["last_change"]["version"], r["last_change"]["note"]), (2, "added the data protection branch"))
        self.assertEqual([(h["version"], h["can_go_back"]) for h in r["history"]], [(2, False), (1, True)])
        self.assertEqual(s["pieces"][0]["id"], "review")                       # the one used, first
        # Pages reached through another page's If / Calls say so, with the condition.
        self.assertEqual(by["data-clause"]["reached_from"],
                         [{"id": "review", "title": "Review a services contract", "if": "it processes personal data"}])
        self.assertEqual(by["house-style"]["reached_from"][0]["if"], "")
        self.assertEqual(r["reached_from"], [])
        # Its steps, with the branches nested under the step that leads there.
        steps = [(x["id"], x["depth"], x.get("if")) for x in r["steps"]]
        self.assertEqual(steps, [("read", 0, None), ("data", 0, None), ("draft", 1, "it processes personal data"),
                                 ("check", 1, None), ("sum", 0, None), ("tone", 1, None)])
        # What each agent and model gave.
        gave = {(g["agent"], g["model"]): g for g in s["gave"]}
        self.assertEqual(gave[("Codex", "gpt-6.1-sol")]["tasks"], 2)
        self.assertEqual(gave[("Codex", "gpt-6.1-sol")]["with_know_how"], 1)
        self.assertEqual(gave[("Claude Code", "claude-opus-5-5")]["success_rate"], 0.5)
        self.assertEqual((s["tasks"], s["marked"]), (4, 3))

    def test_a_full_library_answers_in_under_a_second(self):
        import time
        for i in range(70):
            store.create(f"Way of working {i}", f"task number {i}", REVIEW, piece_id=f"w{i}")
        for i in range(700):                                               # ~2,000 events
            task(f"x{i}", "claude-code", "claude-opus-5-5", [f"w{i % 70}"], "ok" if i % 3 else None)
        t = time.perf_counter()
        s = library.snapshot()
        self.assertLess(time.perf_counter() - t, 1.0)
        self.assertEqual(len(s["pieces"]), 73)

    def test_going_back_to_a_version_makes_a_new_one_and_keeps_every_version(self):
        store.update("review", "a third version", body=REVIEW + "\n## #extra\n**Do:** extra.\n")
        p = store.revert("review", to=1)
        self.assertEqual(p.version, 4)
        self.assertEqual(p.history[0].split(":")[1].strip(), "reverted to v1")
        self.assertEqual(sorted(f.name for f in (paths.history() / "review").iterdir()), ["v1.md", "v2.md", "v3.md"])
        with self.assertRaises(FileNotFoundError):
            store.revert("review", to=4)                                   # not an earlier version
        self.assertEqual(store.revert("review").version, 5)                 # the plain revert still works


class LibraryServerTest(TempHome):
    def setUp(self):
        super().setUp()
        store.create("Review a services contract", "reviewing a services contract", REVIEW, piece_id="review")
        store.update("review", "second")
        self.opened = []
        old, library.opener = library.opener, self.opened.append
        self.addCleanup(setattr, library, "opener", old)
        server = ThreadingHTTPServer(("127.0.0.1", 0), library.handler_for("secret-token"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def req(self, path, data=None, headers=None):
        r = urllib.request.Request(self.base + path, headers=headers or {},
                                   data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(r) as x:
                return x.status, x.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_the_page_carries_this_runs_token_and_the_data(self):
        code, html = self.req("/")
        self.assertEqual(code, 200)
        self.assertIn('content="secret-token"', html)
        code, body = self.req("/api/library")
        self.assertEqual(json.loads(body)["pieces"][0]["id"], "review")

    def test_revert_through_the_page_creates_a_new_version(self):
        code, body = self.req("/api/revert", {"id": "review", "version": 1}, {"X-Athos-Token": "secret-token"})
        self.assertEqual((code, json.loads(body)["version"]), (200, 3))
        p = store.get("review")
        self.assertEqual(p.version, 3)
        self.assertTrue(p.history[0].endswith("reverted to v1"))
        self.assertEqual(len(p.history), 3)                                 # nothing taken out of the history
        self.assertTrue((paths.history() / "review" / "v2.md").is_file())

    def test_actions_need_the_token_and_this_host(self):
        for headers in ({}, {"X-Athos-Token": "wrong"}):
            self.assertEqual(self.req("/api/revert", {"id": "review", "version": 1}, headers)[0], 403)
            self.assertEqual(self.req("/api/open", {"id": "review"}, headers)[0], 403)
        self.assertEqual(store.get("review").version, 2)
        self.assertEqual(self.opened, [])
        # A name rebound to 127.0.0.1 by another site is refused, reads included.
        self.assertEqual(self.req("/api/library", headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.req("/api/revert", {"id": "review", "version": 1},
                                  {"X-Athos-Token": "secret-token", "Host": "attacker.example"})[0], 403)

    def test_open_only_opens_files_of_the_know_how(self):
        (paths.home() / "notes.md").write_text("not a page")
        for bad in ("../notes", "../events", "/etc/passwd", "", "nope"):
            code, _ = self.req("/api/open", {"id": bad}, {"X-Athos-Token": "secret-token"})
            self.assertEqual(code, 403, bad)
        self.assertEqual(self.opened, [])
        code, _ = self.req("/api/open", {"id": "review"}, {"X-Athos-Token": "secret-token"})
        self.assertEqual(code, 200)
        self.assertEqual(self.opened, [str((paths.know_how() / "review.md").resolve())])


class LibraryAppTest(TempHome):
    """Claude Desktop's chat: athos_library opens the library page; its buttons go through athos_library_do."""

    def rpc(self, *msgs):
        init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
                "capabilities": {"extensions": {mcp.UI_EXTENSION: {"mimeTypes": [mcp.UI_MIME]}}}}}
        out = io.StringIO()
        mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in (init, *msgs))), out)
        return [json.loads(line) for line in out.getvalue().splitlines()][1:]

    def call(self, i, name, **args):
        return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}

    def test_the_library_opens_in_the_chat_and_goes_back_a_version(self):
        store.create("Review a services contract", "reviewing a services contract", REVIEW, piece_id="review")
        store.update("review", "second")
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                     {"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": "ui://athos/library"}},
                     self.call(3, "athos_library"),
                     self.call(4, "athos_library_do", action="revert", id="review", version=1),
                     self.call(5, "athos_library_do", action="open", id="../events"))
        tools = {t["name"]: t for t in r[0]["result"]["tools"]}
        self.assertEqual(tools["athos_library"]["_meta"]["ui"]["resourceUri"], "ui://athos/library")
        self.assertEqual(tools["athos_library_do"]["_meta"]["ui"]["visibility"], ["app"])
        self.assertIn("athos-library", r[1]["result"]["contents"][0]["text"])
        self.assertEqual(r[2]["result"]["_meta"]["athos/library"]["pieces"][0]["id"], "review")
        self.assertNotIn("structuredContent", r[2]["result"])                    # the model reads one line
        self.assertEqual(json.loads(r[3]["result"]["content"][0]["text"])["version"], 3)
        self.assertTrue(r[4]["result"]["isError"])
        self.assertEqual(store.get("review").version, 3)

    def test_the_desktop_manifest_leaves_the_pages_tools_out(self):
        from athos import desktop
        names = {t["name"] for t in desktop.manifest()["tools"]}
        self.assertIn("athos_library", names)
        self.assertNotIn("athos_library_do", names)
