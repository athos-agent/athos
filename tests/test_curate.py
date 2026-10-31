import json
from pathlib import Path
from unittest import mock

from athos import curate, eval as ev, load, paths, store, trail
from tests.helpers import TempHome

BODY = "## #a\n**When:** at the start.\n**Do:** do it.\n"


class CurateTest(TempHome):
    def setUp(self):
        super().setUp()
        self.shop = Path(self.home) / "shop"
        self.shop.mkdir()
        # Test homes live in a temporary folder, which marks every task a rehearsal; here they are real work.
        patcher = mock.patch.object(ev, "SCRATCH_PREFIXES", ("/nowhere/",))
        patcher.start()
        self.addCleanup(patcher.stop)

    def task(self, sid, prompt, cwd, steps=()):
        ev.task_start({"session_id": sid, "prompt": prompt, "cwd": str(cwd)})
        load.on_prompt({"session_id": sid, "prompt": prompt, "cwd": str(cwd)})
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

    def test_tests_and_rehearsals_propose_nothing(self):
        store.create("Release a package", "releasing a package", BODY, projects=["lib"], piece_id="release")
        demo = Path(self.home) / "athos-demo-x"
        demo.mkdir()
        self.task("s1", "release the package for the demo", demo, ["release#a"])        # named like a demo
        with mock.patch.object(ev, "SCRATCH_PREFIXES", (str(self.shop),)):
            self.task("s2", "release the package in the shop", self.shop, ["release#a"])  # in a scratch folder
        self.assertEqual([x for x in curate.proposals() if x["kind"] == "tag"], [])
        other = Path(self.home) / "office"
        other.mkdir()
        self.task("s3", "release the package from the office", other, ["release#a"])
        self.assertEqual([x["project"] for x in curate.proposals() if x["kind"] == "tag"], ["office"])
        curate.ignore("office")
        self.assertEqual([x for x in curate.proposals() if x["kind"] == "tag"], [])

    def test_a_dismissed_proposal_stays_away_and_new_ones_say_so(self):
        store.create("Release a package", "releasing a package", BODY, projects=["lib"], piece_id="release")
        self.task("s1", "release the shop package now", self.shop, ["release#a"])
        first = curate.proposals()
        self.assertFalse(first[0]["new"])                                   # no earlier pass to compare with
        curate.mark_pass(first)
        store.create("Deploy", "deploying", BODY + "**Links:** [[gone]]\n", piece_id="deploy")
        again = {x["kind"]: x for x in curate.proposals()}
        self.assertFalse(again["tag"]["new"])
        self.assertTrue(again["link"]["new"])
        curate.dismiss(again["tag"])
        self.assertNotIn("tag", {x["kind"] for x in curate.proposals()})
        self.assertIn("tag", {x["kind"] for x in curate.proposals(all_=True)})

    def test_corrections_become_a_proposed_dont_rule(self):
        store.create("Review a lease", "reviewing a lease", BODY, piece_id="lease")
        d = paths.home() / "cases" / "lease"
        d.mkdir(parents=True)
        (d / "t1.json").write_text(json.dumps({"task_id": "t1", "piece": "lease", "mark": "corrected",
                                                "request": "review this lease", "correction": "never cite the old code",
                                                "at": "2099-01-01T00:00:00"}))
        rule = [x for x in curate.proposals() if x["kind"] == "rule"]
        self.assertEqual(len(rule), 1)
        self.assertIn("«never cite the old code»", rule[0]["why"])
        self.assertTrue(rule[0]["request"].startswith("Athos · adjust lease: add a step with what not to do"))

    def test_a_page_that_keeps_going_wrong_is_flagged_for_review(self):
        store.create("Release a package", "release a package", BODY, piece_id="release")
        for i in range(3):
            self.task(f"b{i}", "release a package now", self.shop)
            ev.mark("c", session_id=f"b{i}")
        self.assertEqual([x["id"] for x in curate.proposals() if x["kind"] == "review"], ["release"])

    def test_a_correction_belongs_to_the_page_the_task_walked(self):
        store.create("Triage", "triage an incident", BODY + "\n## #b\n**When:** later.\n**Do:** more.\n",
                     piece_id="triage")
        store.create("Postmortem", "write the postmortem", BODY, piece_id="postmortem")
        self.task("s1", "triage the checkout incident", self.shop, ["triage#a", "triage#b"])
        tid = ev.tasks()[-1]["task_id"]
        for pid in ("triage", "postmortem"):                    # a case is kept for every page that loaded
            d = paths.home() / "cases" / pid
            d.mkdir(parents=True)
            (d / f"{tid}.json").write_text(json.dumps({"task_id": tid, "piece": pid, "mark": "corrected",
                                                       "request": "triage", "correction": "check migrations first",
                                                       "at": "2099-01-01T00:00:00"}))
        self.assertEqual([x["id"] for x in curate.proposals() if x["kind"] == "rule"], ["triage"])
