"""`athos bench route --replay`: one session's requests again, through the scope the hooks apply (`control.select`),
read-only and counts only. All data here is synthetic."""

import contextlib
import io
import json
from pathlib import Path

from athos import cli, control, store
from athos.bench import route
from tests.helpers import TempHome

SECRET = "zebra quartz marmalade"            # words that must never be printed


def piece(pid, title, when, projects=(), body="## #one\n**When:** at the start.\n**Do:** the first thing.\n"):
    p = store.Piece(id=pid, title=title, when=when, body=body, projects=list(projects), created="2026-11-01",
                    last_used="2026-11-01", origin={"platform": "test", "model": "test"})
    store._write(p)
    return p


class ScopeTest(TempHome):
    def test_select_gives_the_same_pieces_as_filter_pieces_and_says_why(self):
        piece("a1", "Alpha thing", "alpha work", ["alpha"])
        piece("b1", "Beta thing", "beta work", ["beta"])
        piece("g1", "General thing", "any work")
        piece("u1", "Untagged thing", "other work")
        everything = store.all_pieces()
        control.profile_add(["g1"])                                   # g1 applies everywhere; u1 only has no tag
        cases = [("alpha", "", "auto:project", {"a1", "g1"}), ("alpha", "as in beta", "auto:project+named",
                                                                {"a1", "b1", "g1"}),
                 ("gamma", "", "auto:no-own-pieces", {"g1"}),
                 ("gamma", "as in beta", "auto:no-own-pieces+named", {"b1", "g1"})]
        for project, prompt, reason, ids in cases:
            chosen, why = control.select(everything, None, prompt, project=project)
            self.assertEqual(({p.id for p in chosen}, why["reason"]), (ids, reason))
            self.assertEqual(chosen, control.filter_pieces(everything, None, prompt, project=project))
            self.assertEqual(chosen, control.scope_project(everything, project, prompt))
        self.assertEqual(control.select(everything, None, "")[1]["reason"], "auto:no-folder")
        self.assertEqual(len(control.select(everything, None, "")[0]), 4)          # no folder: every piece
        control.set_selection("all")
        self.assertEqual(len(control.select(everything, None, "", project="gamma")[0]), 4)   # the way back
        control.set_selection("none")
        self.assertEqual(control.select(everything, None, "", project="alpha"), ([], {
            "mode": "none", "project": "alpha", "reason": "none", "named": [], "marker": False, "public": False,
            "private_held": 0}))


class ReplayTest(TempHome):
    def test_a_replay_counts_loads_other_projects_and_characters_without_printing_requests(self):
        piece("a1", "Ship a release with the checklist", "shipping a release of the app", ["alpha"])
        piece("b1", "Write the weekly report", "writing the weekly report for the team", ["beta"])
        case = {"project": "gamma", "cases": [{"request": f"write the weekly report for the team {SECRET}"},
                                              {"request": "what time is it"},
                                              {"request": "ship a release of the app", "expect": ["a1"]},
                                              {"request": f"write the weekly report for the team as in beta {SECRET}",
                                               "expect": ["b1"]}]}
        f = Path(self.home) / "case.json"
        f.write_text(json.dumps(case))
        r = route.replay(route.load_replay(f))
        # A project with no pieces of its own sees only the profile (empty here): another project's piece loads
        # only for the request that names that project.
        self.assertEqual((r["prompts"], r["loaded"], r["other_project"], r["as_expected"]), (4, 1, 1, 3))
        self.assertEqual(r["scope"], {"auto:no-own-pieces": 3, "auto:no-own-pieces+named": 1})
        self.assertGreater(r["injected_max"], 0)
        self.assertNotIn("rows", r)
        text = route.render_replay(r)
        self.assertNotIn("zebra", text)
        self.assertNotIn("b1", text)
        shown = route.render_replay(route.replay(case, show=True))
        self.assertIn("b1", shown)
        self.assertNotIn("zebra", shown)
        in_alpha = route.replay({**case, "project": "alpha"})
        self.assertEqual((in_alpha["loaded"], in_alpha["other_project"]), (2, 1))

    def test_the_command(self):
        piece("a1", "Ship a release with the checklist", "shipping a release of the app", ["alpha"])
        f = Path(self.home) / "case.json"
        f.write_text(json.dumps({"project": "alpha", "cases": [{"request": "ship a release of the app"}]}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["bench", "route", "--replay", str(f), "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["lexical"]["loaded"], 1)
        before = sorted(p.name for p in Path(self.home).rglob("*"))
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["bench", "route", "--replay", str(f)])
        self.assertEqual(sorted(p.name for p in Path(self.home).rglob("*")), before)    # read-only
