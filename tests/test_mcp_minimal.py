"""Claude Desktop's chat in the minimal interface (the default): athos_find opens Athos's panel in a minimal form whose
header is the one state (indicator.chat: collaborating, learning or idle), with the piece's steps or the steps being
drafted under it, and the two buttons the person teaches with. The person's press writes their own piece (athos_keep,
app-only); the model's athos_save still saves nothing. All data here is synthetic."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from athos import control, indicator, mcp, session, store
from athos import eval as ev
from tests.helpers import TempHome

ROOT = Path(__file__).resolve().parents[1]
BODY = ("## #tag\n**When:** the version is bumped.\n**Do:** tag the release.\n\n"
        "## #push-tag\n**Do:** push the tag.\n")
APPS = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}


def ui_events():
    return [(e["from"], e["state"], e["why"]) for e in ev.events() if e.get("type") == "ui"]


class MinimalChatTest(TempHome):
    def rpc(self, *msgs, apps=True):
        init = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": APPS if apps else {}}}
        out = io.StringIO()
        mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in (init, *msgs))), out)
        return [json.loads(line) for line in out.getvalue().splitlines()][1:]

    def call(self, i, name, **args):
        return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}

    def trail(self):
        return self.rpc(self.call(1, "athos_trail"))[0]["result"]["structuredContent"]

    def release(self):
        return store.create("Release the greet package", "releasing greet with a new option", BODY,
                            piece_id="release")

    # ------------------------------------------------------------------------------------------------ the tools
    def test_find_opens_the_minimal_panel_and_done_opens_none(self):
        tools = {t["name"]: t for t in self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[0]["result"]["tools"]}
        self.assertEqual(tools["athos_find"]["_meta"]["ui"]["resourceUri"], mcp.UI_URI)
        self.assertNotIn("_meta", tools["athos_done"])
        self.assertEqual(tools["athos_keep"]["_meta"]["ui"]["visibility"], ["app"])       # the person's, never the model's
        plain = {t["name"] for t in self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                             apps=False)[0]["result"]["tools"]}
        self.assertFalse({"athos_keep", "athos_trail", "athos_rate"} & plain)
        self.classic()
        tools = {t["name"]: t for t in self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[0]["result"]["tools"]}
        self.assertNotIn("athos_keep", tools)                                   # the classic panel has no such button
        self.assertEqual(tools["athos_done"]["_meta"]["ui"]["resourceUri"], mcp.UI_URI)

    def test_the_page_knows_its_interface_and_the_model_is_not_asked_to_save(self):
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": mcp.UI_URI}})
        self.assertIn('<html data-ui="minimal">', r[0]["result"]["contents"][0]["text"])
        out = io.StringIO()
        mcp.serve(io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}) + "\n"), out)
        said = json.loads(out.getvalue())["result"]["instructions"]
        self.assertEqual(said, mcp.INSTRUCTIONS_MINIMAL)
        self.assertNotIn("call athos_save once", said)
        self.classic()
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": mcp.UI_URI}})
        self.assertEqual(r[0]["result"]["contents"][0]["text"], mcp.UI_HTML.read_text())    # classic: as before

    def test_the_page_draws_the_mark_in_both_languages(self):
        html = mcp.UI_HTML.read_text()
        for words in ("Athos is collaborating", "Athos está colaborando", "Athos is learning", "Athos está aprendiendo",
                      "Change this step", "Cambiar este paso", "Save as a way of working",
                      "Guardar como forma de trabajar", "'athos_keep'", "■"):
            self.assertIn(words, html)

    # ------------------------------------------------------------------------------------------- the one state
    def test_the_state_moves_with_the_task_and_is_recorded_when_it_changes(self):
        self.release()
        r = self.rpc(self.call(1, "athos_find", request="write a haiku about autumn"))
        idle = r[0]["result"]["_meta"]["athos/panel"]
        self.assertEqual(idle["indicator"], {"state": "idle", "why": "nothing_in_use"})
        self.assertEqual((idle["trail"]["pieces"], idle["trail"]["new"], idle["can_save"]), ([], [], False))
        self.assertNotIn("The person has no ways of working yet", r[0]["result"]["content"][0]["text"])

        r = self.rpc(self.call(1, "athos_step", new="pick the season's words"),
                     self.call(2, "athos_step", new="count the syllables"))
        learning = r[1]["result"]["_meta"]["athos/panel"]
        self.assertEqual(learning["indicator"], {"state": "learning", "why": "drafting_steps"})
        self.assertEqual(learning["trail"]["new"], ["pick the season's words", "count the syllables"])
        self.assertTrue(learning["can_save"])

        r = self.rpc(self.call(1, "athos_find", request="release greet 0.3.0"),
                     self.call(2, "athos_step", step="release#tag"),
                     self.call(3, "athos_step", new="announce it"))
        found = r[0]["result"]["_meta"]["athos/panel"]
        self.assertEqual(found["indicator"], {"state": "collaborating", "why": "piece_found"})
        both = r[2]["result"]["_meta"]["athos/panel"]
        self.assertEqual(both["indicator"]["state"], "collaborating")              # collaborating wins
        p = both["trail"]["pieces"][0]
        self.assertEqual((p["title"], [(s["id"], s["state"]) for s in p["steps"]]),
                         ("Release the greet package", [("tag", "now"), ("push-tag", "ahead")]))
        self.assertTrue(both["can_adjust"])

        self.rpc(self.call(1, "athos_done", outcome="tagged"))
        done = self.trail()
        self.assertEqual(done["indicator"], {"state": "idle", "why": "between_tasks"})
        self.assertEqual(done["trail"]["pieces"], [])
        self.assertEqual(ui_events(), [("idle", "learning", "drafting_steps"), ("learning", "collaborating", "piece_found"),
                                       ("collaborating", "idle", "between_tasks")])
        self.assertEqual(self.trail()["indicator"]["state"], "idle")
        self.assertEqual(len(ui_events()), 3)                                    # a poll that changes nothing records nothing

    def test_the_chat_state_by_hand(self):
        st = {"task_id": "t1", "task_end": None, "trail": [], "task_why": {}}
        self.assertEqual(indicator.chat({}), ("idle", "no_task"))
        self.assertEqual(indicator.chat(st), ("idle", "nothing_in_use"))
        self.assertEqual(indicator.chat({**st, "trail": [{"kind": "new", "text": "x"}]}), ("learning", "drafting_steps"))
        self.assertEqual(indicator.chat({**st, "trail": [{"kind": "step", "piece": "a", "step": "s"}]}, allowed={"b"}),
                         ("idle", "nothing_in_use"))               # a step on a piece that may not be named: nothing
        self.assertEqual(indicator.chat({**st, "task_why": {"a": []}, "trail": [{"kind": "new", "text": "x"}]}),
                         ("collaborating", "piece_found"))
        self.assertEqual(indicator.chat({**st, "task_end": {"task_id": "t1"}, "task_why": {"a": []}}),
                         ("idle", "between_tasks"))
        self.assertEqual(indicator.chat({**st, "chat_saving": 1.0}), ("learning", "saving"))
        session.save("old", {**st, "task_why": {"a": []}})
        os.utime(session._file("old"), (1, 1))
        self.assertEqual(indicator.chat(session.load("old"), "old"), ("idle", "stale_task"))

    def test_the_minimal_payload_leaves_out_the_rest(self):
        self.release()
        r = self.rpc(self.call(1, "athos_find", request="release greet 0.3.0"), self.call(2, "athos_trail"))
        for s in (r[0]["result"]["_meta"]["athos/panel"], r[1]["result"]["structuredContent"]):
            self.assertEqual(s["ui"], "minimal")
            for gone in ("greeting", "setup", "moment", "related", "pieces", "save_prompt", "learned"):
                self.assertNotIn(gone, s)
            self.assertFalse({"why", "record", "see", "when"} & set(s["trail"]["pieces"][0]))
            self.assertFalse({"beside", "edits", "connectors", "request"} & set(s["trail"]))
        self.assertNotIn("Ratings:", r[0]["result"]["content"][0]["text"])        # no stars to explain
        self.classic()
        classic = self.trail()
        self.assertTrue({"greeting", "setup", "moment"} <= set(classic))

    def test_spanish_and_english(self):
        r = self.rpc(self.call(1, "athos_find", request="Revisá este contrato de locación antes de que lo firme"),
                     self.call(2, "athos_step", new="leer las cláusulas"))
        s = r[1]["result"]["_meta"]["athos/panel"]
        self.assertEqual((s["lang"], s["adjust_prefix"]), ("es", "Athos · ajustar"))
        r = self.rpc(self.call(1, "athos_find", request="Please review this lease before my client signs it"))
        self.assertEqual(r[0]["result"]["_meta"]["athos/panel"]["lang"], "en")

    # ------------------------------------------------------------------------------------------- who may save
    def test_the_persons_save_from_the_panel_writes_their_own_piece(self):
        r = self.rpc(self.call(1, "athos_find", request="summarise the quarterly numbers for the board"),
                     self.call(2, "athos_step", new="pull the numbers"),
                     self.call(3, "athos_step", new="compare with last quarter"),
                     self.call(4, "athos_done", outcome="summary sent"))
        self.assertTrue(self.trail()["can_save"])                 # the task is done: the button stays, the mark is gone
        before = len(ui_events())
        r = self.rpc(self.call(1, "athos_keep", action="save"))[0]["result"]
        self.assertFalse(r["isError"])
        out = json.loads(r["content"][0]["text"])
        p = store.get(out["id"])
        self.assertEqual(p.title, "Summarise the quarterly numbers for the board")
        self.assertEqual(p.status, "")                             # the person's own piece
        self.assertTrue(store.legacy(p))
        self.assertIn("**Do:** Pull the numbers.", p.body)
        self.assertIn("**Do:** Compare with last quarter.", p.body)
        self.assertEqual(ui_events()[before:], [("idle", "learning", "saving"), ("learning", "idle", "between_tasks")])
        after = r["structuredContent"]
        self.assertFalse(after["can_save"])
        self.assertEqual(after["saved"]["title"], p.title)
        again = self.rpc(self.call(1, "athos_keep", action="save"))[0]["result"]
        self.assertTrue(again["isError"])                          # nothing new to save twice

    def test_the_persons_save_adds_new_steps_to_the_piece_in_use(self):
        self.release()
        self.rpc(self.call(1, "athos_find", request="release greet 0.3.0"),
                 self.call(2, "athos_step", step="release#tag"),
                 self.call(3, "athos_step", new="announce it on the list"))
        out = json.loads(self.rpc(self.call(1, "athos_keep", action="save"))[0]["result"]["content"][0]["text"])
        p = store.get("release")
        self.assertEqual((out["id"], p.version, out["improved"]), ("release", 2, True))
        self.assertTrue(p.body.startswith(BODY.rstrip()))
        self.assertIn("## #announce-it-on-the-list\n**Do:** Announce it on the list.", p.body)
        self.assertTrue(store.legacy(p))

    def test_change_this_step_writes_the_persons_words_into_it(self):
        self.release()
        self.rpc(self.call(1, "athos_find", request="release greet 0.3.0"),
                 self.call(2, "athos_step", step="release#tag"))
        r = self.rpc(self.call(1, "athos_keep", action="adjust", step="release#tag", text="sign the tag"))[0]["result"]
        self.assertFalse(r["isError"])
        p = store.get("release")
        self.assertIn("**Do:** tag the release. Sign the tag.\n", p.body)
        self.assertIn("## #push-tag\n**Do:** push the tag.", p.body)
        self.assertEqual(p.version, 2)
        bad = self.rpc(self.call(1, "athos_keep", action="adjust", step="release#nope", text="x"))[0]["result"]
        self.assertTrue(bad["isError"])

    def test_the_models_own_save_still_saves_nothing(self):
        r = self.rpc(self.call(1, "athos_find", request="plan the offsite"),
                     self.call(2, "athos_step", new="book the room"),
                     self.call(3, "athos_save", text="---\ntitle: Plan the offsite\nwhen: planning\n---\n"
                                                    "## #room\n**Do:** book the room.\n"))
        self.assertTrue(r[2]["result"]["isError"])
        self.assertIn("not saved", r[2]["result"]["content"][0]["text"])
        self.assertEqual(store.all_pieces(), [])

    # ------------------------------------------------------------------------------------------------- privacy
    def test_the_panel_names_only_what_find_may_hand_over(self):
        self.release()
        store.create("Board pack for the other team", "board pack", "## #pack\n**Do:** build the pack.\n",
                     piece_id="board-pack")
        store.create("Notes kept apart", "notes", "## #n\n**Do:** keep it.\n", piece_id="apart")
        # A step of the release piece hands over to the board pack, which the person's selection leaves out.
        p = store.get("release")
        store.update("release", "calls", body=p.body + "\n## #pack\n**Do:** the pack.\n**Calls:** [[board-pack]]\n")
        control.set_selection("pieces", ["release"])
        r = self.rpc(self.call(1, "athos_find", request="release greet 0.3.0"),
                     self.call(2, "athos_show", id="apart"),
                     self.call(3, "athos_step", step="apart#n"),
                     self.call(4, "athos_step", step="release#pack"),
                     self.call(5, "athos_trail"),
                     self.call(6, "athos_keep", action="adjust", step="apart#n", text="x"))
        allowed = {p.id for p in mcp.load.enabled(None)}
        self.assertEqual(allowed, {"release"})
        states = [x["result"].get("_meta", {}).get("athos/panel") for x in r[:4]] + [r[4]["result"]["structuredContent"]]
        for s in states:
            text = json.dumps(s)
            for hidden in ("apart", "Notes kept apart", "board-pack", "Board pack for the other team"):
                self.assertNotIn(hidden, text)
        self.assertTrue(r[5]["result"]["isError"])                 # nor changed from the panel
        self.assertEqual(store.get("apart").version, 1)

    def test_with_nothing_handed_over_a_step_elsewhere_does_not_light_the_mark(self):
        store.create("Notes kept apart", "notes", "## #n\n**Do:** keep it.\n", piece_id="apart")
        control.set_selection("none")
        r = self.rpc(self.call(1, "athos_find", request="notes"), self.call(2, "athos_step", step="apart#n"))
        s = r[1]["result"]["_meta"]["athos/panel"]
        self.assertEqual(s["indicator"]["state"], "idle")
        self.assertNotIn("apart", json.dumps(s))


class OverStdioTest(TempHome):
    """The server itself, as Claude Desktop runs it: `athos mcp` over stdio, in a throwaway home."""

    def test_a_chat_end_to_end(self):
        store.create("Release the greet package", "releasing greet with a new option", BODY, piece_id="release")

        def call(i, name, **args):
            return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}

        msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18", "capabilities": APPS}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                call(2, "athos_find", request="release greet 0.3.0"),
                call(3, "athos_step", step="release#tag"),
                call(4, "athos_trail"),
                call(5, "athos_keep", action="adjust", step="release#tag", text="sign it"),
                call(6, "athos_done", outcome="tagged"),
                call(7, "athos_find", request="write the onboarding email"),
                call(8, "athos_step", new="greet the new hire"),
                call(9, "athos_trail"),
                call(10, "athos_save", text="---\ntitle: Onboarding\nwhen: onboarding\n---\n## #a\n**Do:** greet.\n"),
                call(11, "athos_keep", action="save"),
                call(12, "athos_trail")]
        env = {**os.environ, "HOME": self.home}
        out = subprocess.run([sys.executable, str(ROOT / "bin" / "athos"), "mcp"], input="".join(
            json.dumps(m) + "\n" for m in msgs), capture_output=True, text=True, env=env, timeout=60, cwd=self.home)
        r = {x["id"]: x for x in map(json.loads, out.stdout.splitlines())}
        self.assertEqual(r[0]["result"]["instructions"], mcp.INSTRUCTIONS_MINIMAL)
        tools = {t["name"]: t for t in r[1]["result"]["tools"]}
        self.assertEqual(tools["athos_find"]["_meta"]["ui"]["resourceUri"], "ui://athos/trail")
        self.assertEqual(r[2]["result"]["_meta"]["athos/panel"]["indicator"]["state"], "collaborating")
        s = r[4]["result"]["structuredContent"]
        self.assertEqual([(x["id"], x["state"]) for x in s["trail"]["pieces"][0]["steps"]],
                         [("tag", "now"), ("push-tag", "ahead")])
        self.assertEqual(json.loads(r[5]["result"]["content"][0]["text"])["version"], 2)
        self.assertEqual(r[9]["result"]["structuredContent"]["indicator"], {"state": "learning", "why": "drafting_steps"})
        self.assertTrue(r[10]["result"]["isError"])                                       # the model's save
        saved = json.loads(r[11]["result"]["content"][0]["text"])
        self.assertEqual(saved["title"], "Write the onboarding email")
        last = r[12]["result"]["structuredContent"]
        self.assertEqual((last["saved"]["id"], last["can_save"]), (saved["id"], False))
        piece = store.get(saved["id"])
        self.assertTrue(piece is not None and store.legacy(piece))
        self.assertEqual(store.get("release").version, 2)
