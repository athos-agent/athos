"""The edit detector fails towards "nobody": a change another writer could have made is never the person's. Each case
runs the real hooks in a child process with the fields Claude Code sends (a PreToolUse stamp with the call's id, the
end hook with `duration_ms`, subagents' `agent_id`, `run_in_background` and its `backgroundTaskId`, the Stop hook's
`background_tasks`). Synthetic files only."""

import json
import subprocess
import sys
import time
import unittest

from athos import edits, session
from tests.test_edits import REPORT, HookCase, edit_events


class NobodysChangeTest(HookCase):
    def setUp(self):
        super().setUp()
        self.hook("prompt", {**self.ev, "prompt": "review a services contract for a client"})
        self.report = self.agent_writes()
        self.n = 100

    def tool(self, hook, tool, tool_input, call, ms=10, **more):
        payload = {**self.ev, "tool_name": tool, "tool_input": tool_input, "tool_use_id": call, **more}
        if hook != "tool-start":
            payload["duration_ms"] = ms
        r = self.run_athos("hook", hook, stdin=json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)

    def given_to_person(self):
        return [e for e in edit_events(self.home) if e.get("attributed_to") == "person"]

    def nobody_because(self):
        return [e["basis"][0] for e in edit_events(self.home) if e["decision"] == "unattributed"]

    def test_another_plugins_formatter_right_after_the_write(self):
        time.sleep(0.2)
        self.report.write_text(REPORT.replace("\n- ", "\n* "))                 # a formatter hook, not the person
        time.sleep(edits.MARGIN_S + 0.3)
        self.tool("tool-start", "Read", {"file_path": "x.md"}, "r1")
        self.tool("tool", "Read", {"file_path": "x.md"}, "r1")
        self.assertEqual(self.given_to_person(), [])
        self.assertIn("within_grace_after_a_call:Read", self.nobody_because())

    def test_a_hook_that_starts_late(self):
        self.age_clock()
        self.tool("tool-start", "Bash", {"command": "python3 fix.py"}, "b1")
        self.report.write_text(REPORT.replace("should pay", "pays"))          # the command's own change, at once
        time.sleep(edits.MARGIN_S + 0.6)                                       # its end hook comes late
        self.tool("tool", "Bash", {"command": "python3 fix.py"}, "b1", ms=100)
        self.assertEqual(self.given_to_person(), [])

    def test_two_subagents_one_writing_while_the_other_reads(self):
        self.age_clock()
        self.tool("tool-start", "Bash", {"command": "python3 long_job.py"}, "a1", agent_id="sub-a")
        self.report.write_text(REPORT.replace("should pay", "pays"))          # subagent A's long command writes
        time.sleep(edits.MARGIN_S + 0.3)
        self.tool("tool-start", "Read", {"file_path": "x.md"}, "b1", agent_id="sub-b")
        self.tool("tool", "Read", {"file_path": "x.md"}, "b1", ms=5, agent_id="sub-b")
        self.assertEqual(self.given_to_person(), [])

    def test_a_task_left_running_in_the_background(self):
        self.age_clock()
        self.tool("tool-start", "Bash", {"command": "sleep 1; ./gen.sh", "run_in_background": True}, "g1")
        self.tool("tool", "Bash", {"command": "sleep 1; ./gen.sh", "run_in_background": True}, "g1", ms=3,
                  tool_response={"stdout": "", "backgroundTaskId": "bg1"})
        time.sleep(0.2)
        self.report.write_text(REPORT.replace("should pay", "pays"))          # the background task writes
        time.sleep(edits.MARGIN_S + 0.3)
        self.tool("tool-start", "Read", {"file_path": "x.md"}, "r2")
        self.tool("tool", "Read", {"file_path": "x.md"}, "r2")
        self.assertEqual(self.given_to_person(), [])
        self.assertIn("background_task_running:Read", self.nobody_because())

    def test_a_writer_right_after_the_turn_ended(self):
        self.hook("stop", self.ev)
        self.report.write_text(REPORT.replace("should pay", "pays"))          # another Stop hook, at once
        self.hook("prompt", {**self.ev, "prompt": "now draft the email"})
        self.assertEqual(self.given_to_person(), [])
        self.assertIn("within_grace_after_turn_end", self.nobody_because())

    def test_another_session_working_in_the_same_project(self):
        self.hook("stop", self.ev)
        self.age_clock()
        self.hook("prompt", {"session_id": "s2", "cwd": str(self.work), "prompt": "tidy the docs"})
        self.report.write_text(REPORT.replace("should pay", "pays"))          # the other session's agent?
        self.hook("prompt", {**self.ev, "prompt": "now draft the email"})
        self.assertEqual(self.given_to_person(), [])
        self.assertIn("another_session_active", self.nobody_because())

    def test_the_person_is_still_seen_when_nothing_else_could_have_written(self):
        self.hook("stop", self.ev)
        self.age_clock()
        self.report.write_text(REPORT.replace("should pay", "shall pay"))
        self.hook("prompt", {**self.ev, "prompt": "now draft the email"})
        self.assertEqual(len(self.given_to_person()), 1)


class OneFailureCostsNothingElseTest(HookCase):
    def test_the_evidence_is_noted_even_when_the_edit_detector_fails(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from unittest import mock
        from athos import cli, evidence
        session.save("s9", {"task_id": "t9", "model": "claude-opus-5-5"})
        event = {"session_id": "s9", "cwd": str(self.work), "tool_name": "Bash", "tool_input": {"command": "pytest -q"},
                 "tool_response": {"stdout": "3 passed", "stderr": "", "interrupted": False}}
        with mock.patch.object(edits, "on_tool", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps(event))), redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()):
            cli.hook("tool")
        self.assertEqual([i["ok"] for i in evidence.of_task("t9")], [True])


class TimingUnitTest(unittest.TestCase):
    def test_a_ctime_in_the_future_is_nobodys(self):
        now = time.time()
        clock = {"turn_end": now - 100, "tool_end": now - 200}
        self.assertEqual(edits._after_turn(now + 120, {"checked": now - 300}, clock)[1], "ctime_in_the_future")
        self.assertEqual(edits._between_calls(now + 120, {"checked": now - 300}, now, {}, {}, now, {})[1],
                         "ctime_in_the_future")

    def test_without_a_start_stamp_nothing_is_the_persons(self):
        now = time.time()
        self.assertEqual(edits._between_calls(now - 50, {"checked": now - 300}, None, {}, {}, now, {})[1],
                         "no_start_stamp")


if __name__ == "__main__":
    unittest.main()
