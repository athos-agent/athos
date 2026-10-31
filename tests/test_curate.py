from pathlib import Path

from athos import curate, eval as ev, paths, store, trail
from tests.helpers import TempHome

BODY = "## #a\n**When:** at the start.\n**Do:** do it.\n"


class CurateTest(TempHome):
    def setUp(self):
        super().setUp()
        self.shop = Path(self.home) / "shop"
        self.shop.mkdir()

    def task(self, sid, prompt, cwd, steps=()):
        ev.task_start({"session_id": sid, "prompt": prompt, "cwd": str(cwd)})
        for ref in steps:
            trail.step(sid, ref, None)
        ev.task_end({"session_id": sid})

    def test_a_page_walked_in_a_project_it_isnt_tagged_with_is_proposed_for_it(self):
        store.create("Release a package", "releasing a package", BODY, projects=["lib"], piece_id="release")
        self.task("s1", "release the shop package now", self.shop, ["release#a"])
        p = [x for x in curate.proposals() if x["kind"] == "tag"]
        self.assertEqual([(x["id"], x["project"]) for x in p], [("release", "shop")])
        self.assertIn("now loads in shop too (v2)", curate.apply(p[0]))
        self.assertEqual(store.get("release").projects, ["lib", "shop"])
        self.assertEqual([x for x in curate.proposals() if x["kind"] == "tag"], [])

    def test_an_unused_page_is_archived_and_restored(self):
        p = store.create("Old routine", "an old routine", BODY, piece_id="old")
        f = p.path
        f.write_text(f.read_text().replace(f"last_used: {p.last_used}", "last_used: 2025-01-01")
                     .replace(f"created: {p.created}", "created: 2025-01-01"))
        a = [x for x in curate.proposals() if x["kind"] == "archive"]
        self.assertEqual([x["id"] for x in a], ["old"])
        curate.apply(a[0])
        self.assertIsNone(store.get("old"))
        self.assertTrue((paths.home() / "archive" / "old.md").is_file())
        curate.restore("old")
        self.assertIsNotNone(store.get("old"))

    def test_a_page_another_page_calls_is_never_archived(self):
        p = store.create("Tax check", "checking taxes", BODY, piece_id="tax")
        p.path.write_text(p.path.read_text().replace(f"last_used: {p.last_used}", "last_used: 2025-01-01")
                          .replace(f"created: {p.created}", "created: 2025-01-01"))
        store.create("Deal", "a deal", BODY + "**If:** abroad → [[tax]]\n", piece_id="deal")
        self.assertEqual([x for x in curate.proposals() if x["kind"] == "archive"], [])

    def test_look_alikes_broken_links_and_repeated_work(self):
        store.create("Review a lease contract", "reviewing a lease contract for a tenant", BODY, piece_id="a")
        store.create("Review a lease contract fast", "reviewing a lease contract for a tenant quickly",
                     BODY + "**Links:** [[nowhere]]\n", piece_id="b")
        for i in range(3):
            self.task(f"t{i}", f"translate the quarterly newsletter into french number {i}", self.shop)
        self.task("t9", "como viene?", self.shop)
        kinds = {x["kind"] for x in curate.proposals()}
        self.assertTrue({"similar", "link", "new"} <= kinds)
        new = [x for x in curate.proposals() if x["kind"] == "new"]
        self.assertEqual(new[0]["project"], "shop")
        self.assertNotIn("viene", new[0]["why"])                         # conversation isn't work
        with self.assertRaises(ValueError):
            curate.apply(new[0])                                         # advice, not an action
