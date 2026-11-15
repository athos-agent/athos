"""One piece of work is one task: a message the harness sends in the middle of it (a background task's notification,
a subagent's report) continues the task instead of starting a new one, so the work is graded once. Synthetic, through
the real hooks."""

import json

from athos import eval as ev, evidence, session, store
from tests.test_cli import ThroughTheLauncher

BODY = """## #run_tests
**When:** after changing the parser.
**Do:** run the unit tests.
**Check:** `python3 -m unittest discover -s tests` exits 0
"""


class HarnessMessageTest(ThroughTheLauncher):
    def test_a_notification_in_the_middle_does_not_start_a_new_task(self):
        p = store.create("Fix the parser", "fixing the parser of this project", BODY, projects=["work"],
                         status="candidate", learned_by="claude-opus-5-5", confidence="0.3", risk="normal")
        work = self.home + "/work"
        import os
        os.makedirs(work)
        e = {"session_id": "h1", "cwd": work, "transcript_path": None, "prompt_id": "p-1"}
        self.send("session-start", {**e, "model": "claude-opus-5-5"})
        self.send("prompt", {**e, "prompt": "fix the parser of this project"})
        session.update("h1", task_loaded=[p.id])
        first = session.load("h1")["task_id"]
        self.send("tool", {**e, "tool_name": "Bash", "tool_input": {"command": "python3 -m unittest -q"},
                           "tool_response": {"stdout": "Ran 3 tests\n\nOK", "stderr": "", "interrupted": False}})
        self.send("prompt", {**e, "prompt": "<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n"
                                            "</task-notification>"})
        self.assertEqual(session.load("h1")["task_id"], first)                  # the same task goes on
        self.assertEqual([x for x in ev.events() if x.get("type") == "reuse"], [])
        self.send("tool", {**e, "tool_name": "Bash", "tool_input": {"command": "python3 -m unittest -q"},
                           "tool_response": {"stdout": "Ran 3 tests\n\nOK", "stderr": "", "interrupted": False}})
        self.send("stop", e)
        self.send("prompt", {**e, "prompt_id": "p-2", "prompt": "thanks, now the docs"})
        reuses = [x for x in ev.events() if x.get("type") == "reuse"]
        self.assertEqual([(r["piece"], r["task_id"]) for r in reuses], [(p.id, first)])   # graded once
        self.assertEqual(len([i for i in evidence.of_task(first) if i["type"] == "verify"]), 2)
