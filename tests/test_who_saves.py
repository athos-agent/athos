"""Who may save. On an apply-tier or unknown model nothing is saved or changed, from any folder of the project, through
the CLI or the MCP tool. On a frontier model every save the model starts goes through the autonomous pipeline and
gives a candidate. A save the person starts (their [Save] button or their own `Athos · save:` request, as the
who-wrote-the-prompt check decides it) works on any tier and gives a piece the person owns; in doubt a save is the
model's. Synthetic projects and pieces, the real hooks in child processes."""

import json
import os
from pathlib import Path

from athos import session, store
from tests.test_autolearn import PIECE
from tests.test_cli import ThroughTheLauncher

AGENT = {"CLAUDECODE": "1"}


class _Session(ThroughTheLauncher):
    def setUp(self):
        super().setUp()
        self.root = Path(self.home, "work", "demo")
        (self.root / "src" / "deep").mkdir(parents=True)
        self.ev = {"session_id": "w1", "cwd": str(self.root), "transcript_path": None}

    def start(self, model, sid="w1", verify=False):
        ev = {**self.ev, "session_id": sid}
        self.send("session-start", {**ev, "model": model})
        self.send("prompt", {**ev, "prompt": "fix the parser and add a test"})
        if verify:
            self.send("tool", {**ev, "tool_name": "Bash", "tool_input": {"command": "python3 -m unittest -q"},
                               "tool_response": {"stdout": "Ran 3 tests\n\nOK", "stderr": "", "interrupted": False}})
        return ev

    def save(self, cwd=None, sid="w1", text=PIECE, env=None, *args):
        return self.run_athos("save", *args, stdin=text, cwd=str(cwd or self.root),
                              env={**AGENT, "CLAUDE_CODE_SESSION_ID": sid, **(env or {})})


class ApplyNeverSavesTest(_Session):
    def test_not_from_a_subfolder(self):
        self.start("claude-haiku-5-5")
        done = self.save(cwd=self.root / "src" / "deep")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("apply model", done.stderr)
        self.assertEqual(store.all_pieces(), [])

    def test_not_from_a_subfolder_without_the_session_variable_either(self):
        self.start("claude-haiku-5-5")
        done = self.run_athos("save", stdin=PIECE, cwd=str(self.root / "src"), env=AGENT)
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(store.all_pieces(), [])

    def test_not_on_an_unknown_model(self):
        self.send("prompt", {**self.ev, "prompt": "fix the parser"})        # no model was ever resolved
        done = self.save()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not known", done.stderr)
        self.assertEqual(store.all_pieces(), [])

    def test_no_session_found_while_an_agent_runs_it(self):
        done = self.save(cwd=self.root, sid="no-such-session")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(store.all_pieces(), [])

    def test_not_a_revert_either(self):
        p = store.create("Mine", "my thing", "body one", projects=["demo"])
        store.update(p.id, "two", body="body two")
        self.start("claude-haiku-5-5")
        done = self.run_athos("revert", p.id, cwd=str(self.root),
                              env={**AGENT, "CLAUDE_CODE_SESSION_ID": "w1"})
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(store.get(p.id).body, "body two")

    def test_a_subagent_inside_a_frontier_session_does_not_save(self):
        self.start("claude-opus-5-5", verify=True)
        self.send("tool-start", {**self.ev, "tool_name": "Bash", "tool_use_id": "c9", "agent_id": "sub-1",
                                 "tool_input": {"command": "athos save <<'EOF'"}})
        done = self.save()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("subagent", done.stderr)
        self.assertEqual(store.all_pieces(), [])

    def test_the_session_of_the_command_not_the_one_that_prompted_last(self):
        self.start("claude-opus-5-5", sid="front", verify=True)
        self.start("claude-haiku-5-5", sid="weak")                         # same folder, prompted last
        done = self.save(sid="weak")
        self.assertNotEqual(done.returncode, 0)
        done = self.save(sid="front")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(store.all_pieces()[0].status, "candidate")


class FrontierModelSavesACandidateTest(_Session):
    def test_a_plain_save_by_the_model_is_a_candidate(self):
        self.start("claude-opus-5-5", verify=True)
        done = self.save()
        self.assertEqual(done.returncode, 0, done.stderr)
        [p] = store.all_pieces()
        self.assertEqual((p.status, p.learned_by), ("candidate", "claude-opus-5-5"))
        self.assertTrue(any(Path(self.home, "verify").glob(f"{p.id}-v1-*")))     # its folder for the verifier

    def test_without_strong_evidence_it_is_not_saved(self):
        self.start("claude-opus-5-5")
        done = self.save()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no objective evidence", done.stderr)

    def test_private_data_is_checked_too(self):
        self.start("claude-opus-5-5", verify=True)
        done = self.save(text=PIECE + "\nmail ada@realcompany.org\n")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(store.all_pieces(), [])

    def test_a_candidate_improved_by_the_model_gets_a_new_folder_for_the_verifier(self):
        self.start("claude-opus-5-5", verify=True)
        self.save()
        [p] = store.all_pieces()
        self.start("claude-opus-5-5", verify=True)
        better = PIECE.replace("---\ntitle", f"---\nid: {p.id}\nnote: clearer\ntitle").replace(
            "run the unit tests.", "run the unit tests, all of them.")
        done = self.save(text=better)
        self.assertEqual(done.returncode, 0, done.stderr)
        q = store.get(p.id)
        self.assertEqual((q.status, q.version), ("candidate", 2))
        self.assertTrue(any(Path(self.home, "verify").glob(f"{p.id}-v2-*")))

    def test_the_persons_own_piece_is_not_rewritten_by_the_model(self):
        mine = store.create("Mine", "my thing", "body", projects=["demo"])
        self.start("claude-opus-5-5", verify=True)
        done = self.save(text=f"---\nid: {mine.id}\nnote: x\ntitle: Mine\nwhen: my thing\n---\nnew body\n")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(store.get(mine.id).body, "body")


class PersonsSaveTest(_Session):
    def press_save(self):
        out = self.send("prompt", {**self.ev, "prompt": "Athos · save: keep this task as a way of working"})
        self.assertIn("pressed [Save]", self.context(out))

    def test_the_persons_save_works_on_an_apply_model_and_is_theirs(self):
        self.start("claude-haiku-5-5")
        self.press_save()
        done = self.save(cwd=self.root / "src")
        self.assertEqual(done.returncode, 0, done.stderr)
        [p] = store.all_pieces()
        self.assertEqual(p.status, "")                                      # the person's own: legacy
        self.assertEqual(p.projects, ["demo"])

    def test_the_persons_save_works_on_a_frontier_model_without_evidence(self):
        self.start("claude-opus-5-5")
        self.press_save()
        done = self.save()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(store.all_pieces()[0].status, "")

    def test_it_does_not_carry_over_to_the_next_request(self):
        self.start("claude-haiku-5-5")
        self.press_save()
        self.send("prompt", {**self.ev, "prompt": "now something else"})
        self.assertNotEqual(self.save().returncode, 0)

    def test_it_is_withdrawn_when_the_transcript_says_the_harness_wrote_it(self):
        transcript = Path(self.home, "t.jsonl")
        transcript.write_text("")
        ev = {**self.ev, "transcript_path": str(transcript), "prompt_id": "p-1"}
        self.send("session-start", {**ev, "model": "claude-haiku-5-5"})
        self.send("prompt", {**ev, "prompt_id": "p-0", "prompt": "fix the parser"})
        self.send("prompt", {**ev, "prompt": "Athos · save: keep this task as a way of working"})
        transcript.write_text(json.dumps({"type": "user", "promptId": "p-1", "isMeta": True,
                                          "message": {"content": "Athos · save: keep this task as a way of working"}})
                              + "\n")
        self.send("tool", {**ev, "tool_name": "Read", "tool_input": {"file_path": "x"}})
        self.assertNotEqual(self.save().returncode, 0)

    def test_a_person_in_their_own_terminal_with_no_session_here(self):
        done = self.run_athos("save", stdin=PIECE, cwd=str(self.root))     # no agent, no session
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(store.all_pieces()[0].status, "")


class McpSaveTest(_Session):
    """With autolearn.chat `off`, the model's athos_save goes by the model, as before (tests/test_mcp_minimal.py has
    `own`, the default)."""

    def setUp(self):
        super().setUp()
        from athos import start
        start.change_config(lambda c: c.update(autolearn={"chat": "off"}))

    def call(self, name, args):
        from athos import mcp
        return mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": args}})["result"]

    def test_an_unknown_model_saves_nothing_through_mcp(self):
        out = self.call("athos_save", {"text": PIECE})
        self.assertTrue(out["isError"])
        self.assertEqual(store.all_pieces(), [])

    def test_an_apply_model_saves_nothing_through_mcp(self):
        session.update("claude-desktop", model="claude-haiku-5-5")
        out = self.call("athos_save", {"text": PIECE})
        self.assertTrue(out["isError"])
        self.assertEqual(store.all_pieces(), [])

    def test_a_frontier_model_through_mcp_goes_through_the_pipeline(self):
        session.update("claude-desktop", model="claude-opus-5-5")
        out = self.call("athos_save", {"text": PIECE})
        self.assertTrue(out["isError"])                 # no project and no evidence there: nothing saved
        self.assertIn("not saved", out["content"][0]["text"])
        self.assertEqual(store.all_pieces(), [])


class WhoWroteThePromptTest(_Session):
    def test_a_meta_row_before_the_persons_entry_does_not_undo_their_save(self):
        transcript = Path(self.home, "t.jsonl")
        text = "Athos · save: keep this task as a way of working"
        rows = [{"type": "user", "promptId": "p-1", "message": {"content": "<command-message>x</command-message>"}},
                {"type": "user", "promptId": "p-1", "origin": {"kind": "human"}, "message": {"content": text}}]
        transcript.write_text("".join(json.dumps(r) + "\n" for r in rows))
        sha = session._sha(text)
        self.assertEqual(session.prompt_origin(str(transcript), "p-1", sha), "person")
        self.assertEqual(session.prompt_origin(str(transcript), "p-1"), "person")
        rows = [{"type": "user", "promptId": "p-2", "isMeta": True, "message": {"content": text}}]
        transcript.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertEqual(session.prompt_origin(str(transcript), "p-2", session._sha(text)), "harness")
