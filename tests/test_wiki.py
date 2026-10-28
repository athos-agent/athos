import os
import tempfile
from pathlib import Path

from athos import capture, session, store, wiki
from tests.helpers import TempHome

LAND = """## #run_guard
**When:** about to commit to the public repo.
**Do:** run the guard and stop on any finding.
**Because:** a private name reached a public PR once.
**Links:** [[land#open_pr]] · [[bump-version#bump]]

## #open_pr
**When:** the guard is clean.
**Do:** push the branch and open the PR with the label.
**Links:** [[land#run_guard]]
"""
BUMP = """## #bump
**When:** the plugin changed.
**Do:** bump the version in the three manifests.
**Because:** the marketplace only updates on a new version.
"""


class WikiTest(TempHome):
    def pages(self):
        store.create("Land a change", "committing to the public repo", LAND, projects=["athos"], piece_id="land")
        store.create("Bump the version", "the plugin changed", BUMP, projects=["athos"], piece_id="bump-version")
        store.create("Old one", "something old", "1. do this\n2. then that", projects=["other"], piece_id="old")

    def test_statements_fields_and_links(self):
        self.pages()
        ss = wiki.statements(store.get("land"))
        self.assertEqual([s.id for s in ss], ["run_guard", "open_pr"])
        self.assertEqual(ss[0].do, "run the guard and stop on any finding.")
        self.assertEqual(ss[0].links, [("land", "open_pr"), ("bump-version", "bump")])
        self.assertEqual([s.id for s in wiki.statements(store.get("old"))], ["steps"])

    def test_lint_finds_broken_links_dupes_and_old_pages(self):
        self.pages()
        store.create("Broken", "x", "## #a\n**Do:** x\n**Links:** [[nowhere]] · [[land#missing]]\n\n## #a\n**Do:** y",
                     piece_id="broken")
        r = wiki.lint()
        self.assertEqual(r["broken"], ["broken → [[nowhere]]", "broken → [[land#missing]]"])
        self.assertEqual(r["duplicate_ids"], ["broken#a"])
        self.assertEqual(r["old_format"], ["old"])
        self.assertEqual(r["entries"], ["broken", "old"])         # land is reached from broken
        self.assertNotIn("bump-version", r["entries"])          # reached through land's link

    def test_index_and_trajectory_agent(self):
        self.pages()
        r = wiki.rebuild()
        idx = (Path(self.home) / "know-how" / "Index.md").read_text()
        self.assertIn("**[[land#run_guard|Land a change]]**: committing to the public repo", idx)
        self.assertIn("[[land|Land a change]] → [[bump-version|Bump the version]]", idx)
        self.assertEqual(r["agents"], ["athos-land.md"])
        agent = (wiki.agents_dir() / "athos-land.md").read_text()
        self.assertIn("name: athos-land", agent)
        self.assertIn("### [[bump-version#bump]]", agent)
        self.assertIn("land v1, bump-version v1", agent)
        self.assertEqual(len(store.all_pieces()), 3)            # the index is not a piece

    def test_the_agent_evolves_with_its_pages(self):
        self.pages()
        wiki.rebuild()
        store.update("bump-version", "also the codex manifest",
                     body=BUMP.replace("three manifests", "three manifests, codex included"))
        r = wiki.rebuild()
        self.assertEqual(r["written"], ["athos-land.md"])
        agent = (wiki.agents_dir() / "athos-land.md").read_text()
        self.assertIn("codex included", agent)
        self.assertIn("bump-version v2", agent)
        store.update("land", "no longer needs the bump", body=LAND.replace(" · [[bump-version#bump]]", ""))
        self.assertEqual(wiki.rebuild()["removed"], ["athos-land.md"])

    def test_save_rebuilds_and_installs_when_chosen(self):
        target = Path(self.home) / "claude-agents"
        (Path(self.home) / "agents-install").write_text(str(target))
        self.pages()
        capture.save_text("---\ntitle: Land a change\nwhen: committing\nid: land\nnote: same\n---\n" + LAND, "w1")
        self.assertTrue((target / "athos-land.md").exists())
        self.assertTrue((Path(self.home) / "know-how" / "Index.md").exists())
        self.assertEqual(session.load("w1")["wiki"]["broken"], [])

    def test_cli(self):
        from athos import cli
        self.pages()
        self.assertEqual(cli.main(["wiki"]), 0)
        target = Path(self.home) / "agents-out"
        self.assertEqual(cli.main(["wiki", "agents", "--install", "--dir", str(target)]), 0)
        self.assertTrue((target / "athos-land.md").exists())
        self.assertEqual(cli.main(["wiki", "agents", "--uninstall", "--dir", str(target)]), 0)
        self.assertFalse((target / "athos-land.md").exists())


class FollowingTest(TempHome):
    def test_following_names_the_loaded_pieces_and_where_they_are_ready(self):
        from athos import cli
        from athos.adapters import codex
        store.create("Land a change", "committing", LAND, piece_id="land")
        (codex.skills_dir() / "athos-land").mkdir(parents=True)
        out = cli.following({"task_loaded": ["land", "gone"]})
        self.assertEqual(out, [{"id": "land", "title": "Land a change", "version": 1, "steps": 2, "wiki": True,
                                "platforms": ["Claude Code", "Codex", "Muse Code"]}])
