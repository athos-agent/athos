import os
import tempfile
from pathlib import Path

from athos import eval as ev, project, store
from tests.helpers import TempHome

BODY = """## #read_checklist
**When:** a contract to review arrives with the person's checklist.
**Do:** read the checklist file before the contract.
**Because:** the points are the person's, not generic ones.
**Links:** [[review-a-contract#table]]

## #table
**When:** every point is checked.
**Do:** never decide for the client: return a table of clause, issue, proposal, priority.
**Because:** what to negotiate is the client's call."""


class ProjectTest(TempHome):
    def setUp(self):
        super().setUp()
        self._proj = tempfile.TemporaryDirectory()
        self.root = Path(self._proj.name) / "office"
        self.root.mkdir()
        store.create("Review a contract", "reviewing a contract against a checklist", BODY, projects=["office"],
                     piece_id="review-a-contract")
        store.create("Plan a training week", "planning an athlete's week", "## #load\n**Do:** compute the load.",
                     projects=["club"], piece_id="plan-a-week")

    def tearDown(self):
        self._proj.cleanup()
        super().tearDown()

    def test_sync_builds_the_folder_and_points_every_agent_at_it(self):
        (self.root / "AGENTS.md").write_text("# House rules\n\nUse tabs.\n")
        r = project.sync(self.root)
        self.assertEqual(r["pieces"], ["review-a-contract"])                      # only this project's piece
        a = self.root / ".athos"
        for f in ("README.md", "wiki/Index.md", "wiki/METHOD.md", "wiki/review-a-contract.md", "agents/AGENTS.md",
                  "agents/athos-review-a-contract.md", "skills/SKILLS.md", "skills/athos-review-a-contract/SKILL.md",
                  "tools/README.md"):
            self.assertTrue((a / f).is_file(), f)
        for f in (".claude/skills/athos-review-a-contract/SKILL.md", ".agents/skills/athos-review-a-contract/SKILL.md",
                  ".claude/agents/athos-review-a-contract.md", ".opencode/agents/athos-review-a-contract.md"):
            self.assertTrue((self.root / f).is_file(), f)
        agents_md = (self.root / "AGENTS.md").read_text()
        self.assertTrue(agents_md.startswith("# House rules\n\nUse tabs.\n"))      # the person's text stays
        self.assertIn(".athos/wiki/Index.md", agents_md)
        self.assertIn(".athos/wiki/Index.md", (self.root / "CLAUDE.md").read_text())
        self.assertIn(".athos/", (self.root / ".gitignore").read_text())
        oc = (self.root / ".opencode/agents/athos-review-a-contract.md").read_text()
        self.assertIn("mode: subagent", oc)
        self.assertNotIn("name:", oc.split("---")[1])

    def test_method_says_how_trajectories_are_made_and_lists_what_not_to_do(self):
        project.sync(self.root)
        method = (self.root / ".athos/wiki/METHOD.md").read_text()
        self.assertIn("## How a trajectory is made", method)
        self.assertIn("[[review-a-contract#table]]: never decide for the client", method)
        self.assertIn("### Review a contract (`review-a-contract`, v1)", method)

    def test_sync_twice_is_the_same_and_drops_pages_no_longer_chosen(self):
        project.sync(self.root, everything=True)
        self.assertTrue((self.root / ".claude/skills/athos-plan-a-week").is_dir())
        mine = self.root / ".claude/skills/my-own-skill"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("---\nname: my-own-skill\n---\nmine")
        project.sync(self.root)
        project.sync(self.root)
        self.assertFalse((self.root / ".claude/skills/athos-plan-a-week").exists())
        self.assertTrue(mine.is_dir())                                            # never anyone else's files
        self.assertEqual((self.root / "AGENTS.md").read_text().count("athos:begin"), 1)
        self.assertEqual((self.root / ".gitignore").read_text().count(".athos/"), 1)

    def test_a_project_task_selects_its_pieces(self):
        ev.append({"type": "task_start", "task_id": "t1", "project": "office", "at": "2026-10-29T10:00:00+00:00"})
        ev.append({"type": "task_end", "task_id": "t1", "pieces": ["plan-a-week"], "at": "2026-10-29T10:01:00+00:00"})
        self.assertEqual({p.id for p in project.select(self.root)}, {"review-a-contract", "plan-a-week"})

    def test_nothing_to_sync_is_said_plainly(self):
        empty = Path(self._proj.name) / "empty"
        empty.mkdir()
        with self.assertRaises(LookupError):
            project.sync(empty)
        with self.assertRaises(LookupError):
            project.sync(empty, ids=["no-such-piece"])

    def test_commit_keeps_it_out_of_gitignore_and_remove_leaves_the_project_as_it_was(self):
        (self.root / "AGENTS.md").write_text("# House rules\n")
        project.sync(self.root, commit=True)
        self.assertFalse((self.root / ".gitignore").exists())
        project.sync(self.root)
        gone = project.remove(self.root)
        self.assertIn(".athos", gone)
        self.assertEqual((self.root / "AGENTS.md").read_text(), "# House rules\n")
        for f in ("CLAUDE.md", ".gitignore", ".athos"):
            self.assertFalse((self.root / f).exists(), f)
        self.assertEqual(list((self.root / ".claude/skills").iterdir()), [])
