"""The memory core: Athos's parts as swappable services, the overnight review that proposes what to keep, and the same
learning loop in Claude Code and Codex (their hooks) as in Claude Desktop."""

import json
import os
import subprocess
import sys
from pathlib import Path

from athos import consolidate, rating, services, session, store, trail
from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")
PIECE = """---
title: Cut a release
when: cut a release of the package
---
## #bump
**When:** starting.
**Do:** bump the version.

## #tag
**When:** after the bump.
**Do:** tag and push.
"""


def rating_event(stars, step="tag", piece="release", version=1, task="t1", did="tagged on main"):
    return {"type": "rating", "id": f"r{stars}{task}", "stars": stars, "piece": piece, "step": step, "label": "Tag",
            "version": version, "task_id": task, "request": "cut a release", "did": did, "at": "2026-11-11T10:00:00"}


class ServicesTest(TempHome):
    def tearDown(self):
        for name in services.DEFAULTS:
            services.use(name, None)
        super().tearDown()

    def test_defaults_are_athos_own_and_keep_their_contracts(self):
        store.create("Release", "cut a release", "## #tag\n**Do:** tag.\n", piece_id="release")
        self.assertEqual([p.id for p in services.get("store").all_pieces()], ["release"])
        self.assertTrue(isinstance(services.get("consolidator"), services.Consolidator))
        self.assertTrue(callable(services.get("recorder").events))
        with self.assertRaises(KeyError):
            services.get("nope")

    def test_a_service_is_swapped_by_code_or_by_the_environment(self):
        class Fake:
            def review(self, events, pieces):
                return {"proposals": [], "trajectories": [], "fake": True}
        services.use("consolidator", Fake())
        self.assertTrue(consolidate.run(write=False)["fake"])
        with self.assertRaises(TypeError):
            services.use("consolidator", object())                   # it must keep the contract
        services.use("consolidator", None)
        os.environ["ATHOS_SERVICES"] = "consolidator=tests.test_memory_core:EnvReview"
        try:
            self.assertTrue(consolidate.run(write=False)["from_env"])
        finally:
            os.environ.pop("ATHOS_SERVICES")


class EnvReview:
    def review(self, events, pieces):
        return {"proposals": [], "trajectories": [], "from_env": True}


class ReviewTest(TempHome):
    def setUp(self):
        super().setUp()
        store.create("Cut a release", "cut a release of the package", PIECE.split("---\n", 2)[2], piece_id="release")

    def test_two_low_ratings_propose_a_rule_to_avoid_with_their_evidence(self):
        out = consolidate.Review().review([rating_event(1, task="a"), rating_event(2, task="b")], store.all_pieces())
        [p] = out["proposals"]
        self.assertEqual((p["kind"], p["piece"], p["step"]), ("avoid", "release", "tag"))
        self.assertEqual([e["stars"] for e in p["evidence"]], [1, 2])
        self.assertIn("tagged on main", p["evidence"][0]["did"])

    def test_one_low_rating_is_enough_when_the_task_was_also_marked_corrected(self):
        events = [rating_event(2, task="a"), {"type": "mark", "task_id": "a", "result": "corrected"}]
        self.assertEqual(consolidate.Review().review(events, store.all_pieces())["proposals"][0]["kind"], "avoid")
        self.assertEqual(consolidate.Review().review(events[:1], store.all_pieces())["proposals"], [])

    def test_two_high_ratings_keep_the_mechanic_and_old_versions_do_not_count(self):
        high = [rating_event(5, task="a"), rating_event(4, task="b")]
        self.assertEqual(consolidate.Review().review(high, store.all_pieces())["proposals"][0]["kind"], "keep")
        store.update("release", note="learned from the stars", body=store.get("release").body + "\n")  # v2: acted on
        self.assertEqual(consolidate.Review().review(high, store.all_pieces())["proposals"], [])

    def test_a_replay_writes_nothing_and_an_approved_proposal_becomes_an_adjust_request_once(self):
        events = [rating_event(1, task="a"), rating_event(2, task="b")]
        dry = consolidate.run(events, write=False)
        self.assertEqual(len(dry["proposals"]), 1)
        self.assertFalse(consolidate.path().exists())
        consolidate.run(events)
        text = consolidate.apply(1, "es")
        self.assertTrue(text.startswith("Athos · ajustar release#tag: lo califiqué bajo 2 veces"))
        self.assertIn("«tagged on main»", text)
        self.assertEqual(consolidate.run(events)["proposals"], [])              # not proposed again

    def test_trajectories_count_the_tasks_that_walked_each_page_and_their_stars(self):
        events = [{"type": "trail", "kind": "step", "piece": "release", "step": "tag", "task_id": t} for t in "ab"]
        out = consolidate.Review().review(events + [rating_event(4)], store.all_pieces())
        self.assertEqual(out["trajectories"], [{"page": "release", "tasks": 2, "stars": 4.0}])


class HooksTest(TempHome):
    """Claude Code and Codex: the same loop through hooks and the `athos` command."""

    def run_athos(self, *args, stdin=""):
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=self.home, env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli",
                                                  "GIT_CONFIG_GLOBAL": os.path.join(self.home, "gitconfig")})

    def hook(self, event, payload):
        r = self.run_athos("hook", event, stdin=json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_did_stars_the_next_request_and_the_receipt(self):
        self.run_athos("save", stdin=PIECE)
        ev = {"session_id": "h1", "cwd": self.home}
        self.hook("session-start", ev)
        ctx = self.hook("prompt", {**ev, "prompt": "cut a release of the package"})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("--did", ctx)
        self.run_athos("step", "cut-a-release#bump")
        self.run_athos("step", "cut-a-release#tag", "--did", "bumped to 0.3.0")
        # A sandboxed agent's command, read from the tool hook.
        self.hook("tool", {**ev, "tool_name": "Bash", "tool_input": {"command": 'athos step --new "announce" --did "tagged v0.3.0"'}})
        view = trail.view(session.load("h1"))
        self.assertEqual(view["pieces"][0]["steps"][0]["did"], "bumped to 0.3.0")
        rating.rate("h1", 2, "cut-a-release", "bump")                             # from the panel beside the agent
        self.hook("stop", ev)
        self.assertEqual(session.load("h1")["task_end"]["task_id"], session.load("h1")["task_id"])
        ctx = self.hook("prompt", {**ev, "prompt": "cut a release of the package again"})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Rating from the person, in Athos's panel: 2/5", ctx)
        self.assertIn("There you had done: bumped to 0.3.0", ctx)
        self.assertIn("Ratings: the person can rate any step", ctx)              # what it means, said openly

    def test_session_start_offers_the_review_once_it_has_proposals(self):
        self.run_athos("save", stdin=PIECE)
        from athos import eval as ev
        for t in "ab":
            ev.append(rating_event(1, piece="cut-a-release", task=t))
        ctx = self.hook("session-start", {"session_id": "h2", "cwd": self.home})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("proposes 1 change(s)", ctx)
        self.assertIn("dream --apply N", ctx)
        out = self.run_athos("dream").stdout
        self.assertIn("1. «Cut a release» · «Tag» → avoid (1★, 1★)", out)
        self.assertIn("Athos · adjust cut-a-release#tag", self.run_athos("dream", "--apply", "1").stdout)
