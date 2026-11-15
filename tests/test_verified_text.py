"""Verified means verified for that text: a change to a verified piece's title, when or body returns it to candidate,
and a revert to a text no verifier passed does too. Using and grading a learned piece leave its file alone: its last
use and its counters live beside it, and the file is written on a status change. Synthetic pieces only."""

import json
import unittest

from athos import eval as ev, evidence, grade, store
from tests.helpers import TempHome

BODY = """## #run_tests
**When:** after changing the parser.
**Do:** run the unit tests.
**Check:** `python3 -m unittest discover -s tests` exits 0
"""


def verified(**more):
    return store.create("Parser change", "changing the parser", BODY, projects=["demo"], status="verified",
                        learned_by="claude-opus-5-5", confidence="0.8", risk="normal", **more)


class TextChangeTest(TempHome):
    def test_a_new_body_title_or_when_returns_a_verified_piece_to_candidate(self):
        for change in ({"body": BODY + "\nAlso lint.\n"}, {"title": "Parser change, safely"},
                       {"when": "changing any parser"}):
            p = verified()
            q, _ = store.update(p.id, "edited", **change)
            self.assertEqual(q.status, "candidate", change)
            self.assertIn("candidate", q.history[0])
            self.assertEqual(store.get(p.id).status, "candidate")

    def test_the_same_text_or_a_new_project_keeps_it_verified(self):
        p = verified()
        q, _ = store.update(p.id, "tagged", projects=["other"])
        self.assertEqual(q.status, "verified")
        q, _ = store.update(p.id, "same", body=BODY)
        self.assertEqual(q.status, "verified")

    def test_a_revert_to_a_text_no_verifier_passed_is_a_candidate(self):
        p = store.create("Parser change", "changing the parser", BODY, projects=["demo"], status="verified",
                         learned_by="claude-opus-5-5", confidence="0.8", risk="normal")
        p2, _ = store.update(p.id, "reworded", body=BODY + "\nAlso lint.\n")       # now a candidate
        store.set_status(p.id, "verified", "test: verified again")
        back = store.revert(p.id, 1)                                             # the v1 text, verified, no pass
        self.assertEqual(back.status, "candidate")
        ev.audit({"type": "verify", "piece": p.id, "outcome": "pass", "body_sha": grade.body_sha(back),
                  "paths_only": True, "version": back.version})
        good = store.set_status(p.id, "verified", "test: verified")
        store.update(p.id, "reworded again", body=BODY + "\nAlso format.\n")
        self.assertEqual(store.revert(p.id, good.version).status, "verified")   # that text has its own pass


class FileLeftAloneTest(TempHome):
    def test_use_and_grading_do_not_rewrite_a_learned_piece(self):
        p = verified()
        p.last_used = "2026-01-01"
        store._write(p)
        before = p.path.read_bytes()
        store.touch(p.id)
        store.set_meta(p.id, confidence="0.9", evidence=["verifier:pass"], last_verified="2026-02-02")
        evidence.add("t1", {"type": "verify", "kind": "test", "label": "unittest", "ok": True, "strength": "strong",
                            "polarity": "positive"})
        grade.finish_task("s1", "t1", {"task_loaded": [p.id], "model": "claude-opus-5-5"})
        self.assertEqual(p.path.read_bytes(), before)
        now = store.get(p.id)
        self.assertEqual((now.last_used, now.last_verified, now.evidence), (store.today(), "2026-02-02",
                                                                             ["verifier:pass"]))
        self.assertGreater(store.confidence(now), 0.9)
        self.assertEqual(store.last_used(now), store.today())

    def test_a_status_change_writes_the_counters_into_the_file(self):
        p = verified()
        store.set_meta(p.id, confidence="0.9")
        store.set_status(p.id, "candidate", "test")
        text = store.get(p.id).path.read_text()
        self.assertIn("confidence: 0.9", text)
        self.assertNotIn(p.id, json.loads((store.paths.home() / "piece-meta.json").read_text()))


if __name__ == "__main__":
    unittest.main()
