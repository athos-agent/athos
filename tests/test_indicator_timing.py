"""The indicator follows the work, not a fixed twenty minutes: it stays on through a long tool call (a stamped call
that has not ended), goes off a few minutes after the session stopped moving, and at once when the transcript says
the person interrupted the turn. Synthetic sessions."""

import json
import os
import time
from pathlib import Path

from athos import indicator, session
from tests.helpers import TempHome


class IndicatorTimingTest(TempHome):
    def state(self, **more):
        st = {"task_id": "t1", "task_loaded": ["p"], "task_delivery": "piece", "model": "claude-haiku-5-5", **more}
        session.save("s1", st)
        return st

    def age(self, seconds):
        f = session._file("s1")
        t = time.time() - seconds
        os.utime(f, (t, t))

    def test_it_goes_off_a_few_minutes_after_an_interrupted_turn(self):
        self.state()
        self.age(10 * 60)
        self.assertEqual(indicator.compute("s1")[0], indicator.IDLE)

    def test_it_stays_on_through_a_long_tool_call(self):
        self.state()
        session.live_start("s1", "c1", {"at": time.time() - 25 * 60, "tool": "Bash"})
        self.age(25 * 60)
        self.assertEqual(indicator.compute("s1")[0], indicator.COLLABORATING)

    def test_an_interruption_in_the_transcript_ends_it_at_once(self):
        transcript = Path(self.home, "t.jsonl")
        transcript.write_text(json.dumps({"type": "user", "message": {"content": "fix it"}}) + "\n"
                              + json.dumps({"type": "user", "message": {"content": [
                                  {"type": "text", "text": "[Request interrupted by user]"}]}}) + "\n")
        self.state(transcript_path=str(transcript))
        self.assertEqual(indicator.compute("s1"), (indicator.IDLE, "interrupted"))
