import json
import os
import subprocess
import sys
from pathlib import Path

from athos import edits, session
from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")
PIECE = """---
title: Review a services contract
when: review a services contract for a client
---
## #penalties
**When:** reading the penalty clauses.
**Do:** list each penalty with its amount.

## #report
**When:** at the end.
**Do:** write the report.
"""
REPORT = "# Contract review\n\nPenalties:\n- The supplier should pay 10% per week of delay.\n- Fine of 5%.\n"


class EditsTest(TempHome):
    def run_athos(self, *args, stdin="", env=None, cwd=None):
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=cwd or self.home, env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli",
                                                  "GIT_CONFIG_GLOBAL": os.path.join(self.home, "gitconfig"),
                                                  **(env or {})})

    def hook(self, event, payload, env=None):
        r = self.run_athos("hook", event, stdin=json.dumps(payload), env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def context(self, out):
        return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")

    def setUp(self):
        super().setUp()
        self.work = Path(self.home) / "work"
        self.work.mkdir()
        self.ev = {"session_id": "s1", "cwd": str(self.work)}
        self.run_athos("save", stdin=PIECE)

    def agent_writes(self, name="report.md", text=REPORT, tool="Write", **tin):
        f = self.work / name
        f.write_text(text)
        self.hook("tool", {**self.ev, "tool_name": tool, "tool_input": tin or {"file_path": str(f), "content": text}})
        return f

    def snapshots(self, sid="s1"):
        return edits._index(sid)

    def test_a_hand_edit_is_offered_once_with_its_diff_and_noted_for_the_panels(self):
        self.hook("prompt", {**self.ev, "prompt": "review a services contract for a client"})
        self.hook("tool", {**self.ev, "tool_name": "Bash",
                           "tool_input": {"command": "athos step review-a-services-contract#penalties"}})
        f = self.agent_writes()
        snap = self.snapshots()
        self.assertEqual([(s["path"], s["pieces"], s["statement"]) for s in snap],
                         [(str(f), ["review-a-services-contract"], "review-a-services-contract#penalties")])
        self.assertTrue((Path(self.home) / "snapshots" / "s1" / f"{snap[0]['hash']}.txt").is_file())
        self.hook("stop", self.ev)
        f.write_text(REPORT.replace("The supplier should pay", "The supplier shall pay"))   # the person's hand
        ctx = self.context(self.hook("prompt", {**self.ev, "prompt": "now draft the email to the client"}))
        self.assertIn("the person edited what you wrote", ctx)
        self.assertIn("-- The supplier should pay", ctx)
        self.assertIn("+- The supplier shall pay", ctx)
        self.assertIn("«Review a services contract»", ctx)
        self.assertIn("review-a-services-contract#penalties", ctx)
        self.assertIn("Never save it without their yes", ctx)
        st = json.loads(self.run_athos("status", "--json", cwd=self.work).stdout)
        self.assertEqual(st["learned_from_edit"][0]["name"], "report.md")
        self.assertEqual(st["learned_from_edit"][0]["adjust_prompt"],
                         "Athos · adjust review-a-services-contract#penalties: ")
        # The panels' [Keep this rule]: the request it sends, then gone once sent.
        keep = "Athos · adjust review-a-services-contract#penalties: keep the rule you proposed from my edit of report.md"
        self.assertEqual([x["keep"] for x in st["trail"]["edits"]], [keep])
        self.assertEqual(self.snapshots(), [])
        self.assertFalse((Path(self.home) / "snapshots" / "s1").exists())       # deleted after use
        evs = [json.loads(x) for x in (Path(self.home) / "events.jsonl").read_text().splitlines()]
        self.assertEqual([e["file"] for e in evs if e["type"] == "learned_from_edit"], [str(f)])
        # Offered once: the next request says nothing, and the panels' note goes with the new task.
        self.assertNotIn("edited", self.context(self.hook("prompt", {**self.ev, "prompt": "yes, add it"})))
        self.assertIsNone(json.loads(self.run_athos("status", "--json", cwd=self.work).stdout)["learned_from_edit"])

    def test_nothing_is_said_when_the_file_is_untouched_whitespace_only_or_the_agent_changed_it_last(self):
        self.hook("prompt", {**self.ev, "prompt": "review a services contract for a client"})
        f = self.agent_writes()
        self.assertNotIn("edited", self.context(self.hook("prompt", {**self.ev, "prompt": "go on"})))
        self.assertEqual(len(self.snapshots()), 1)                # untouched: kept for a later request
        f.write_text(REPORT.replace("\n-", "\n  -"))               # spacing only
        self.assertNotIn("edited", self.context(self.hook("prompt", {**self.ev, "prompt": "go on"})))
        self.assertEqual(self.snapshots(), [])
        self.hook("prompt", {**self.ev, "prompt": "review a services contract for a client"})
        self.agent_writes()
        self.agent_writes(text=REPORT + "- New line.\n", tool="Edit", file_path=str(f))   # the agent's own edit
        self.assertNotIn("edited", self.context(self.hook("prompt", {**self.ev, "prompt": "go on"})))

    def test_no_snapshot_without_a_piece_or_for_binary_large_or_capture_off(self):
        self.hook("prompt", {**self.ev, "prompt": "something unrelated entirely"})
        self.agent_writes()
        self.assertEqual(self.snapshots(), [])
        self.hook("prompt", {**self.ev, "prompt": "review a services contract for a client"})
        b = self.work / "scan.pdf"
        b.write_bytes(b"%PDF\0\0binary")
        self.hook("tool", {**self.ev, "tool_name": "Write", "tool_input": {"file_path": str(b)}})
        big = self.agent_writes("big.txt", "x" * (edits.FILE_CAP + 1))
        self.assertEqual(self.snapshots(), [])
        self.hook("tool", {**self.ev, "tool_name": "Write", "tool_input": {"file_path": str(big)}},
                  env={"ATHOS_CAPTURE": "off"})
        self.assertEqual(self.snapshots(), [])

    def test_other_agents_tool_names_and_codex_patches(self):
        self.hook("prompt", {**self.ev, "prompt": "review a services contract for a client"})
        (self.work / "a.md").write_text("one\n")
        (self.work / "b.md").write_text("two\n")
        (self.work / "c.md").write_text("three\n")
        self.hook("tool", {**self.ev, "tool_name": "Write", "tool_input": {"filePath": str(self.work / "a.md")}})  # OpenCode
        self.hook("tool", {**self.ev, "tool_name": "write_file", "tool_input": {"path": "b.md"}})                # Muse Code
        patch = "*** Begin Patch\n*** Update File: c.md\n@@\n-x\n+three\n*** End Patch\n"
        self.hook("tool", {**self.ev, "tool_name": "apply_patch", "tool_input": {"command": patch}})             # Codex
        self.assertEqual(sorted(Path(s["path"]).name for s in self.snapshots()), ["a.md", "b.md", "c.md"])

    def test_only_the_last_tasks_are_kept(self):
        for i in range(edits.KEEP_TASKS + 2):
            self.hook("prompt", {**self.ev, "prompt": "review a services contract for a client"})
            self.agent_writes(f"r{i}.md")
        names = [Path(s["path"]).name for s in self.snapshots()]
        self.assertEqual(names, [f"r{i}.md" for i in range(2, edits.KEEP_TASKS + 2)])
        files = {p.name for p in (Path(self.home) / "snapshots" / "s1").iterdir()}
        self.assertEqual(len(files), edits.KEEP_TASKS + 1)                      # the snapshots and the index

    def test_the_diff_is_capped(self):
        before = "\n".join(f"line {i}" for i in range(200))
        after = "\n".join(f"LINE {i}" for i in range(200))
        lines = edits.diff(before, after, "x.md").splitlines()
        self.assertEqual(len(lines), edits.DIFF_LINES + 1)
        self.assertTrue(lines[-1].startswith("… ("))


class EditsUnitTest(TempHome):
    def test_written_paths_resolve_against_the_event_folder(self):
        ev = {"cwd": "/w", "tool_name": "apply_patch",
              "tool_input": {"command": "*** Begin Patch\n*** Add File: n.md\n+x\n*** Update File: /abs/o.md\n"
                                        "*** Move to: p.md\n*** End Patch"}}
        self.assertEqual([str(p) for p in edits.written_paths(ev)], ["/w/n.md", "/abs/o.md", "/w/p.md"])
        self.assertEqual(edits.written_paths({"tool_name": "Read", "tool_input": {"file_path": "/x"}}), [])
        self.assertEqual(session.load("none"), {})

    def test_keep_this_rule_sends_an_adjust_and_the_button_goes_away(self):
        session.update("s1", task_id="t1", learned_from_edit={"task_id": "t1", "files": [
            {"file": "/w/report.md", "name": "report.md", "piece": "p", "title": "P", "statement": "penalties"},
            {"file": "/w/memo.md", "name": "memo.md", "piece": "p", "title": "P", "statement": None}]})
        from athos import trail
        keeps = [x["keep"] for x in trail.view(session.load("s1"))["edits"]]
        self.assertEqual(keeps, ["Athos · adjust p#penalties: keep the rule you proposed from my edit of report.md",
                                 "Athos · adjust p: keep the rule you proposed from my edit of memo.md"])
        from athos.cli import learned_from_edit
        self.assertEqual([f["adjust_prompt"] for f in learned_from_edit(session.load("s1"))],
                         ["Athos · adjust p#penalties: ", "Athos · adjust p: "])
        edits.kept("s1", keeps[0])                       # what the prompt hook does with an adjust request
        self.assertEqual([x["name"] for x in trail.view(session.load("s1"))["edits"]], ["memo.md"])
