from pathlib import Path

from athos import eval as ev, journal, load, store
from tests.helpers import TempHome


class JournalTest(TempHome):
    def setUp(self):
        super().setUp()
        self.proj = Path(self.home) / "shop"
        self.proj.mkdir()
        self.other = Path(self.home) / "blog"
        self.other.mkdir()
        store.create("Release the shop", "release the shop", "## #a\n**When:** x\n**Do:** y", projects=["shop"])
        store.create("Write a blog post", "write a blog post", "## #a\n**When:** x\n**Do:** y", projects=["blog"])

    def task(self, sid, prompt, cwd, mark=None):
        ev.task_start({"session_id": sid, "prompt": prompt, "cwd": str(cwd)})
        load.on_prompt({"session_id": sid, "prompt": prompt, "cwd": str(cwd)})
        ev.task_end({"session_id": sid})
        if mark:
            ev.mark(mark, session_id=sid)

    def test_the_journal_is_the_project_recent_tasks_and_what_is_open(self):
        self.task("s1", "release the shop 2.0", self.proj, "g")
        self.task("s2", "release the shop 2.1 hotfix", self.proj, "c")
        self.task("s3", "write a blog post about the release", self.other, "g")
        self.task("s4", "<agent-message from=\"x\"> done", self.proj)
        text = journal.text("shop")
        self.assertIn("Recently in shop", text)
        self.assertIn("«release the shop 2.1 hotfix»", text)
        self.assertIn("with «Release the shop»", text)
        self.assertIn("Open (corrected or failed", text)
        self.assertNotIn("blog post", text)                          # another project's past stays there
        self.assertNotIn("agent-message", text)
        self.assertLess(text.index("2.1 hotfix"), text.index("2.0»"))  # newest first

    def test_a_session_starts_with_its_project_journal(self):
        self.task("s1", "release the shop 2.0", self.proj, "g")
        self.assertIn("Recently in shop", load.on_session_start({"session_id": "n", "cwd": str(self.proj)}))
        self.assertNotIn("Recently in", load.on_session_start({"session_id": "d"}))   # Desktop: no folder

    def test_older_tasks_are_only_counted(self):
        for i in range(journal.RECENT + 3):
            self.task(f"s{i}", f"release the shop {i}", self.proj, "g")
        text = journal.text("shop")
        self.assertEqual(text.count("\n- "), journal.RECENT)
        self.assertIn("Before that: 3 tasks, most with «Release the shop» ×3.", text)
