from pathlib import Path

from athos import capture, session, store
from tests.helpers import TempHome


class ImproveTest(TempHome):
    def setUp(self):
        super().setUp()
        self.p = store.create("Fix a flaky test", "a test fails only sometimes", "Run it 20 times.",
                              origin={"platform": "claude-code", "model": "claude-opus-5-5"})

    def test_update_bumps_version_keeps_history_and_archives(self):
        new, diff = store.update(self.p.id, "added the seed step", body="Run it 20 times.\nFix the random seed.")
        self.assertEqual(new.version, 2)
        self.assertTrue(new.history[0].startswith("v2 "))
        self.assertIn("added the seed step", new.history[0])
        self.assertEqual(len(new.history), 2)
        self.assertIn("+Fix the random seed.", diff)
        archived = Path(self.home) / "know-how" / ".history" / self.p.id / "v1.md"
        self.assertEqual(store.parse(archived.read_text()).body, "Run it 20 times.")

    def test_improving_through_capture_uses_the_id(self):
        session.update("s1", model="gpt-x")
        text = f"---\nid: {self.p.id}\nnote: works on Windows too\n---\nRun it 20 times.\nOn Windows use -n 1."
        piece, diff = capture.save_text(text, "s1")
        self.assertEqual(piece.version, 2)
        self.assertEqual(piece.title, "Fix a flaky test")                       # unchanged fields are kept
        self.assertEqual(piece.origin["model"], "gpt-x")
        self.assertIsNotNone(diff)
        self.assertEqual(len(store.all_pieces()), 1)                            # no duplicate

    def test_revert_restores_and_is_itself_reversible(self):
        store.update(self.p.id, "worse", body="Just rerun CI.")
        back = store.revert(self.p.id)
        self.assertEqual(back.body, "Run it 20 times.")
        self.assertEqual(back.version, 3)
        again = store.revert(self.p.id)
        self.assertEqual(again.body, "Just rerun CI.")

    def test_nothing_is_overwritten_without_a_version(self):
        for i in range(3):
            store.update(self.p.id, f"change {i}", body=f"body {i}")
        arch = sorted(f.name for f in (Path(self.home) / "know-how" / ".history" / self.p.id).glob("*.md"))
        self.assertEqual(arch, ["v1.md", "v2.md", "v3.md"])
        self.assertEqual(store.get(self.p.id).version, 4)
