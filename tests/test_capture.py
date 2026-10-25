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
        session.update("s1", loaded=["fix-flaky-test"], tools_since_capture=capture.THRESHOLD)
        self.assertIn("fix-flaky-test", capture.stop_decision({"session_id": "s1"})["reason"])
