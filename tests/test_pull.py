"""Pull instead of push: a frontier model gets a short index of the pieces in reach and opens the one it needs with
`athos show`, which the tool hook counts as use; an apply model (or one of unknown tier) gets the piece itself. All
data here is synthetic."""

from athos import load, session
from tests.test_audit import HookCase, events, log_text, piece

BODY = "## #one\n**When:** at the start.\n**Do:** the first thing, as the team does it.\n"


class PullTest(HookCase):
    def setUp(self):
        super().setUp()
        piece("ship-release", "Ship a release with the checklist", "shipping a release of the app", ["alpha"], BODY)
        piece("rotate-keys", "Rotate the signing keys", "rotating the keys before a release", ["alpha"], BODY)
        piece("write-report", "Write the weekly report", "writing the weekly report for the team", ["beta"], BODY)
        self.ev = {"session_id": "p1", "cwd": str(self.alpha)}

    def ask(self, prompt, model=None):
        out = self.hook("prompt", {**self.ev, "prompt": prompt, **({"model": model} if model else {})})
        return out["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_a_frontier_model_gets_an_index_and_opening_a_piece_is_use(self):
        told = self.ask("please ship the release of the app", "claude-opus-5-5")
        self.assertIn("`ship-release` — Ship a release with the checklist", told)
        self.assertIn(" show <id>`", told)                                     # how to open one
        self.assertNotIn("the first thing, as the team does it", told)        # not the piece's text
        self.assertNotIn("write-report", told)                                  # another project's piece
        lines = [ln for ln in told.splitlines() if ln.startswith("- `")]
        self.assertEqual(lines[0].split("`")[1], "ship-release")                # the router's choice first
        self.assertIn("rotate-keys", told)                                      # then the rest in reach
        (r,) = events("route")
        self.assertEqual((r["delivery"], r["chosen"], r["offered"]),
                         ("index", ["ship-release"], ["ship-release", "rotate-keys"]))
        self.assertEqual(r["injected_chars"], r["index_chars"])
        self.assertLess(r["index_chars"], r["piece_chars"])
        self.assertTrue(r["collaborates"])
        state = session.load("p1")
        self.assertEqual((state["task_loaded"], state["task_offered"], state["task_delivery"]),
                         ([], ["ship-release", "rotate-keys"], "index"))
        self.assertIn("index of 2 (ship-release, rotate-keys)", log_text())
        # The model opens the piece through its shell: that is the use, recorded for this task.
        self.hook("tool", {**self.ev, "tool_name": "Bash", "tool_input": {"command": "athos show ship-release"}})
        (o,) = events("piece_opened")
        self.assertEqual((o["piece"], o["offered"], o["task_id"]), ("ship-release", True, r["task_id"]))
        self.assertEqual(session.load("p1")["task_loaded"], ["ship-release"])

    def test_an_apply_model_or_an_unknown_one_gets_the_piece(self):
        for n, model in enumerate(("claude-haiku-5-5", None)):
            self.ev["session_id"] = f"p{n + 2}"
            told = self.ask("please ship the release of the app", model)
            self.assertIn("the first thing, as the team does it", told)
            r = events("route")[-1]
            self.assertEqual((r["delivery"], r["offered"]), ("piece", []))
            self.assertEqual(session.load(f"p{n + 2}")["task_loaded"], ["ship-release"])

    def test_nothing_chosen_means_nothing_at_all_on_either_tier(self):
        for model in ("claude-opus-5-5", "claude-sonnet-5-5"):
            self.assertEqual(self.ask("what time is it", model), "")
            self.assertEqual(events("route")[-1]["delivery"], None)

    def test_the_index_is_small_and_bounded(self):
        for i in range(12):
            piece(f"ship-variant-{i}", f"Ship a release variant {i} " + "with many words " * 8,
                  "shipping a release of the app " + "in a very particular way " * 12, ["alpha"], BODY)
        text, ids = load.pull_index([], {}, [p for p in load.store.all_pieces() if "alpha" in p.projects])
        self.assertLessEqual(len(ids), load.PULL_LINES)
        self.assertLessEqual(len(text), load.PULL_CAP)
        told = self.ask("please ship the release of the app", "claude-fable-5-2")
        self.assertLessEqual(len(told), load.PULL_CAP)
        self.assertLessEqual(len(events("route")[-1]["offered"]), load.PULL_LINES)
