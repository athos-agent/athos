"""One source of truth for what the person reads: a learned piece's moving numbers (confidence, last verified,
evidence) live beside its file, never in it, so the file can never show a stale number and a graded reuse never
rewrites it; `athos show` and `athos report` read the real ones. A piece the person owns keeps its file byte for byte.
Synthetic pieces only."""

import json
import re

from athos import eval as ev, evidence, grade, store
from tests.helpers import TempHome
from tests.test_autolearn import BODY

PASS = {"type": "verify", "kind": "test", "label": "unittest", "ok": True, "strength": "strong", "polarity": "positive"}
MOVING = re.compile(r"^(confidence|last_verified|evidence):", re.M)


def learned(**more):
    fields = {"status": "candidate", "learned_by": "claude-opus-5-5", "confidence": "0.3", "risk": "normal",
              "evidence": ["verify:unittest:ok", "task:t0"], **more}
    return store.create("Change the parser safely", "changing the parser", BODY, projects=["demo"], **fields)


class FileNumbersTest(TempHome):
    def test_a_learned_piece_file_never_holds_the_moving_numbers(self):
        p = learned()
        self.assertIsNone(MOVING.search(p.path.read_text()))
        self.assertEqual((store.get(p.id).confidence, store.get(p.id).evidence), ("0.3", ["verify:unittest:ok",
                                                                                           "task:t0"]))
        store.set_meta(p.id, confidence="0.25")
        store.set_status(p.id, "verified", "test")                    # a status change writes the file
        text = p.path.read_text()
        self.assertIsNone(MOVING.search(text))
        self.assertIn("status: verified", text)
        self.assertEqual(store.confidence(store.get(p.id)), 0.25)
        store.update(p.id, "clearer", body=BODY + "\nMore.\n")         # an improvement writes it too
        self.assertIsNone(MOVING.search(p.path.read_text()))
        self.assertEqual(store.confidence(store.get(p.id)), 0.25)

    def test_a_graded_reuse_does_not_touch_the_file(self):
        p = learned()
        before = p.path.read_bytes()
        evidence.add("t1", dict(PASS))
        grade.finish_task("s1", "t1", {"task_loaded": [p.id], "model": "claude-opus-5-5"})
        self.assertEqual(p.path.read_bytes(), before)
        self.assertAlmostEqual(store.confidence(store.get(p.id)), 0.4)

    def test_show_prints_the_real_numbers(self):
        from tests.test_cli import ThroughTheLauncher
        p = learned()
        store.set_meta(p.id, confidence="0.25")
        cli = ThroughTheLauncher()
        cli.home = self.home
        shown = cli.run_athos("show", p.id).stdout
        self.assertIn("confidence: 0.25", shown)
        self.assertNotIn("confidence: 0.3", shown)

    def test_a_persons_piece_is_left_byte_for_byte(self):
        mine = store.create("Mine", "my way", BODY, projects=["demo"])
        hand = mine.path.read_text().replace("version: 1", "confidence: 0.9\nversion: 1")
        mine.path.write_text(hand)
        self.assertEqual(store.move_bookkeeping(), [])
        self.assertEqual(mine.path.read_text(), hand)

    def test_an_old_file_with_a_stale_number_is_moved_once(self):
        p = learned()
        store.set_meta(p.id, confidence="0.25")
        stale = p.path.read_text().replace("version: 1", "confidence: 0.05\nlast_verified: 2026-01-01\nversion: 1")
        p.path.write_text(stale)                                         # what an older version left
        other = store.create("Other", "other things", BODY, projects=["demo"], status="candidate",
                             learned_by="claude-opus-5-5")
        other.path.write_text(other.path.read_text().replace("version: 1", "confidence: 0.6\nversion: 1"))
        self.assertEqual(sorted(store.move_bookkeeping()), sorted([p.id, other.id]))
        self.assertIsNone(MOVING.search(p.path.read_text()))
        self.assertEqual(store.confidence(store.get(p.id)), 0.25)       # the kept number wins over the file's
        self.assertEqual(store.get(p.id).last_verified, "2026-01-01")   # one only the file had moves beside it
        self.assertEqual(store.confidence(store.get(other.id)), 0.6)
        self.assertEqual(store.get(p.id).version, 1)                    # no new version
        self.assertEqual(store.move_bookkeeping(), [])                  # once

    def test_a_revert_keeps_todays_numbers(self):
        p = learned()
        store.update(p.id, "clearer", body=BODY + "\nMore.\n")
        store.set_meta(p.id, confidence="0.55")
        store.revert(p.id)
        self.assertEqual(store.confidence(store.get(p.id)), 0.55)


class ReportReusesTest(TempHome):
    def test_report_shows_evaluated_reuses(self):
        p = learned()
        for task in ("t1", "t2"):
            ev.append({"type": "task_start", "task_id": task, "session_id": "s" + task, "model": "claude-opus-5-5",
                       "project": "demo", "at": ev._iso(ev.now())})
            ev.append({"type": "task_end", "task_id": task, "session_id": "s" + task, "at": ev._iso(ev.now()),
                       "model": "claude-opus-5-5", "pieces": [p.id], "saved": []})
        evidence.add("t1", dict(PASS))
        grade.finish_task("st1", "t1", {"task_loaded": [p.id], "model": "claude-opus-5-5"})
        grade.finish_task("st2", "t2", {"task_loaded": [p.id], "model": "claude-opus-5-5"})   # nothing proved it
        row = next(r for r in ev.report()["pieces"] if r["piece"] == p.id)
        self.assertEqual((row["reuses_evaluated"], row["reuses_clean"]), (1, 1))
        text = ev.render(ev.report())
        self.assertIn("graded reuses 1 clean of 1", text)
        self.assertIn("confidence 0.40", text)
        self.assertEqual(json.loads(json.dumps(row))["status"], "candidate")


if __name__ == "__main__":
    import unittest
    unittest.main()
