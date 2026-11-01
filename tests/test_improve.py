from pathlib import Path

from athos import capture, session, store
from tests.helpers import TempHome

FIRST_BODY = "Run it 20 times."
WRITTEN_IN = {"platform": "claude-code", "model": "claude-opus-5-5"}


class VersionedChangesTest(TempHome):
    def setUp(self):
        TempHome.setUp(self)
        self.p = store.create("Fix a flaky test", "a test fails only sometimes", FIRST_BODY, origin=WRITTEN_IN)

    def archive_dir(self):
        return Path(self.home) / "know-how" / ".history" / self.p.id

    def test_an_update_archives_the_old_text_and_logs_the_change(self):
        improved, diff = store.update(self.p.id, "added the seed step", body=FIRST_BODY + "\nFix the random seed.")
        self.assertEqual(improved.version, 2)
        newest = improved.history[0]
        self.assertTrue(newest.startswith("v2 ") and "added the seed step" in newest, newest)
        self.assertEqual(len(improved.history), 2)
        self.assertTrue(any(line == "+Fix the random seed." for line in diff.splitlines()), diff)
        archived = store.parse((self.archive_dir() / "v1.md").read_text())
        self.assertEqual(archived.body, FIRST_BODY)

    def test_a_captured_reply_with_an_id_improves_that_piece(self):
        session.update("capture-session", model="other-model")
        reply = f"---\nid: {self.p.id}\nnote: works on Windows too\n---\n{FIRST_BODY}\nOn Windows use -n 1."
        piece, diff = capture.save_text(reply, "capture-session")
        self.assertEqual((piece.version, piece.origin.get("model")), (2, "other-model"))
        self.assertEqual(piece.title, "Fix a flaky test")             # fields the reply leaves out stay as they were
        self.assertTrue(diff)
        self.assertEqual(len(store.all_pieces()), 1)                  # the same piece, not a second one

    def test_reverting_twice_brings_the_change_back(self):
        worse = "Just rerun the whole pipeline."
        store.update(self.p.id, "a worse idea", body=worse)
        restored = store.revert(self.p.id)
        self.assertEqual((restored.body, restored.version), (FIRST_BODY, 3))
        self.assertEqual(store.revert(self.p.id).body, worse)

    def test_every_update_leaves_an_archived_version(self):
        for n in range(3):
            store.update(self.p.id, f"change {n}", body=f"body {n}")
        kept = sorted(f.name for f in self.archive_dir().glob("*.md"))
        self.assertEqual(kept, ["v1.md", "v2.md", "v3.md"])
        self.assertEqual(store.get(self.p.id).version, 1 + 3)
