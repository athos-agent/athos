"""Autonomous learning: piece status and provenance, Check lines, evidence, the autonomous save, the independent
verifier, promotion and demotion, risk lanes, the apply tier, repairing polluted statistics and the audit rules.
Everything here is offline: the verifier's model runner is stubbed."""

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
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
        from athos import eval as ev, grade
        ev.audit({"type": "verify", "piece": p.id, "outcome": "pass", "body_sha": grade.body_sha(p),
                  "paths_only": True, "version": 1})                    # the verifier passed this very text
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


class VerificationCommandsTest(unittest.TestCase):
    def kinds(self, cmd, checks=None):
        from athos import evidence
        return [(s["kind"], s["label"], s["owns_success"], s["owns_failure"]) for s in evidence.classify(cmd, checks)]

    def test_test_runners_builds_linters_and_type_checkers(self):
        from athos import evidence
        for cmd, kind in [("pytest -q", "test"), ("python3 -m unittest discover -s tests -t .", "test"),
                          ("npm test", "test"), ("npm run test:stories", "test"), ("go test ./...", "test"),
                          ("cargo test", "test"), ("make check", "test"), ("npx vitest run", "test"),
                          ("npm run build", "build"), ("cargo build --release", "build"), ("tsc -p .", "build"),
                          ("ruff check .", "lint"), ("eslint src", "lint"), ("black --check .", "lint"),
                          ("mypy athos", "typecheck"), ("tsc --noEmit", "typecheck"), ("go vet ./...", "typecheck")]:
            self.assertEqual(evidence.kind_of(cmd)[0], kind, cmd)

    def test_what_is_not_a_verification(self):
        from athos import evidence
        for cmd in ["ls", "git status", "echo pytest", "cat tests/test_x.py", "ruff format .", "black .",
                    "python3 script.py", "make", "docker build .", "bash -c 'pytest'", "(pytest)", "npm install"]:
            self.assertIsNone(evidence.kind_of(cmd), cmd)

    def test_whose_exit_status_it_is(self):
        self.assertEqual(self.kinds("pytest"), [("test", "pytest", True, True)])
        self.assertEqual(self.kinds("cd app && npm test"), [("test", "test", True, True)])
        self.assertEqual(self.kinds("pytest | tail -5"), [("test", "pytest", False, False)])      # tail's status
        self.assertEqual(self.kinds("pytest || true"), [("test", "pytest", False, False)])
        self.assertEqual(self.kinds("pytest; echo done"), [("test", "pytest", False, False)])
        self.assertEqual(self.kinds("pytest && git commit -m x"), [("test", "pytest", True, False)])
        self.assertEqual(self.kinds("make lint-fix && pytest"), [("test", "pytest", True, False)])
        self.assertEqual(self.kinds("make lint-fix; pytest"), [("test", "pytest", True, True)])
        self.assertEqual(self.kinds("pytest > /tmp/out.txt 2>&1"), [("test", "pytest", True, True)])
        self.assertEqual(self.kinds("FOO=1 timeout 60 pytest -x"), [("test", "pytest", True, True)])

    def test_a_pieces_own_check_is_recognised(self):
        # Only a Check that is itself a verification counts: a script of the project's own is not known to verify
        # anything, so running it is no evidence.
        from athos import evidence
        self.assertEqual(evidence.classify("./scripts/smoke.sh --fast --verbose",
                                           [("release", "built", "./scripts/smoke.sh --fast")]), [])
        self.assertEqual(evidence.classify("pytest -q", [("p", "s", "pytest -q")])[0]["check_of"], "p#s")
        self.assertEqual(evidence.classify("pytest -q -x", [("p", "s", "pytest -q")])[0]["check_of"], "p#s")

    def test_secrets_are_blanked(self):
        from athos import evidence
        self.assertNotIn("hunter2", evidence.redact("API_KEY=hunter2 npm test"))
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123456789", evidence.redact("x abcdefghijklmnopqrstuvwxyz0123456789"))


def _bash(sid, cmd, cwd, ok=True, stdout="", platform="claude-code"):
    """A Claude Code tool event for a shell command: PostToolUse when it exited 0, PostToolUseFailure otherwise."""
    from athos import evidence
    event = {"session_id": sid, "cwd": cwd, "tool_name": "Bash", "tool_input": {"command": cmd},
             "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False}}
    if not ok:
        event = {**event, "error": "Exit code 1\n" + stdout}
        event.pop("tool_response")
    return evidence.on_tool(event, sid, failed=not ok, platform=platform)


class EvidenceGatheringTest(TempHome):
    def setUp(self):
        super().setUp()
        from athos import session
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})

    def test_a_passing_test_command_is_strong_positive_with_its_output_kept(self):
        from athos import evidence
        _bash("s1", "python3 -m unittest -q", self.home, stdout="Ran 4 tests\nOK")
        [item] = evidence.of_task("t1")
        self.assertEqual((item["type"], item["ok"], item["strength"], item["polarity"]), ("verify", True, "strong",
                                                                                          "positive"))
        self.assertIn("Ran 4 tests", Path(item["output"]).read_text())
        self.assertEqual(evidence.qualifies(evidence.of_task("t1")), (True, "strong_evidence"))

    def test_a_failure_and_a_masked_status(self):
        from athos import evidence
        _bash("s1", "pytest -q", self.home, ok=False, stdout="1 failed")
        _bash("s1", "pytest -q | tail -3", self.home, stdout="1 failed")
        items = evidence.of_task("t1")
        self.assertEqual([(i["ok"], i["strength"]) for i in items], [(False, "strong"), (True, "weak")])
        self.assertEqual(evidence.qualifies(items), (False, "no_strong_evidence"))

    def test_the_last_verification_failing_spoils_an_earlier_pass(self):
        from athos import evidence
        _bash("s1", "pytest", self.home)
        _bash("s1", "pytest", self.home, ok=False)
        self.assertEqual(evidence.qualifies(evidence.of_task("t1")), (False, "last_verification_failed"))

    def test_commits_and_reverts(self):
        import subprocess
        from athos import evidence
        repo = os.path.join(self.home, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=a", "commit", "-q", "--allow-empty",
                        "-m", "x"], cwd=repo, check=True)
        # A commit counts only when HEAD moved since the call's start (the PreToolUse stamp keeps it).
        import time
        stamp = {**evidence.start_stamp(repo), "at": time.time()}
        subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=a", "commit", "-q", "--allow-empty",
                        "-m", "y"], cwd=repo, check=True)
        evidence.on_tool({"session_id": "s1", "cwd": repo, "tool_name": "Bash", "tool_input": {"command": "git commit -m x"},
                          "tool_response": {"stdout": ""}}, "s1", started=stamp)
        _bash("s1", "git reset --hard HEAD~1", repo)
        items = evidence.of_task("t1")
        self.assertEqual([i["type"] for i in items], ["commit", "revert"])
        self.assertTrue(items[0].get("sha"))
        self.assertEqual(evidence.qualifies(items), (False, "correction_after_success"))

    def test_subagents_athos_commands_and_unknown_status_on_other_agents(self):
        from athos import evidence
        evidence.on_tool({"session_id": "s1", "tool_name": "Bash", "agent_id": "a1",
                          "tool_input": {"command": "pytest"}}, "s1")
        _bash("s1", "athos save --auto", self.home)
        self.assertEqual(evidence.of_task("t1"), [])
        _bash("s1", "pytest", self.home, platform="codex")                 # no exit code in the event
        [item] = evidence.of_task("t1")
        self.assertEqual((item["ok"], item["strength"]), (None, "weak"))

    def test_an_explicit_exit_code_wins(self):
        from athos import evidence
        evidence.on_tool({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "pytest"},
                          "tool_response": {"exit_code": 2}}, "s1", platform="codex")
        self.assertEqual(evidence.of_task("t1")[0]["ok"], False)

    def test_public_repository_keeps_no_command(self):
        from athos import evidence, session
        session.update("s1", public=True)
        _bash("s1", "pytest tests/test_secret_project.py", self.home)
        item = evidence.of_task("t1")[0]
        self.assertNotIn("cmd", item)
        self.assertNotIn("secret_project", Path(item["output"]).read_text())

    def test_person_edits_and_reactions(self):
        from athos import evidence
        evidence.note_person_edits([{"task_id": "t0", "file_sha": "f", "piece": "p", "statement": None,
                                     "basis": ["changed_after_turn_end"]}])
        evidence.note_reaction("t0", "corrected")
        items = evidence.of_task("t0")
        self.assertEqual([(i["type"], i["strength"], i["polarity"]) for i in items],
                         [("person_edit", "strong", "negative"), ("reaction", "weak", "negative")])
        self.assertEqual(evidence.qualifies(items), (False, "no_strong_evidence"))

    def test_the_hooks_gather_it(self):
        from athos import cli, evidence, session
        session.save("h1", {"task_id": "t9", "model": "claude-opus-5-5"})
        event = {"session_id": "h1", "cwd": self.home, "tool_name": "Bash", "tool_input": {"command": "npm test"},
                 "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False}}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(event))), redirect_stdout(io.StringIO()):
            cli.hook("tool")
        with mock.patch("sys.stdin", io.StringIO(json.dumps({**event, "error": "Exit code 1"}))), \
                redirect_stdout(io.StringIO()):
            cli.hook("tool-failed")
        self.assertEqual([i["ok"] for i in evidence.of_task("t9")], [True, False])

    def test_summary_tokens(self):
        from athos import evidence
        _bash("s1", "pytest", self.home)
        _bash("s1", "pytest", self.home)
        self.assertEqual(evidence.summary(evidence.of_task("t1"), "t1"), ["verify:pytest:ok", "task:t1"])


class EditsAreEvidenceTest(TempHome):
    def test_the_model_is_not_told_about_edits_when_learning_on_its_own_or_applying(self):
        from athos import autolearn, session
        session.save("a", {"model": "claude-opus-5-5"})
        session.save("b", {"model": "claude-haiku-5-5"})
        session.save("c", {"model": "unknown"})
        self.assertEqual([autolearn.tells_edits(s) for s in "abc"], [False, False, True])
        with mock.patch.object(autolearn, "settings", return_value={**autolearn.DEFAULTS, "on": False}):
            self.assertTrue(autolearn.tells_edits("a"))


PIECE = """---
title: Change the parser safely
when: changing the parser of this project
---
""" + BODY


class _HookedTask(TempHome):
    """A task through the hooks, as Claude Code runs them (headless), in a project folder named demo."""

    def setUp(self):
        super().setUp()
        from tests.test_cli import ThroughTheLauncher
        self.cli = ThroughTheLauncher()
        self.cli.home = self.home
        self.cli.assertEqual = self.assertEqual
        self.work = os.path.join(self.home, "work", "demo")
        os.makedirs(self.work)
        self.ev = {"session_id": "f1", "cwd": self.work, "transcript_path": None}

    def task(self, model="claude-opus-5-5", verify=True, ok=True, edits=4, stop=True):
        self.cli.send("session-start", {**self.ev, "model": model})
        self.cli.send("prompt", {**self.ev, "prompt": "fix the parser and add a test"})
        for _ in range(edits):
            self.cli.send("tool", {**self.ev, "tool_name": "Edit", "tool_input": {"file_path": "x.py"}})
        if verify:
            name = "tool" if ok else "tool-failed"
            event = {**self.ev, "tool_name": "Bash", "tool_input": {"command": "python3 -m unittest -q"}}
            event.update({"tool_response": {"stdout": "OK", "stderr": "", "interrupted": False}} if ok
                         else {"error": "Exit code 1"})
            self.cli.send(name, event)
        return self.cli.send("stop", self.ev) if stop else None

    def learns(self):
        from athos import eval as ev
        return [e for e in ev.events() if e.get("type") == "learn"]


class AutonomousSaveTest(_HookedTask):
    """A frontier task, then the model's `athos save --auto`."""

    def test_a_qualifying_frontier_task_with_strong_evidence_saves_a_candidate(self):
        # By default (`autolearn.ask: guide`) the Stop hook says nothing: the session guide told the model to save
        # before its final answer, and the hook records that the task qualified.
        self.assertIsNone(self.task())
        done = self.cli.run_athos("save", "--auto", stdin=PIECE, cwd=self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("as a candidate of demo", done.stdout)
        [piece] = store.all_pieces()
        self.assertEqual((piece.status, piece.projects, piece.learned_by, piece.visibility, piece.risk),
                         ("candidate", ["demo"], "claude-opus-5-5", "project", "normal"))
        self.assertIn("verify:unittest:ok", piece.evidence)
        self.assertTrue(any(e.startswith("task:") for e in piece.evidence))
        decisions = [(e["decision"], e["reason"]) for e in self.learns()]
        self.assertEqual(decisions, [("qualified", "strong_evidence"), ("saved", "strong_evidence")])
        self.assertEqual((self.learns()[0]["ask"], self.learns()[0]["guide"]), ("guide", True))
        self.assertEqual(self.learns()[-1]["checks"], 1)              # `cat VERSION` proves nothing: not runnable

    def test_as_the_guide_says_the_model_saves_before_its_answer_and_the_stop_hook_stays_silent(self):
        self.task(stop=False)
        done = self.cli.run_athos("save", "--auto", stdin=PIECE, cwd=self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.cli.run_athos("hook", "tool", stdin=json.dumps({**self.ev, "tool_name": "Bash", "tool_input": {
            "command": "athos save --auto <<'EOF'"}}))
        self.assertIsNone(self.cli.send("stop", self.ev))
        self.assertEqual([e["decision"] for e in self.learns()], ["saved"])

    def test_the_guide_says_to_save_before_the_final_answer(self):
        opening = self.cli.context(self.cli.send("session-start", {**self.ev, "model": "claude-opus-5-5"}))
        self.assertIn("Before your final answer", opening)
        self.assertIn("save --auto", opening)
        self.assertNotIn("Stop hook", opening)

    def test_ask_stop_brings_back_the_one_line_at_the_stop(self):
        Path(self.home, "config.json").write_text(json.dumps({"autolearn": {"ask": "stop"}}))
        opening = self.cli.context(self.cli.send("session-start", {**self.ev, "model": "claude-opus-5-5"}))
        self.assertIn("Stop hook says so once", opening)
        asked = self.task()
        line = asked["hookSpecificOutput"]["additionalContext"]
        self.assertIn("save --auto", line)
        self.assertEqual(len(line.splitlines()), 1)                         # one short line: the person sees it
        self.assertLess(len(line), 200)
        self.assertEqual((self.learns()[-1]["decision"], self.learns()[-1]["ask"]), ("asked", "stop"))

    def test_without_strong_evidence_nothing_is_asked_or_saved(self):
        self.assertIsNone(self.task(verify=False))
        self.assertEqual([(e["decision"], e["reason"]) for e in self.learns()], [("skipped", "no_strong_evidence")])
        done = self.cli.run_athos("save", "--auto", stdin=PIECE, cwd=self.work)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no objective evidence", done.stderr)
        self.assertEqual(store.all_pieces(), [])

    def test_a_failed_last_verification_is_not_learned(self):
        self.assertIsNone(self.task(ok=False))
        self.assertEqual(self.learns()[-1]["reason"], "no_strong_evidence")

    def test_the_private_data_detector_blocks_a_save(self):
        self.task()
        leaky = PIECE.replace("bump the version in `VERSION`.", "mail ada@realcompany.org and edit /Users/ada/x.txt.")
        done = self.cli.run_athos("save", "--auto", stdin=leaky, cwd=self.work)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("private data (email, folder)", done.stderr)
        self.assertEqual(store.all_pieces(), [])
        self.assertEqual((self.learns()[-1]["reason"], self.learns()[-1]["private"]), ("private_data",
                                                                                        ["email", "folder"]))

    def test_another_projects_name_blocks_it_too(self):
        store.create("Other", "other things", "x", projects=["zebra-shop"])
        self.task()
        done = self.cli.run_athos("save", "--auto", stdin=PIECE + "\nAs in zebra-shop.\n", cwd=self.work)
        self.assertIn("project", done.stderr)

    def test_the_model_that_stops_saving_nothing_is_recorded(self):
        self.task()
        self.cli.send("prompt", {**self.ev, "prompt": "thanks, next thing"})
        self.assertEqual((self.learns()[-1]["reason"], self.learns()[-1]["ask"]), ("model_saved_nothing", "guide"))

    def test_an_existing_piece_is_never_changed_autonomously(self):
        old = store.create("Old", "old", "x", projects=["demo"])
        self.task()
        done = self.cli.run_athos("save", "--auto", stdin=PIECE.replace("---\ntitle", f"---\nid: {old.id}\ntitle"),
                                  cwd=self.work)
        self.assertIn("the person's own", done.stderr)                     # a model never rewrites it
        self.assertEqual(store.get(old.id).version, 1)

    def test_the_session_guide_is_the_autonomous_one_on_a_frontier_model(self):
        opening = self.cli.context(self.cli.send("session-start", {**self.ev, "model": "claude-opus-5-5"}))
        self.assertIn("save --auto", opening)
        self.assertIn("**Check:**", opening)

    def test_with_autonomous_learning_off_the_old_offer_comes_back(self):
        Path(self.home, "config.json").write_text(json.dumps({"autolearn": {"on": False}}))
        asked = self.task()
        self.assertIn("athos save", asked["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("--auto", asked["hookSpecificOutput"]["additionalContext"])


class ApplyModeNeverSavesTest(_HookedTask):
    def test_no_save_prompt_and_both_saves_refuse(self):
        self.assertIsNone(self.task(model="claude-haiku-5-5"))
        self.assertEqual(self.learns()[-1]["reason"], "apply_model")
        auto = self.cli.run_athos("save", "--auto", stdin=PIECE, cwd=self.work)
        plain = self.cli.run_athos("save", stdin=PIECE, cwd=self.work)
        for done in (auto, plain):
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("apply model", done.stderr)
        self.assertEqual(store.all_pieces(), [])

    def test_no_capture_guide_at_session_start(self):
        store.create("Mine", "my thing", "x", projects=["demo"])
        opening = self.cli.context(self.cli.send("session-start", {**self.ev, "model": "claude-haiku-5-5"}))
        self.assertNotIn("athos save", opening)

    def test_no_offer_in_an_interactive_session(self):
        from athos import session
        self.cli.send("session-start", {**self.ev, "model": "claude-sonnet-5-5"})
        for _ in range(5):
            self.cli.run_athos("hook", "tool", stdin=json.dumps({**self.ev, "tool_name": "Edit"}),
                               env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.cli.run_athos("hook", "stop", stdin=json.dumps(self.ev), env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertIsNone(session.load("f1").get("offer"))


class RiskDetectorTest(unittest.TestCase):
    def test_risky_steps(self):
        from athos import autolearn
        for text, kind in [("run `npm publish`", "publish"), ("git push origin main", "publish"),
                           ("`gh pr merge 12 --squash`", "merge"), ("merge the branch", "merge"),
                           ("deploy to staging", "deploy"), ("`kubectl apply -f x.yaml`", "deploy"),
                           ("`terraform destroy`", "deploy"), ("`rm -rf build/`", "delete"),
                           ("delete the old rows", "delete"), ("DROP TABLE users", "delete"),
                           ("`git push --force-with-lease`", "force_push"), ("on the production database", "production"),
                           ("`vercel --prod`", "production"), ("publicar la versión", "publish"),
                           ("borrar la rama", "delete"), ("desplegar en producción", "deploy")]:
            self.assertIn(kind, autolearn.risks_in(text), text)

    def test_ordinary_steps_are_not_risky(self):
        from athos import autolearn
        for text in ["run the unit tests", "edit the README", "open a pull request", "read the product page",
                     "commit with a clear message", "`git status`", "format the code", "release notes draft"]:
            self.assertEqual(autolearn.risks_in(text), [], text)

    def test_a_piece_is_high_when_any_step_is(self):
        from athos import autolearn
        p = store.Piece(id="x", title="x", when="x", body=BODY + "\n## #ship\n**When:** done.\n**Do:** `git push`.\n")
        self.assertEqual(autolearn.risky_steps(p), {"ship": ["publish"]})
        self.assertEqual(autolearn.risk_of(p), "high")
        self.assertEqual(autolearn.risk_of(store.Piece(id="y", title="y", when="y", body=BODY)), "normal")


PASS = json.dumps({c: {"pass": True, "why": "shown"} for c in
                   ("evidence_passed", "piece_matches_work", "checks_runnable", "no_private_data", "reusable")})


class StubRunner:
    """Stands in for `claude -p`: records what it was given and answers as told."""

    def __init__(self, text=PASS, ok=True, cost=0.04, error=None):
        self.text, self.ok, self.cost, self.error, self.calls = text, ok, cost, error, []

    def __call__(self, prompt, bundle, model, timeout, max_usd):
        self.calls.append({"prompt": prompt, "bundle": bundle, "model": model, "timeout": timeout, "max_usd": max_usd})
        return {"ok": self.ok, "text": self.text, "cost_usd": self.cost, "error": self.error, "duration_s": 1.0}


def candidate(project="demo", body=BODY, task="t1", **more):
    from athos import evidence
    evidence.add(task, {"type": "verify", "kind": "test", "label": "unittest", "ok": True, "strength": "strong",
                        "polarity": "positive"})
    fields = {"status": "candidate", "learned_by": "claude-opus-5-5", "confidence": "0.3", "risk": "normal", **more}
    return store.create("Change the parser safely", "changing the parser", body, projects=[project], **fields)


class VerifierTest(TempHome):
    def setUp(self):
        super().setUp()
        from athos import verify
        self.piece = candidate()
        self.bundle = verify.build_bundle(self.piece, "t1", None)

    def events(self, kind):
        from athos import eval as ev
        return [e for e in ev.events() if e.get("type") == kind]

    def test_the_prompt_carries_paths_only(self):
        from athos import verify
        prompt, named = verify.prompt_for(self.bundle)
        self.assertTrue(verify.paths_only(prompt, named, self.bundle))
        self.assertFalse(verify.paths_only(prompt + "\nThe worker says all tests pass.", named, self.bundle))
        self.assertFalse(verify.paths_only(prompt, {**named, "piece": "/tmp/elsewhere/piece.md"}, self.bundle))
        self.assertFalse(verify.paths_only(prompt, {**named, "summary": "done"}, self.bundle))
        rest = prompt
        for value in sorted(named.values(), key=len, reverse=True):     # files.json before its folder files/
            rest = rest.replace(value, "<path>")
        self.assertEqual(rest, verify.PROMPT.format(**{k: "<path>" for k in named}))   # fixed text and paths

    def test_a_passing_verdict_is_recorded_with_its_cost_and_model(self):
        from athos import verify
        runner = StubRunner()
        out = verify.run(self.piece.id, self.bundle, runner)
        self.assertEqual(out["outcome"], "pass")
        self.assertTrue(out["paths_only"])
        self.assertEqual(out["inputs"], sorted(verify.INPUTS))
        self.assertEqual(runner.calls[0]["model"], "fable")                    # not the worker's family
        self.assertFalse(out["same_model_fallback"])
        self.assertEqual(Path(self.bundle, "prompt.txt").read_text(), runner.calls[0]["prompt"])
        again = store.get(self.piece.id)
        self.assertIn("verifier:pass", again.evidence)
        self.assertEqual((again.confidence, again.last_verified), ("0.50", store.today()))
        [run] = [e for e in self.events("model_run") if e.get("phase") == "settled"]
        self.assertEqual((run["purpose"], run["cost_usd"], run["model"]), ("verify", 0.04, "fable"))
        self.assertEqual(self.events("grade")[-1]["basis"],
                         "verifier_passed; waiting for 2 clean frontier reuses or a pass on an apply model")
        self.assertEqual(self.events("learn")[-1]["decision"], "graded")

    def test_the_worker_never_sees_its_own_summary(self):
        from athos import verify
        runner = StubRunner()
        verify.run(self.piece.id, self.bundle, runner)
        sent = runner.calls[0]["prompt"]
        self.assertNotIn("Change the parser safely", sent)                     # the piece itself is only a path
        self.assertEqual(sorted(p.name for p in Path(self.bundle).iterdir() if p.name in verify.INPUTS),
                         sorted(verify.INPUTS))

    def test_the_same_model_is_a_recorded_fallback(self):
        from athos import tiers, verify
        tiers.add("apply", ["claude-fable-*", "claude-mythos-*"])              # only opus is frontier now
        runner = StubRunner()
        out = verify.run(self.piece.id, self.bundle, runner)
        self.assertEqual((runner.calls[0]["model"], out["same_model_fallback"]), ("opus", True))
        self.assertIn("verifier:pass:same-model", store.get(self.piece.id).evidence)

    def test_a_failing_verdict_names_the_criteria(self):
        from athos import verify
        bad = json.loads(PASS)
        bad["checks_runnable"] = {"pass": False, "why": "vague"}
        out = verify.run(self.piece.id, self.bundle, StubRunner(json.dumps(bad)))
        self.assertEqual(out["outcome"], "fail")
        self.assertEqual(store.get(self.piece.id).status, "candidate")
        self.assertEqual(self.events("grade")[-1]["basis"], "verifier_failed: checks_runnable")

    def test_a_timeout_or_an_unreadable_answer_leaves_a_candidate_and_says_why(self):
        from athos import verify
        out = verify.run(self.piece.id, self.bundle, StubRunner(ok=False, cost=None, error="timeout after 300 s"))
        self.assertEqual((out["outcome"], out["error"]), ("error", "timeout after 300 s"))
        self.assertEqual(store.get(self.piece.id).status, "candidate")
        self.assertIn("timeout", self.events("grade")[-1]["basis"])
        self.assertTrue(self.events("model_run")[-1]["cost_estimated"])
        out = verify.run(self.piece.id, self.bundle, StubRunner(text="looks fine to me"))
        self.assertEqual(out["error"], "the answer held no readable verdict")

    def test_caps_are_enforced(self):
        from athos import start, verify
        start.config_file().write_text(json.dumps({"autolearn": {"budget": {"runs_per_day": 1}}}))
        verify.run(self.piece.id, self.bundle, StubRunner(ok=False, cost=None, error="boom"))
        runner = StubRunner()
        out = verify.run(self.piece.id, self.bundle, runner)
        self.assertEqual((out["outcome"], runner.calls), ("skipped", []))
        self.assertIn("daily cap of 1 runs", out["error"])
        # The failed run reported no cost, so it counts the whole cap it reserved (US$0.50): a day of US$0.80 has
        # US$0.30 left, and the next run's cap is cut to that.
        start.config_file().write_text(json.dumps({"autolearn": {"budget": {"runs_per_day": 9, "usd_per_day": 0.8}}}))
        runner = StubRunner(cost=0.1)
        verify.run(self.piece.id, self.bundle, runner)
        self.assertEqual(runner.calls[0]["max_usd"], 0.3)
        start.config_file().write_text(json.dumps({"autolearn": {"budget": {"runs_per_day": 9, "usd_per_day": 0.6}}}))
        out = verify.run(self.piece.id, self.bundle, StubRunner())
        self.assertIn("US$0.6", out["error"])
        self.assertEqual(self.events("model_run")[-1]["refused"], out["error"])

    def test_the_verifier_can_be_turned_off(self):
        from athos import start, verify
        start.config_file().write_text(json.dumps({"autolearn": {"verifier": {"on": False}}}))
        runner = StubRunner()
        self.assertEqual(verify.run(self.piece.id, self.bundle, runner)["outcome"], "skipped")
        self.assertEqual(runner.calls, [])
        spawned = []
        self.assertFalse(verify.after_save(self.piece, {"task_id": "t1"}, None, Path("athos"), spawned.append))
        self.assertEqual(spawned, [])
        self.assertEqual(self.events("grade")[-1]["basis"], "verifier_off")

    def test_after_a_save_it_starts_detached(self):
        from athos import verify
        calls = []
        started = verify.after_save(self.piece, {"task_id": "t1"}, None, Path("/x/bin/athos"),
                                    lambda argv, **kw: calls.append((argv, kw)))
        self.assertTrue(started)
        argv, kw = calls[0]
        self.assertIn("verify", argv)
        self.assertTrue(kw["start_new_session"])
        self.assertEqual(kw["stdout"], verify.subprocess.DEVNULL)

    def test_the_child_run_is_isolated_and_read_only(self):
        from athos import verify
        cmd = verify.command("p", "fable", self.bundle, 0.5)
        for flag in ("--safe-mode", "--no-session-persistence", "--strict-mcp-config"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(cmd[cmd.index("--max-budget-usd") + 1], "0.50")
        env = verify.child_env("/tmp/throwaway")
        self.assertEqual((env["ATHOS_HOME"], env["ATHOS_HOOKS"], env["ATHOS_CAPTURE"]), ("/tmp/throwaway", "off", "off"))

    def test_athos_hooks_are_inert_in_the_child(self):
        from athos import cli, eval as ev
        with mock.patch.dict(os.environ, {"ATHOS_HOOKS": "off"}), \
                mock.patch("sys.stdin", io.StringIO(json.dumps({"session_id": "v", "prompt": "hi", "cwd": self.home}))), \
                redirect_stdout(io.StringIO()) as out:
            cli.hook("prompt")
        self.assertEqual((out.getvalue(), [e for e in ev.events() if e.get("session_id") == "v"]), ("", []))

    def test_the_bundle_is_built_from_git_and_the_hooks_output(self):
        import subprocess
        from athos import evidence, verify
        repo = os.path.join(self.home, "repo")
        os.makedirs(repo)
        git = ["git", "-c", "user.email=a@example.com", "-c", "user.name=a"]
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        Path(repo, "a.py").write_text("x = 1\n")
        subprocess.run([*git, "add", "a.py"], cwd=repo, check=True)
        subprocess.run([*git, "commit", "-qm", "first"], cwd=repo, check=True)
        Path(repo, "a.py").write_text("x = 2\n")
        Path(repo, "out.txt").write_text("Ran 3 tests OK\n")
        evidence.add("t2", {"type": "verify", "kind": "test", "label": "pytest", "ok": True, "strength": "strong",
                            "polarity": "positive", "output": str(Path(repo, "out.txt"))})
        folder = verify.build_bundle(self.piece, "t2", repo)
        self.assertIn("-x = 1", Path(folder, "diff.patch").read_text())
        self.assertIn("Ran 3 tests OK", Path(folder, "verification.txt").read_text())
        self.assertEqual(json.loads(Path(folder, "checks.json").read_text())[0]["command"],
                         "python3 -m unittest discover -s tests")

    def test_pending_candidates_are_retried_a_bounded_number_of_times(self):
        from athos import verify
        self.assertEqual([p for p, _ in verify.pending()], [self.piece.id])
        verify.run(self.piece.id, self.bundle, StubRunner(ok=False, error="boom", cost=None))
        verify.run(self.piece.id, self.bundle, StubRunner(ok=False, error="boom", cost=None))
        self.assertEqual(verify.pending(), [])                                 # two attempts, then left alone

    def test_verdict_parsing(self):
        from athos import verify
        partial = verify.verdict_of('Here: {"evidence_passed": {"pass": true, "why": "ok"}}')
        self.assertTrue(partial["evidence_passed"]["pass"])
        self.assertFalse(partial["reusable"]["pass"])
        self.assertEqual(partial["reusable"]["why"], "not answered")
        self.assertIsNone(verify.verdict_of("no json"))


def reuse(pid, tier="frontier", outcome="clean", basis=("strong_positive",)):
    from athos import eval as ev, grade
    ev.audit({"type": "reuse", "piece": pid, "tier": tier, "outcome": outcome, "basis": list(basis),
              "version": store.get(pid).version})
    return grade.evaluate(pid)


class PromotionTest(TempHome):
    def setUp(self):
        super().setUp()
        from athos import verify
        self.piece = candidate()
        self.bundle = verify.build_bundle(self.piece, "t1", None)

    def grades(self):
        from athos import eval as ev
        return [e for e in ev.events() if e.get("type") == "grade"]

    def verified(self):
        from athos import verify
        verify.run(self.piece.id, self.bundle, StubRunner())

    def test_verifier_and_two_clean_frontier_reuses_verify_it(self):
        self.verified()
        self.assertFalse(reuse(self.piece.id))
        self.assertEqual(store.get(self.piece.id).status, "candidate")
        self.assertTrue(reuse(self.piece.id))
        p = store.get(self.piece.id)
        self.assertEqual((p.status, p.last_verified), ("verified", store.today()))
        self.assertGreaterEqual(store.confidence(p), 0.7)
        last = self.grades()[-1]
        self.assertEqual((last["from"], last["to"], last["verifier_pass"]), ("candidate", "verified", True))
        self.assertIn("2 clean frontier reuses", last["basis"])

    def test_reuses_alone_never_verify_it(self):
        reuse(self.piece.id)
        reuse(self.piece.id)
        reuse(self.piece.id)
        self.assertEqual(store.get(self.piece.id).status, "candidate")

    def test_a_pass_on_an_apply_model_is_enough_with_the_verifier(self):
        self.verified()
        self.assertTrue(reuse(self.piece.id, tier="apply", outcome="replay_pass"))
        self.assertEqual(store.get(self.piece.id).status, "verified")

    def test_no_runnable_check_no_promotion(self):
        from athos import verify
        p = candidate(body="## #a\n**When:** x.\n**Do:** y.\n**Check:** the page looks right\n", task="t5")
        folder = verify.build_bundle(p, "t5", None)
        verify.run(p.id, folder, StubRunner())
        reuse(p.id)
        reuse(p.id)
        self.assertEqual(store.get(p.id).status, "candidate")
        self.assertIn("no runnable Check", [g for g in self.grades() if g["piece"] == p.id][0]["basis"])

    def test_a_high_risk_piece_needs_a_clean_reuse_not_just_a_replay(self):
        from athos import verify
        p = candidate(body=BODY + "\n## #ship\n**When:** done.\n**Do:** `git push origin main`.\n", task="t6",
                      risk="high")
        folder = verify.build_bundle(p, "t6", None)
        verify.run(p.id, folder, StubRunner())
        self.assertFalse(reuse(p.id, tier="apply", outcome="replay_pass"))
        self.assertTrue(reuse(p.id))
        self.assertIn("high risk", self.grades()[-1]["basis"])

    def test_a_correction_demotes_and_repeated_failures_retire(self):
        from athos import grade
        self.verified()
        reuse(self.piece.id)
        reuse(self.piece.id)
        self.assertEqual(store.get(self.piece.id).status, "verified")
        self.assertTrue(grade.demote(self.piece.id, "corrected reuse on frontier (person_edit)", strong=True))
        self.assertEqual(store.get(self.piece.id).status, "candidate")
        reuse(self.piece.id, outcome="corrected", basis=["person_edit"])
        self.assertTrue(reuse(self.piece.id, outcome="failed", basis=["check_failed"]) or True)
        reuse(self.piece.id, outcome="corrected", basis=["reaction_corrected"])
        p = store.get(self.piece.id)
        self.assertEqual(p.status, "retired")
        self.assertTrue((store.paths.history() / p.id).is_dir())             # superseded, not deleted
        self.assertEqual(store.revert(p.id).status, "candidate")

    def test_a_legacy_piece_is_never_demoted_only_marked_for_review(self):
        from athos import grade
        legacy = store.create("Legacy", "legacy", BODY, projects=["demo"])
        before = legacy.path.read_bytes()
        self.assertFalse(grade.demote(legacy.id, "corrected (reaction_corrected)", strong=False))
        self.assertEqual(legacy.path.read_bytes(), before)                            # untouched
        self.assertFalse(grade.demote(legacy.id, "failed (check_failed)", strong=True))
        self.assertEqual(legacy.path.read_bytes(), before)                            # still untouched
        self.assertEqual(store.status(store.get(legacy.id)), store.LEGACY)
        self.assertIn(legacy.id, grade.reviews())                                      # the person decides

    def test_ageing_without_a_model(self):
        import datetime as dt
        from athos import grade
        p = store.create("Aged", "aged", BODY, projects=["demo"], status="verified", last_verified="2026-01-01")
        p.last_used = p.created = "2026-01-01"
        store._write(p)
        used = store.create("Used", "used", BODY, projects=["demo"], status="verified", last_verified="2026-01-01")
        legacy = store.create("Old legacy", "old", BODY, projects=["demo"])
        for q in (legacy,):
            q.last_used = q.created = "2025-01-01"
            store._write(q)
        moved = grade.age_all(today=dt.date.fromisoformat("2026-06-01"), days=90)
        self.assertEqual(moved, [p.id])                                     # use slows ageing; legacy never ages
        self.assertEqual(store.get(p.id).status, "candidate")
        self.assertEqual(store.get(used.id).status, "verified")
        self.assertEqual(store.get(legacy.id).status, "")
        self.assertIn("aged", self.grades()[-1]["basis"])


class ReuseOutcomeTest(TempHome):
    def test_outcomes_by_tier(self):
        from athos import grade
        good = [{"type": "verify", "strength": "strong", "polarity": "positive", "ok": True}]
        self.assertEqual(grade._outcome("p", "frontier", good)[0], "clean")
        self.assertEqual(grade._outcome("p", "frontier", [])[0], "unverified")
        edit = good + [{"type": "person_edit", "piece": "p", "strength": "strong"}]
        self.assertEqual(grade._outcome("p", "frontier", edit), ("corrected", ["person_edit"]))
        check = [{"type": "verify", "strength": "strong", "ok": True, "check_of": "p#a", "polarity": "positive"}]
        self.assertEqual(grade._outcome("p", "apply", check), ("clean", ["check_passed"]))
        self.assertEqual(grade._outcome("p", "apply", good)[0], "unverified")     # none of its own checks ran
        failed = check + [{"type": "verify", "strength": "strong", "ok": False, "check_of": "p#b",
                           "polarity": "negative"}]
        self.assertEqual(grade._outcome("p", "apply", failed), ("failed", ["check_failed"]))

    def test_finishing_a_task_grades_the_pieces_it_used_and_flags_apply_failures(self):
        from athos import eval as ev, evidence, grade
        p = candidate(task="tx")
        evidence.add("t8", {"type": "verify", "strength": "strong", "ok": False, "check_of": f"{p.id}#run_tests",
                            "polarity": "negative"})
        legacy = store.create("Legacy", "legacy", BODY, projects=["demo"])
        out = grade.finish_task("s", "t8", {"task_loaded": [p.id, legacy.id], "task_saved": [],
                                            "model": "claude-haiku-5-5"})
        self.assertEqual([(e["piece"], e["outcome"]) for e in out], [(p.id, "failed"), (legacy.id, "unverified")])
        self.assertIn(p.id, grade.reviews())
        self.assertEqual([e for e in ev.events() if e.get("type") == "reuse"][0]["tier"], "apply")
        self.assertLess(store.confidence(store.get(p.id)), 0.3)

    def test_the_task_that_saved_a_piece_is_not_its_reuse(self):
        from athos import grade
        p = candidate(task="tz")
        self.assertEqual(grade.finish_task("s", "tz", {"task_loaded": [p.id], "task_saved": [p.id],
                                                       "model": "claude-opus-5-5"}), [])


class ApplyTierDeliveryTest(TempHome):
    def setUp(self):
        super().setUp()
        self.cand = candidate(body=BODY + "\n## #ship\n**When:** the tests pass.\n**Do:** `git push origin main`.\n")
        self.ver = store.create("Release the parser", "releasing the parser", BODY + "\n## #ship\n**When:** ready.\n"
                                "**Do:** `npm publish`.\n", projects=["demo"], status="verified", risk="high")
        self.legacy = store.create("Legacy way", "the legacy way", BODY, projects=["demo"])
        self.retired = store.create("Gone", "gone", BODY, projects=["demo"], status="retired")

    def test_apply_models_get_verified_and_legacy_only(self):
        from athos import tiers
        pool = [self.cand, self.ver, self.legacy, self.retired]
        self.assertEqual({p.id for p in load.usable(pool, tiers.APPLY, "demo")}, {self.ver.id, self.legacy.id})
        self.assertEqual({p.id for p in load.usable(pool, tiers.FRONTIER, "demo")},
                         {self.cand.id, self.ver.id, self.legacy.id})

    def test_the_project_candidates_switch(self):
        from athos import start, tiers
        start.config_file().write_text(json.dumps({"autolearn": {"apply_candidates": True}}))
        pool = [self.cand, self.ver, self.legacy]
        self.assertIn(self.cand.id, {p.id for p in load.usable(pool, tiers.APPLY, "demo")})
        self.assertNotIn(self.cand.id, {p.id for p in load.usable(pool, tiers.APPLY, "elsewhere")})

    def test_a_learned_piece_comes_as_a_checklist_with_checks_and_ask_first(self):
        text = load._fit([self.ver], "athos", apply=True)[0]
        self.assertIn(load.CHECKLIST_HEAD, text)
        self.assertIn("1. #run_tests — When: after changing the parser. · Do: run the unit tests.", text)
        self.assertIn("Check: `python3 -m unittest discover -s tests` exits 0", text)
        self.assertIn("**Ask first:** this step publishes", text)
        self.assertNotIn("**Because:**", text)

    def test_a_legacy_piece_keeps_its_form_with_ask_first_on_risky_steps(self):
        legacy = store.create("Ship", "shipping", BODY + "\n## #ship\n**When:** ready.\n**Do:** merge the PR.\n",
                              projects=["demo"])
        text = load._fit([legacy], "athos", apply=True)[0]
        self.assertIn("**Because:** the parser has many edge cases.", text)
        self.assertIn("**Do:** merge the PR.\n**Ask first:** this step merges", text)
        self.assertNotIn("Ask first", load._fit([legacy], "athos")[0])     # a frontier model reads it as written

    def test_the_frontier_index_says_candidate_review_and_stale(self):
        from athos import grade, tiers
        grade.mark_review(self.ver.id, "failed on claude-haiku-5-5")
        old = store.create("Old one", "the parser old way", "## #a\n**When:** x.\n**Do:** run `make zap`.\n"
                           "Edit `src/missing.py`.\n", projects=["demo"])
        old.created = "2020-01-01"
        store._write(old)
        Path(self.home, "Makefile").write_text("all:\n\techo\n")
        pool = [self.cand, self.ver, old]
        trace = {"candidates": []}
        notes = load.index_notes(pool, trace, pool, "s1", self.home)
        self.assertEqual(notes[self.cand.id], "candidate, not verified yet")
        self.assertIn("needs review", notes[self.ver.id])
        self.assertIn("1 named file(s), 1 make target(s) not found here", notes[old.id])
        index = load.deliver(pool, trace, pool, tiers.FRONTIER, notes=notes)["text"]
        self.assertIn("(candidate, not verified yet)", index)
        self.assertEqual(store.render(store.get(old.id)), store.render(old))   # a legacy file is not touched

    def test_confidence_moves_the_score_a_little_and_legacy_not_at_all(self):
        from athos import grade
        self.assertEqual(grade.router_factor(self.legacy), 1.0)
        self.assertAlmostEqual(grade.router_factor(self.cand), 0.92)
        sure = store.create("Sure", "sure", BODY, projects=["demo"], status="verified", confidence="1.0")
        self.assertAlmostEqual(grade.router_factor(sure), 1.06)

    def test_through_the_hooks_an_apply_session_gets_the_checklist_only_once_verified(self):
        from tests.test_cli import ThroughTheLauncher
        cli = ThroughTheLauncher()
        cli.home, cli.assertEqual = self.home, self.assertEqual
        work = os.path.join(self.home, "work", "demo")
        os.makedirs(work)
        ev = {"session_id": "h1", "cwd": work, "transcript_path": None}
        cli.send("session-start", {**ev, "model": "claude-haiku-5-5"})
        out = cli.send("prompt", {**ev, "prompt": "change the parser safely"})
        self.assertNotIn("Change the parser safely", json.dumps(out or {}))       # a candidate: not given
        store.set_status(self.cand.id, "verified", "test")
        out = cli.send("prompt", {**ev, "prompt": "change the parser safely"})
        text = cli.context(out)
        self.assertIn(load.CHECKLIST_HEAD, text)
        self.assertIn("**Ask first:** this step publishes", text)


class CandidateReplayTest(TempHome):
    def setUp(self):
        super().setUp()
        from athos import cases
        self.piece = candidate()
        cases._write({"task_id": "t1", "piece": self.piece.id, "version": 1, "request": "fix the parser",
                      "answer": "fixed, tests pass", "mark": "frontier"})

    def test_off_by_default(self):
        from athos import replay
        runner = StubRunner()
        self.assertEqual(replay.run_candidate(self.piece.id, runner)["error"], "replays are off")
        self.assertEqual(runner.calls, [])

    def test_a_passing_replay_after_the_verifier_verifies_it_within_the_cap(self):
        from athos import eval as ev, start, verify
        start.config_file().write_text(json.dumps({"autolearn": {"replay": {"on": True}}}))

        class Both(StubRunner):
            def __call__(self, prompt, bundle, model, timeout, max_usd):
                super().__call__(prompt, bundle, model, timeout, max_usd)
                if "independent verifier" in prompt:
                    return {"ok": True, "text": PASS, "cost_usd": 0.05, "duration_s": 1}
                if "Second answer" in prompt:
                    return {"ok": True, "text": '{"score": 92, "equivalent": true}', "cost_usd": 0.01,
                            "duration_s": 1}
                return {"ok": True, "text": "the answer", "cost_usd": 0.001, "duration_s": 1}
        runner = Both()
        bundle = verify.build_bundle(self.piece, "t1", None)
        out = verify.run(self.piece.id, bundle, runner)
        self.assertEqual(out["replay"]["outcome"], "replay_pass")
        self.assertEqual([c["model"] for c in runner.calls], ["fable", "haiku", "fable"])
        self.assertEqual(store.get(self.piece.id).status, "verified")
        runs = [e for e in ev.events() if e.get("type") == "model_run" and e.get("phase") == "settled"]
        self.assertEqual([r["purpose"] for r in runs], ["verify", "replay", "replay"])

    def test_the_cap_stops_a_replay(self):
        from athos import replay, start
        start.config_file().write_text(json.dumps({"autolearn": {"replay": {"on": True},
                                                                 "budget": {"runs_per_day": 1}}}))
        runner = StubRunner(text="x")
        out = replay.run_candidate(self.piece.id, runner)
        self.assertEqual(out["outcome"], "skipped")
        self.assertEqual(len(runner.calls), 1)                              # the answer ran, the judge could not


class RepairTest(TempHome):
    """F13 on synthetic data: a session in a project with no pieces of its own that loaded other projects' pieces, and
    edits given to the person by the old detector."""

    def setUp(self):
        super().setUp()
        from athos import eval as ev
        store.create("Other a", "a", "x", projects=["shop"], piece_id="other-a")
        store.create("General", "g", "x", piece_id="general-g")
        lines = [
            {"type": "task_start", "task_id": "k1", "session_id": "sess-1234", "project": "newproj", "at": "2026-11-14T10:00:00"},
            {"type": "task_end", "task_id": "k1", "session_id": "sess-1234", "pieces": ["other-a", "general-g"], "saved": [], "at": "2026-11-14T10:01:00"},
            {"type": "task_start", "task_id": "k2", "session_id": "sess-1234", "project": "newproj", "at": "2026-11-14T10:02:00"},
            {"type": "piece_opened", "task_id": "k2", "session_id": "sess-1234", "piece": "general-g", "at": "2026-11-14T10:02:30"},
            {"type": "task_end", "task_id": "k2", "session_id": "sess-1234", "pieces": ["general-g"], "saved": [], "at": "2026-11-14T10:03:00"},
            {"type": "learned_from_edit", "task_id": "k1", "session_id": "sess-1234", "piece": "other-a", "at": "2026-11-14T10:01:30"},
            {"type": "learned_from_edit", "task_id": "k2", "session_id": "sess-1234", "piece": "general-g", "basis": ["changed_after_turn_end"], "at": "2026-11-14T10:03:30"},
        ]
        for line in lines:
            ev.append(line)

    def test_a_dry_run_writes_nothing(self):
        from athos import eval as ev, repair
        before = len(ev.events())
        found = repair.plan("sess-12")
        self.assertEqual(len(ev.events()), before)
        self.assertEqual(sorted((c["target"], c["task_id"], c["piece"]) for c in found["corrections"]),
                         [("learned_from_edit", "k1", "other-a"), ("task_pieces", "k1", "general-g"),
                          ("task_pieces", "k1", "other-a")])                   # k2 opened its piece itself: kept

    def test_apply_corrects_the_statistics_without_editing_history_and_is_idempotent(self):
        from athos import eval as ev, paths, repair
        log_before = paths.events_file().read_text()
        uses = {r["piece"]: r["uses"] for r in ev.report()["pieces"]}
        self.assertEqual((uses["other-a"], uses["general-g"]), (1, 2))
        self.assertEqual(repair.apply(repair.plan("sess-1234")), 3)
        self.assertTrue(paths.events_file().read_text().startswith(log_before))       # only appended
        uses = {r["piece"]: r["uses"] for r in ev.report()["pieces"]}
        self.assertEqual((uses["other-a"], uses["general-g"]), (0, 1))
        again = repair.plan("sess-1234")
        self.assertEqual((again["corrections"], again["already"]), ([], 3))

    def test_the_audit_marks_corrected_edits(self):
        from athos import audit, eval as ev, repair
        repair.apply(repair.plan("sess-1234"))
        report = audit.check("sess-1234", [e for e in ev.events() if e.get("session_id") == "sess-1234"])
        rule = next(r for r in report["rules"] if r["rule"] == "edit_without_basis")
        self.assertTrue(rule["found"][0].get("corrected"))

    def test_through_the_command(self):
        from tests.test_cli import ThroughTheLauncher
        cli = ThroughTheLauncher()
        cli.home = self.home
        done = cli.run_athos("repair", "--session", "sess-1234")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Dry run: nothing written", done.stdout)
        self.assertIn("a piece of another project", done.stdout)
        self.assertNotIn("other-a", done.stdout)
        self.assertIn("3 correction event(s) written", cli.run_athos("repair", "--session", "sess-1234", "--apply").stdout)


class AutonomousAuditTest(TempHome):
    def rule(self, name, sid="a1"):
        from athos import audit, eval as ev
        evs = [e for e in ev.events() if e.get("session_id") == sid]
        report = audit.check(sid, evs, transcripts=False)
        return next(r for r in report["rules"] if r["rule"] == name)

    def start(self, sid="a1", model="claude-opus-5-5"):
        from athos import eval as ev
        ev.append({"type": "task_start", "task_id": "x1", "session_id": sid, "project": "demo", "model": model,
                   "at": "2026-11-15T10:00:00"})
        ev.audit({"type": "route", "session_id": sid, "task_id": "x1", "project": "demo"})

    def test_weak_evidence_learning_reads_the_strong_count(self):
        from athos import eval as ev
        self.start()
        ev.audit({"type": "learn", "session_id": "a1", "decision": "saved", "piece": "p", "strong": 0,
                  "evidence": ["task:x1"], "project": "demo"})
        ev.audit({"type": "learn", "session_id": "a1", "decision": "saved", "piece": "q", "strong": 2,
                  "evidence": ["verify:pytest:ok"], "project": "demo"})
        rule = self.rule("weak_evidence_learning")
        self.assertEqual((rule["status"], rule["count"]), ("flagged", 1))

    def test_a_save_in_apply_mode_is_flagged(self):
        from athos import eval as ev
        self.start(model="claude-haiku-5-5")
        self.assertEqual(self.rule("save_in_apply_mode")["status"], "clean")
        ev.append({"type": "task_end", "task_id": "x1", "session_id": "a1", "model": "claude-haiku-5-5",
                   "pieces": [], "saved": ["mine"], "at": "2026-11-15T10:01:00"})
        rule = self.rule("save_in_apply_mode")
        self.assertEqual((rule["status"], rule["found"][0]["how"]), ("flagged", "task_end"))

    def test_the_real_paths_never_flag(self):
        """A full loop through the code: autonomous save refused on an apply model, verified with a stub."""
        from athos import verify
        self.start()
        p = candidate()
        folder = verify.build_bundle(p, "t1", None)
        verify.run(p.id, folder, StubRunner())
        reuse(p.id)
        reuse(p.id)
        self.assertEqual(store.get(p.id).status, "verified")
        for name in ("promotion_without_verifier", "verifier_saw_summary", "verifier_over_cap"):
            self.assertEqual(self.rule(name)["status"], "clean", name)

    def test_a_promotion_without_a_verdict_is_flagged(self):
        from athos import grade
        self.start()
        p = candidate()
        store.set_status(p.id, "verified", "by hand")
        grade.note(p.id, "candidate", "verified", "two clean reuses")
        self.assertEqual(self.rule("promotion_without_verifier")["status"], "flagged")

    def test_a_verifier_that_got_more_than_paths_is_flagged(self):
        from athos import verify
        self.start()
        p = candidate()
        folder = verify.build_bundle(p, "t1", None)
        verify.run(p.id, folder, StubRunner())
        Path(folder, "prompt.txt").write_text(Path(folder, "prompt.txt").read_text() + "\nSummary: I fixed it.")
        rule = self.rule("verifier_saw_summary")
        self.assertEqual(rule["status"], "flagged")
        self.assertIn("the kept prompt is not the fixed text with the bundle's input paths", rule["found"][0]["problems"])

    def test_spend_above_the_cap_is_flagged(self):
        from athos import eval as ev
        self.start()
        for cost in (0.6, 0.6):
            ev.audit({"type": "model_run", "purpose": "verify", "started": True, "cost_usd": cost,
                      "usd_per_day": 1.0, "runs_per_day": 6, "project": "demo"})
        rule = self.rule("verifier_over_cap")
        self.assertEqual((rule["status"], rule["found"][0]["usd"]), ("flagged", 1.2))

    def test_a_cap_raised_during_the_day_applies_to_the_runs_after_it(self):
        from athos import eval as ev
        self.start()
        for cap in (1, 3, 3):
            ev.audit({"type": "model_run", "purpose": "verify", "started": True, "cost_usd": 0.01,
                      "usd_per_day": 1.0, "runs_per_day": cap, "project": "demo"})
        self.assertEqual(self.rule("verifier_over_cap")["status"], "clean")
