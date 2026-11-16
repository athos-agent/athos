import tempfile
from pathlib import Path

from athos import store
from tests.helpers import TempHome

CLAUDE = {"platform": "claude-code", "model": "claude-opus-5-5"}
CODEX = {"platform": "codex", "model": "gpt"}


class PieceFilesTest(TempHome):
    def piece_file(self, piece_id):
        return Path(self.home) / "know-how" / f"{piece_id}.md"

    def test_a_new_piece_is_plain_markdown_under_frontmatter(self):
        made = store.create("Cut a release", "preparing a release: of a package", "1. Bump the version.",
                            projects=["athos"], origin=CLAUDE)
        content = made.path.read_text()
        self.assertTrue(content.startswith("---\nid: cut-a-release\n"))
        for expected in ('when: "preparing a release: of a package"',     # a colon forces quotes
                         "  model: claude-opus-5-5", "1. Bump the version.", "## History"):
            self.assertIn(expected, content)

    def test_reading_back_gives_the_same_piece(self):
        made = store.create("Fix flaky test", "a test fails only sometimes", "Run it 20 times.", projects=["a", "b"],
                            origin=CODEX)
        back = store.get(made.id)
        fields = ("title", "when", "body", "projects", "origin")
        self.assertEqual([getattr(back, f) for f in fields], [getattr(made, f) for f in fields])
        self.assertEqual(back.version, 1)
        self.assertEqual(len(back.history), 1)

    def test_a_repeated_title_gets_its_own_id(self):
        first = store.create("Same title", "x", "a")
        second = store.create("Same title", "y", "b")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(store.get(first.id).body, "a")

    def test_edits_made_by_hand_are_picked_up(self):
        made = store.create("Tidy the inbox", "the inbox overflows", "Archive everything older than a week.")
        target = self.piece_file(made.id)
        target.write_text(target.read_text().replace("older than a week", "older than a month"))
        self.assertEqual(store.get(made.id).body, "Archive everything older than a month.")

    def test_export_counts_and_copies_every_piece(self):
        for title in ("Alpha", "Beta"):
            store.create(title, f"when {title}", f"body of {title}")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            self.assertEqual(store.export(out), 2)
            self.assertEqual(sorted(f.name for f in out.glob("*.md")), ["alpha.md", "beta.md"])


class RevertKeepsWhoMaySeeTest(TempHome):
    def test_a_revert_keeps_the_visibility_and_projects_the_piece_has_now(self):
        store.create("Ship", "shipping", "## #a\n**Do:** v1.\n", projects=["alpha"], piece_id="ship")
        store.update("ship", "v2", body="## #a\n**Do:** v2.\n")
        p = store.get("ship")
        # The person marks it private by hand, and tags it with a second project: no new version, no archive.
        p.path.write_text(p.path.read_text().replace("projects: [alpha]", "projects: [alpha, beta]\nvisibility: private"))
        restored = store.revert("ship")
        self.assertIn("v1.", restored.body)
        self.assertEqual((restored.visibility, restored.projects), ("private", ["alpha", "beta"]))
        again = store.get("ship")
        self.assertEqual((again.visibility, again.projects), ("private", ["alpha", "beta"]))
