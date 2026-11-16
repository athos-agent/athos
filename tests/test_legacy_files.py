"""A piece with no `status` (written by the person, or before autonomous learning) is the person's file: Athos never
rewrites it unless the person asks for a change to that piece. Using it, grading it, ageing it and bookkeeping are
recorded in events instead. All data here is synthetic."""

import contextlib
import io
import json
import sys
from pathlib import Path
from unittest import mock

from athos import cli, eval as ev, grade, paths, store
from tests.helpers import TempHome

HAND_WRITTEN = """---
# my own notes, keep them
id: hand-ship
title:   Ship the hand release
when: "shipping the hand release: carefully"
projects: [hand]
owner: me            # a key Athos does not know
created: 2025-01-02
last_used: 2025-01-03
origin:
  platform: by-hand
version: 3
---

## #ship
**When:**  shipping the hand release.
**Do:** run the release script, then check the tag.

Some free text   with odd   spacing.

## History
- v3 2025-01-03: tidied

## History
- v2 2025-01-02: first, kept twice by hand"""                      # no newline at the end


class LegacyFileTest(TempHome):
    def setUp(self):
        super().setUp()
        self.folder = Path(self.home) / "hand"
        self.folder.mkdir()
        self.file = paths.know_how() / "hand-ship.md"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(HAND_WRITTEN)
        self.before = self.file.read_bytes()

    def hook(self, name, payload):
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(io.StringIO()):
            cli.hook(name)

    def test_a_session_that_loads_and_uses_it_leaves_it_byte_identical(self):
        e = {"session_id": "lg1", "cwd": str(self.folder)}
        self.hook("session-start", {**e, "model": "claude-haiku-5-1"})
        self.hook("prompt", {**e, "prompt": "ship the hand release"})
        self.assertIn("hand-ship", json.dumps([x for x in ev.events() if x.get("type") == "route"]))
        self.hook("tool", {**e, "tool_name": "Bash", "tool_input": {"command": "athos show hand-ship"}})
        self.hook("tool-failed", {**e, "tool_name": "Bash", "tool_input": {"command": "pytest -q"},
                                  "tool_response": {"stdout": "1 failed"}})
        self.hook("stop", e)
        self.hook("prompt", {**e, "prompt": "that was wrong, it broke the release"})
        self.hook("stop", e)
        self.hook("session-start", {**e, "model": "claude-haiku-5-1"})
        self.assertEqual(self.file.read_bytes(), self.before)

    def test_grading_ageing_and_bookkeeping_record_instead_of_rewriting(self):
        self.assertFalse(grade.demote("hand-ship", "corrected on an apply model", strong=True))
        store.touch("hand-ship")
        store.set_meta("hand-ship", confidence="0.30", evidence=["test:fail"])
        self.assertIsNone(store.set_status("hand-ship", "retired", "three failures"))
        grade.age_all()
        self.assertEqual(self.file.read_bytes(), self.before)
        (g,) = [x for x in ev.events() if x.get("type") == "grade"]
        self.assertEqual((g["piece"], g["from"], g["to"]), ("hand-ship", "legacy", "legacy"))
        self.assertIn("hand-ship", grade.reviews())

    def test_the_persons_own_change_still_writes_it(self):
        store.update("hand-ship", "the person's change", body="## #ship\n**When:** now.\n**Do:** the new way.\n")
        self.assertIn("the new way", self.file.read_text())
        self.assertEqual(store.get("hand-ship").version, 4)
