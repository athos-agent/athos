import tempfile
from pathlib import Path

from athos import store
from tests.helpers import TempHome


class StoreTest(TempHome):
    def test_create_writes_readable_markdown_with_frontmatter(self):
        p = store.create("Cut a release", "preparing a release: of a package", "1. Bump the version.",
                         projects=["athos"], origin={"platform": "claude-code", "model": "claude-opus-5-5"})
        text = p.path.read_text()
        self.assertTrue(text.startswith("---\nid: cut-a-release\n"))
        self.assertIn('when: "preparing a release: of a package"', text)
        self.assertIn("  model: claude-opus-5-5", text)
        self.assertIn("1. Bump the version.", text)
        self.assertIn("## History", text)

    def test_round_trip(self):
        p = store.create("Fix flaky test", "a test fails only sometimes", "Run it 20 times.", projects=["a", "b"],
                         origin={"platform": "codex", "model": "gpt"})
        q = store.get(p.id)
        self.assertEqual((q.title, q.when, q.body, q.projects, q.origin, q.version),
                         (p.title, p.when, p.body, p.projects, p.origin, 1))
        self.assertEqual(len(q.history), 1)

    def test_ids_never_collide(self):
        a = store.create("Same title", "x", "a")
        b = store.create("Same title", "y", "b")
        self.assertNotEqual(a.id, b.id)
        self.assertEqual(store.get(a.id).body, "a")

    def test_hand_edited_file_is_read(self):
        store.create("Edited", "x", "old")
        f = Path(self.home) / "know-how" / "edited.md"
        f.write_text(f.read_text().replace("old", "edited by hand"))
        self.assertEqual(store.get("edited").body, "edited by hand")

    def test_export_copies_everything(self):
        store.create("One", "x", "1")
        store.create("Two", "y", "2")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(store.export(Path(d) / "out"), 2)
            self.assertEqual(sorted(f.name for f in (Path(d) / "out").glob("*.md")), ["one.md", "two.md"])
