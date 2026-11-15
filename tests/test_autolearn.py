"""Autonomous learning: piece status and provenance, Check lines, evidence, the autonomous save, the independent
verifier, promotion and demotion, risk lanes, the apply tier, repairing polluted statistics and the audit rules.
Everything here is offline: the verifier's model runner is stubbed."""

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from athos import load, store, wiki
from tests.helpers import TempHome

LEGACY = """---
id: old-way
title: Old way
when: doing the old thing
projects: [proj]
created: 2026-01-01
last_used: 2026-01-02
origin:
  platform: claude-code
  model: claude-opus-5-5
version: 3
---

## #first
**When:** starting.
**Do:** run `make test`.
**Because:** it caught a bug once.

## History
- v3 2026-01-02 (claude-code, claude-opus-5-5): tidied
- v2 2026-01-01 (claude-code, claude-opus-5-5): more
- v1 2026-01-01 (claude-code, claude-opus-5-5): created
"""

BODY = """## #run_tests
**When:** after changing the parser.
**Do:** run the unit tests.
**Check:** `python3 -m unittest discover -s tests` exits 0
**Because:** the parser has many edge cases.
**Links:** [[parser-change#bump]]

## #bump
**When:** the tests pass.
**Do:** bump the version in `VERSION`.
**Check:** `cat VERSION` shows the new number
"""


class StatusFieldsTest(TempHome):
    def test_a_legacy_file_is_written_back_unchanged_and_behaves_as_verified(self):
        piece = store.parse(LEGACY)
        self.assertEqual(store.render(piece), LEGACY)
        self.assertEqual(store.status(piece), "legacy")
        self.assertTrue(store.usable_as_verified(piece))
        self.assertIsNone(store.confidence(piece))

    def test_the_new_fields_round_trip(self):
        piece = store.parse(LEGACY)
        piece.status, piece.risk, piece.confidence = "candidate", "high", "0.3"
        piece.learned_by, piece.last_verified = "claude-fable-5-2", "2026-11-01"
        piece.evidence = ["verify:unittest:ok", "commit", "task:abc123"]
        text = store.render(piece)
        again = store.parse(text)
        self.assertEqual(store.render(again), text)
        self.assertEqual((again.status, again.risk, store.confidence(again)), ("candidate", "high", 0.3))
        self.assertEqual(again.evidence, ["verify:unittest:ok", "commit", "task:abc123"])
        self.assertFalse(store.usable_as_verified(again))

    def test_evidence_items_never_break_the_inline_list(self):
        piece = store.parse(LEGACY)
        piece.evidence = ["a, b", "c[d]"]
        self.assertEqual(store.parse(store.render(piece)).evidence, ["a  b", "c d"])

    def test_an_update_keeps_the_fields_and_history(self):
        p = store.create("Parser change", "changing the parser", BODY, projects=["proj"], status="candidate",
                         learned_by="claude-opus-5-5", evidence=["commit"], confidence="0.3", risk="normal")
        improved, _ = store.update(p.id, "clearer", body=BODY + "\nmore\n")
        self.assertEqual((improved.status, improved.learned_by, improved.evidence), ("candidate", "claude-opus-5-5",
                                                                                     ["commit"]))
        self.assertEqual(improved.version, 2)

    def test_retiring_supersedes_and_revert_restores(self):
        p = store.create("Parser change", "changing the parser", BODY, projects=["proj"], status="verified")
        retired = store.set_status(p.id, "retired", "3 failures in the last 5 uses")
        self.assertEqual((retired.status, retired.version), ("retired", 2))
        self.assertIn("verified → retired", retired.history[0])
        self.assertTrue((store.paths.history() / p.id / "v1.md").is_file())     # nothing deleted
        back = store.revert(p.id)
        self.assertEqual((back.status, back.version), ("verified", 3))

    def test_a_status_change_is_not_a_use(self):
        p = store.create("Parser change", "changing the parser", BODY, projects=["proj"], status="candidate")
        p.last_used = "2026-01-01"
        store._write(p)
        self.assertEqual(store.set_status(p.id, "verified", "verifier passed").last_used, "2026-01-01")

    def test_set_meta_changes_bookkeeping_in_place(self):
        p = store.create("Parser change", "changing the parser", BODY, projects=["proj"], status="candidate")
        store.set_meta(p.id, confidence="0.5", status="verified")          # status only through set_status
        again = store.get(p.id)
        self.assertEqual((again.confidence, again.status, again.version), ("0.5", "candidate", 1))


class CheckLinesTest(TempHome):
    def test_a_check_line_is_parsed_per_statement(self):
        p = store.create("Parser change", "changing the parser", BODY, projects=["proj"])
        checks = [s.check for s in wiki.statements(p)]
        self.assertEqual(checks, ["`python3 -m unittest discover -s tests` exits 0", "`cat VERSION` shows the new number"])

    def test_the_check_survives_an_update_and_the_steps_only_form(self):
        p = store.create("Parser change", "changing the parser", BODY + "\n" + "filler " * 2000, projects=["proj"])
        p, _ = store.update(p.id, "longer", body=p.body)
        text, cut, left, steps = load._fit([p], "athos", cap=1500)
        self.assertEqual(steps, [p.id])                                    # given as its steps only
        self.assertIn("**Check:** `python3 -m unittest discover -s tests` exits 0", text)
        self.assertNotIn("**Because:**", text)

    def test_the_capture_guide_asks_for_checks(self):
        from athos import capture
        self.assertIn("**Check:**", capture.guide())


if __name__ == "__main__":
    unittest.main()
