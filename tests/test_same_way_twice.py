"""One way of working, one piece: a frontier task that followed a learned piece and saves a new, narrower piece about
the same kind of task is refused and told to improve that piece (same id); a genuinely different way of working in
the same project is saved; a piece the person owns is never changed, so a new piece that repeats it is saved and the
overlap is shown to the person (`athos report`, `athos audit`). Synthetic pieces only."""

import json
import os

from athos import eval as ev, store, wiki
from tests.test_autolearn import _HookedTask

BROAD = """---
title: Add a recipe to the cookbook
when: adding a new recipe to book/recipes.ts, with its ingredients, steps and a tested serving size
---
## #append
**When:** writing the entry.
**Do:** append the object at the end of `RECIPES` in `book/recipes.ts`.
**Check:** `grep -c "id: 'R" book/recipes.ts` prints the new count
**Links:** [[add-a-recipe-to-the-cookbook#validate]]

## #validate
**When:** the recipe is in the file.
**Do:** run `npm run test:recipes`.
**Check:** `npm run test:recipes` exits 0
"""

NARROW = """---
title: Write a cookbook recipe that changes how dishes are grouped
when: adding a recipe to book/recipes.ts whose change makes the grouper return a new course
---
## #probe
**When:** before writing the assertions.
**Do:** print what the grouper returns today for each input with `node -e`.
**Check:** `npm run test:recipes` exits 0
**Links:** [[add-a-recipe-to-the-cookbook#validate]]
"""

NARROW_NO_LINK = NARROW.replace("**Links:** [[add-a-recipe-to-the-cookbook#validate]]\n", "")

REWORDED = """---
title: Add a new recipe to the cookbook list
when: adding a recipe to the cookbook recipes file
---
## #append
**When:** writing the entry.
**Do:** append it to `STORIES`.
**Check:** `npm run test:recipes` exits 0
"""

DIFFERENT = {
    "release": ("Release the package to the registry", "publishing a new version of the package to npm"),
    "flaky": ("Fix a flaky cookbook test", "a cookbook test fails now and then on the same code"),
    "harness": ("Change how the cookbook builder merges recipes",
                "changing book/lib/builder.ts, the code that merges the recipes of an edition"),
    "rename": ("Rename a recipe id across the cookbook",
               "renaming the id of a recipe in book/recipes.ts and every place that names it"),
}


def text_of(title, when):
    return (f"---\ntitle: {title}\nwhen: {when}\n---\n## #do\n**When:** at the start.\n**Do:** run `make check`.\n"
            f"**Check:** `make check` exits 0\n")


class SameWayTwiceTest(_HookedTask):
    def setUp(self):
        super().setUp()
        self.broad = store.create("Add a recipe to the cookbook", "adding a new recipe to book/recipes.ts, with its "
                                  "ingredients, steps and a tested serving size", BROAD.split("---\n", 2)[2],
                                  projects=["demo"], status="candidate", learned_by="claude-opus-5-5",
                                  confidence="0.3", risk="normal", visibility="project")

    def opened_task(self, piece_id=None):
        """A frontier task that may open a piece, with strong evidence, not stopped yet."""
        self.task(stop=False)
        if piece_id:
            self.cli.send("tool", {**self.ev, "tool_name": "Bash", "tool_input": {"command": f"athos show {piece_id}"},
                                   "tool_response": {"stdout": "", "stderr": "", "interrupted": False}})

    def save(self, text):
        return self.cli.run_athos("save", "--auto", stdin=text, cwd=self.work)

    def ids(self):
        return sorted(p.id for p in store.all_pieces())

    def test_the_proliferation_seen_live_is_refused(self):
        # The task opened the learned piece, did the work, then saved a narrower piece about the same kind of task.
        self.opened_task(self.broad.id)
        done = self.save(NARROW)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(f"the same way of working as `{self.broad.id}`", done.stderr)
        self.assertIn(f"id: {self.broad.id}", done.stderr)
        self.assertIn("Improve that piece instead", done.stderr)
        self.assertEqual(self.ids(), [self.broad.id])                          # nothing created
        refused = [e for e in ev.events() if e.get("type") == "learn" and e.get("reason") == "duplicate"]
        self.assertEqual(refused[-1]["overlaps"], [self.broad.id])
        # The model does as told: the same automatic save, with the piece's id, improves it.
        improved = BROAD.replace("---\ntitle", f"---\nid: {self.broad.id}\nnote: a step for a grouping recipe\ntitle")
        improved += NARROW.split("---\n", 2)[2].replace("[[add-a-recipe-to-the-cookbook#validate]]",
                                                        "[[add-a-recipe-to-the-cookbook#validate]]")
        done = self.save(improved)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.ids(), store.get(self.broad.id).version), ([self.broad.id], 2))

    def test_a_near_duplicate_of_any_learned_piece_of_the_project_is_refused(self):
        self.opened_task()                                                     # it opened nothing
        self.assertIn(self.broad.id, self.save(NARROW).stderr)
        self.assertEqual(self.ids(), [self.broad.id])

    def test_the_piece_the_task_followed_is_held_to_a_lower_bar(self):
        self.opened_task(self.broad.id)
        for text in (NARROW_NO_LINK, REWORDED):
            done = self.save(text)
            self.assertIn(self.broad.id, done.stderr)
        self.assertEqual(self.ids(), [self.broad.id])

    def test_different_ways_of_working_in_the_same_project_are_saved(self):
        self.opened_task(self.broad.id)
        for name, (title, when) in DIFFERENT.items():
            if name == "rename":
                continue                     # same file, close words: under the bar for a piece the task followed
            done = self.save(text_of(title, when))
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.ids()), len(DIFFERENT))

    def test_without_opening_it_even_close_neighbours_are_saved(self):
        self.opened_task()
        for title, when in DIFFERENT.values():
            done = self.save(text_of(title, when))
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.ids()), 1 + len(DIFFERENT))

    def test_a_persons_piece_is_never_changed_and_the_overlap_is_shown(self):
        mine = store.create("Add a recipe to the book list", "adding a recipe to book/recipes.ts by hand",
                            "1. Append it.\n", projects=["demo"])
        before = mine.path.read_bytes()
        store.set_status(self.broad.id, "retired", "test")                     # only the person's piece is left
        self.opened_task(mine.id)
        done = self.save(NARROW)
        self.assertEqual(done.returncode, 0, done.stderr)                      # created...
        self.assertEqual(mine.path.read_bytes(), before)                       # ...the person's piece untouched
        new = next(p for p in store.all_pieces() if p.id not in (mine.id, self.broad.id))
        self.assertIn(f"the same way of working as {mine.id}, not changed", new.history[0])
        saved = [e for e in ev.events() if e.get("type") == "learn" and e.get("decision") == "saved"][-1]
        self.assertEqual(saved["overlaps"], [mine.id])
        report = self.cli.run_athos("report", cwd=self.work).stdout
        self.assertIn(f"same way of working as {mine.id}", report)
        audit = json.loads(self.cli.run_athos("audit", "--json", "--project", "demo", cwd=self.work).stdout)
        [rule] = [r for s in audit["sessions"] for r in s["rules"] if r["rule"] == "overlapping_pieces"]
        self.assertEqual(rule["status"], "flagged")
        self.assertEqual(rule["found"][0]["piece"], new.id)

    def test_a_set_aside_piece_is_not_bypassed(self):
        from athos import grade
        for n in range(grade.MAX_FAILED_VERSIONS):                             # three texts rejected in a row
            p = store.get(self.broad.id)
            ev.audit({"type": "verify", "piece": p.id, "version": p.version, "outcome": "fail",
                      "body_sha": grade.body_sha(p), "verdict": {"reusable": False}, "why": {"reusable": "no"}})
            if n < grade.MAX_FAILED_VERSIONS - 1:
                store.update(p.id, f"try {n + 2}", body=p.body + f"\nTry {n + 2}.\n")
        self.assertTrue(grade.rejection(store.get(self.broad.id))["set_aside"])
        self.opened_task(self.broad.id)
        done = self.save(NARROW)
        self.assertIn("waits for the person", done.stderr)
        self.assertEqual(self.ids(), [self.broad.id])


class ExistingOverlapsTest(_HookedTask):
    def test_overlapping_candidates_already_in_a_store_are_surfaced_not_merged(self):
        make = lambda text: store.create(*(lambda m: (m["title"], m["when"]))(store.parse_frontmatter(text)[0]),
                                         text.split("---\n", 2)[2], projects=["demo"], status="candidate",
                                         learned_by="claude-opus-5-5", confidence="0.3")
        broad, narrow = make(BROAD), make(NARROW)
        other = store.create(*DIFFERENT["release"], "x", projects=["demo"], status="candidate",
                             learned_by="claude-opus-5-5")
        before = {p.id: p.path.read_bytes() for p in store.all_pieces()}
        pairs = wiki.overlapping()
        self.assertEqual([(x["piece"], x["other"]) for x in pairs], [(broad.id, narrow.id)])
        report = self.cli.run_athos("report", cwd=self.work).stdout
        self.assertIn(f"same way of working as {narrow.id}", report)
        self.assertNotIn(f"same way of working as {other.id}", report)
        self.assertEqual({p.id: p.path.read_bytes() for p in store.all_pieces()}, before)   # nothing changed


class CalibrationTest(_HookedTask):
    """The page-level score on synthetic pairs, on both sides of the bars (wiki.SAME_WAY, wiki.SAME_WAY_OPENED)."""

    def test_scores(self):
        broad = store.parse(BROAD.replace("---\ntitle", "---\nid: add-a-recipe-to-the-cookbook\ntitle"))
        score = lambda text: wiki.same_way_score(store.parse(text), broad)
        self.assertGreaterEqual(score(NARROW), wiki.SAME_WAY)                # names its file, links its steps
        self.assertGreaterEqual(score(NARROW_NO_LINK), wiki.SAME_WAY_OPENED)
        self.assertGreaterEqual(score(REWORDED), wiki.SAME_WAY_OPENED)
        self.assertGreaterEqual(score(BROAD), 1.0)                           # the same page
        for name, (title, when) in DIFFERENT.items():
            s = score(text_of(title, when))
            self.assertLess(s, wiki.SAME_WAY, name)
            if name != "rename":
                self.assertLess(s, wiki.SAME_WAY_OPENED, name)


if __name__ == "__main__":
    import unittest
    unittest.main()
