"""Which signals may move a learned piece: only strong evidence tied to that piece changes its status. A change of the
person's credited to another piece or to none, a revert, or a reaction read from words never demotes or retires a
piece; outcomes count from the piece's last status change or revert; and the session that wrote a piece does not
count its reuse. Synthetic pieces and events only."""

import unittest

from athos import eval as ev, evidence, grade, store
from tests.helpers import TempHome

BODY = """## #run_tests
**When:** after changing the parser.
**Do:** run the unit tests.
**Check:** `python3 -m unittest discover -s tests` exits 0
"""
PASS = {"type": "verify", "kind": "test", "label": "unittest", "ok": True, "strength": "strong", "polarity": "positive"}


def learned(title="Parser change", status="verified", **more):
    return store.create(title, "changing the parser", BODY, projects=["demo"], status=status,
                        learned_by="claude-opus-5-5", confidence="0.8", risk="normal", **more)


def finish(task, loaded, model="claude-opus-5-5", saved=(), session_saved=()):
    return grade.finish_task("s1", task, {"task_loaded": list(loaded), "task_saved": list(saved),
                                          "saved": list(session_saved), "model": model})


class TiedEvidenceTest(TempHome):
    def test_an_edit_credited_to_no_piece_or_another_piece_demotes_nothing(self):
        a, b = learned("Alpha"), learned("Beta")
        evidence.add("t1", dict(PASS))
        evidence.add("t1", {"type": "person_edit", "strength": "strong", "polarity": "negative", "piece": None})
        evidence.add("t1", {"type": "person_edit", "strength": "strong", "polarity": "negative", "piece": b.id})
        out = {e["piece"]: e for e in finish("t1", [a.id, b.id])}
        self.assertNotIn(out[a.id]["outcome"], ("corrected", "failed"))
        self.assertEqual(store.get(a.id).status, "verified")
        self.assertEqual(out[b.id]["outcome"], "corrected")                     # the edit named it
        self.assertEqual(store.get(b.id).status, "candidate")

    def test_a_revert_is_not_held_against_every_loaded_piece(self):
        a, b = learned("Alpha"), learned("Beta")
        evidence.add("t1", dict(PASS))
        evidence.add("t1", {"type": "revert", "strength": "strong", "polarity": "negative"})
        out = finish("t1", [a.id, b.id])
        self.assertEqual({e["outcome"] for e in out}, {"unverified"})          # not clean, not corrected either
        self.assertEqual([store.get(p).status for p in (a.id, b.id)], ["verified", "verified"])

    def test_a_reaction_from_words_only_lowers_confidence(self):
        a = learned("Alpha")
        evidence.add("t1", dict(PASS))
        evidence.note_reaction("t1", "corrected")
        [e] = finish("t1", [a.id])
        self.assertNotIn(e["outcome"], ("corrected", "failed"))
        self.assertIn("reaction_corrected", e["basis"])
        p = store.get(a.id)
        self.assertEqual(p.status, "verified")
        self.assertLess(store.confidence(p), 0.8)
        for task in ("t2", "t3", "t4"):                                          # three in a row retire nothing
            evidence.add(task, dict(PASS))
            evidence.note_reaction(task, "corrected")
            finish(task, [a.id])
        self.assertEqual(store.get(a.id).status, "verified")

    def test_its_own_check_failing_still_counts(self):
        a = learned("Alpha")
        evidence.add("t1", {**PASS, "ok": False, "polarity": "negative", "check_of": f"{a.id}#run_tests"})
        [e] = finish("t1", [a.id])
        self.assertEqual((e["outcome"], e["basis"]), ("corrected", ["check_failed"]))
        self.assertEqual(store.get(a.id).status, "candidate")


class SinceTheLastChangeTest(TempHome):
    def test_a_reverted_piece_is_not_retired_again_by_its_next_clean_reuse(self):
        a = learned("Alpha", status="candidate")
        for task in ("t1", "t2", "t3"):
            evidence.add(task, {**PASS, "ok": False, "polarity": "negative", "check_of": f"{a.id}#run_tests"})
            finish(task, [a.id])
        self.assertEqual(store.get(a.id).status, "retired")
        store.revert(a.id)
        self.assertEqual(store.get(a.id).status, "candidate")
        evidence.add("t4", dict(PASS))
        [e] = finish("t4", [a.id])
        self.assertEqual(e["outcome"], "clean")
        self.assertEqual(store.get(a.id).status, "candidate")                   # not retired again


class WritingSessionTest(TempHome):
    def test_a_reuse_in_the_session_that_wrote_the_piece_does_not_count(self):
        a = learned("Alpha", status="candidate")
        evidence.add("t2", dict(PASS))
        self.assertEqual(finish("t2", [a.id], session_saved=[a.id]), [])
        self.assertEqual([e for e in ev.events() if e.get("type") == "reuse"], [])


if __name__ == "__main__":
    unittest.main()
