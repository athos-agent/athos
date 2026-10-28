import os

from athos import capture, session, store
from tests.helpers import TempHome

PIECE = """---
title: Run the flaky test until it fails
when: a test fails only sometimes in CI
---
1. Run it 20 times with `-x`.
2. Look for shared state between tests.
"""


class CaptureTest(TempHome):
    def test_save_creates_a_piece_with_origin_and_project(self):
        session.update("s1", model="claude-opus-5-5")
        piece, diff = capture.save_text(PIECE, "s1", cwd=self.home)
        self.assertIsNone(diff)
        got = store.get(piece.id)
        self.assertEqual(got.when, "a test fails only sometimes in CI")
        self.assertEqual(got.origin, {"platform": "claude-code", "model": "claude-opus-5-5"})
        self.assertEqual(got.projects, [os.path.basename(self.home)])
        self.assertIn("Run it 20 times", got.body)

    def test_save_rejects_incomplete_pieces(self):
        with self.assertRaises(ValueError):
            capture.save_text("---\ntitle: x\n---\nbody", "s1")
        with self.assertRaises(ValueError):
            capture.save_text("---\ntitle: x\nwhen: y\n---\n", "s1")

    def test_save_resets_the_counter(self):
        for _ in range(7):
            capture.count_tool({"session_id": "s1"})
        capture.save_text(PIECE, "s1")
        self.assertEqual(session.load("s1")["tools_since_capture"], 0)

    def test_stop_waits_for_enough_work(self):
        for _ in range(capture.THRESHOLD - 1):
            capture.count_tool({"session_id": "s1"})
        self.assertIsNone(capture.stop_decision({"session_id": "s1"}))
        capture.count_tool({"session_id": "s1"})
        out = capture.stop_decision({"session_id": "s1"})
        self.assertEqual(out["decision"], "block")
        self.assertIn("save <<'EOF'", out["reason"])

    def test_stop_asks_once_then_lets_claude_stop(self):
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "s1"})
        self.assertIsNotNone(capture.stop_decision({"session_id": "s1"}))
        self.assertIsNone(capture.stop_decision({"session_id": "s1"}))                       # counter was reset
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "s1"})
        self.assertIsNone(capture.stop_decision({"session_id": "s1", "stop_hook_active": True}))

    def test_stop_can_be_turned_off(self):
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "s1"})
        os.environ["ATHOS_CAPTURE"] = "off"
        try:
            self.assertIsNone(capture.stop_decision({"session_id": "s1"}))
        finally:
            del os.environ["ATHOS_CAPTURE"]

    def test_stop_suggests_improving_loaded_pieces(self):
        session.update("s1", loaded=["fix-flaky-test"], tools_since_capture=capture.THRESHOLD, work_since_capture=1)
        self.assertIn("fix-flaky-test", capture.stop_decision({"session_id": "s1"})["reason"])


class CounterTest(TempHome):
    def test_subagent_tool_calls_do_not_count(self):
        # Found live: a background research agent's tool calls kept asking for captures on turns with no work.
        for _ in range(10):
            capture.count_tool({"session_id": "s1", "agent_id": "a1", "tool_name": "WebFetch"})
        self.assertIsNone(capture.stop_decision({"session_id": "s1"}))

    def test_athos_own_commands_do_not_count(self):
        for cmd in ("/x/bin/athos save <<'EOF'", "athos mark g", "python3 /p/bin/athos report"):
            capture.count_tool({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": cmd}})
        self.assertEqual(session.load("s1").get("tools_since_capture", 0), 0)
        capture.count_tool({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "git status"}})
        self.assertEqual(session.load("s1")["tools_since_capture"], 1)

    def test_a_new_request_starts_the_count_again(self):
        from athos import eval as ev
        for _ in range(capture.THRESHOLD - 1):
            capture.count_tool({"session_id": "s1"})
        ev.task_start({"session_id": "s1", "prompt": "next request"})
        capture.count_tool({"session_id": "s1"})
        self.assertIsNone(capture.stop_decision({"session_id": "s1"}))


class QuietCaptureTest(TempHome):
    def test_with_the_guide_given_the_stop_line_is_short(self):
        from athos import load
        store.create("Ship", "shipping", "1. ship")
        text = load.on_session_start({"session_id": "s2", "cwd": self.home})
        self.assertIn("Saving know-how (Athos)", text)
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "s2"})
        reason = capture.stop_decision({"session_id": "s2"})["reason"]
        self.assertLess(len(reason), 140)
        self.assertIn("athos save", reason)

    def test_without_the_guide_the_stop_line_carries_the_format(self):
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "s3"})
        self.assertIn("save <<'EOF'", capture.stop_decision({"session_id": "s3"})["reason"])

    def test_save_records_where_the_piece_is_ready(self):
        piece, _ = capture.save_text(PIECE, "s4")
        self.assertEqual(session.load("s4")["last_saved"],
                         {"id": piece.id, "title": piece.title, "version": 1, "platforms": ["Claude Code"]})

    def test_save_refreshes_an_existing_export_for_codex_and_muse(self):
        from athos.adapters import codex
        d = codex.skills_dir()
        self.assertTrue(str(d).startswith(self.home))
        (d / "athos-old").mkdir(parents=True)
        piece, _ = capture.save_text(PIECE, "s5")
        self.assertTrue((d / f"athos-{piece.id}" / "SKILL.md").exists())
        self.assertEqual(session.load("s5")["last_saved"]["platforms"], ["Claude Code", "Codex", "Muse Code"])


class RealWorkTest(TempHome):
    """The Stop hook asks only after a turn that changed something; a turn of reads and checks ends quietly."""

    def _bash(self, cmd):
        capture.count_tool({"session_id": "s9", "tool_name": "Bash", "tool_input": {"command": cmd}})

    def test_reads_and_checks_alone_never_ask(self):
        # Found live: "¿por qué veo este texto?" answered with a grep and `claude plugin list`-style checks still asked.
        for cmd in ("ls ~/.athos", "grep -n x a.py | head -3", "git status --short && git log --oneline -3",
                    "gh pr view 28 --json state", "sed -n 1,20p a.py", "which -a athos", "cat a 2>&1 | tail -2"):
            self._bash(cmd)
        capture.count_tool({"session_id": "s9", "tool_name": "Read", "tool_input": {"file_path": "/x"}})
        self.assertIsNone(capture.stop_decision({"session_id": "s9"}))

    def test_one_change_among_the_calls_asks(self):
        self._bash("ls")
        self._bash("git status")
        capture.count_tool({"session_id": "s9", "tool_name": "Edit", "tool_input": {"file_path": "/x"}})
        self.assertIsNotNone(capture.stop_decision({"session_id": "s9"}))

    def test_what_counts_as_a_change(self):
        for cmd in ("git commit -s -m x", "gh pr merge 28 --squash", "sed -i '' s/a/b/ f", "python3 t.py",
                    "echo x > f.txt", "ls && rm f", "gh api -X PUT repos/o/r/branches/main/protection"):
            self.assertFalse(capture._read_only_shell(cmd), cmd)
        for cmd in ("git log --oneline origin/main..wiki", "ls > /dev/null", "grep x f 2>&1", "FOO=1 git diff"):
            self.assertTrue(capture._read_only_shell(cmd), cmd)
