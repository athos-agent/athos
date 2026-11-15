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
        checks = [("release", "built", "./scripts/smoke.sh --fast")]
        from athos import evidence
        found = evidence.classify("./scripts/smoke.sh --fast --verbose", checks)
        self.assertEqual((found[0]["kind"], found[0]["check_of"]), ("check", "release#built"))
        self.assertEqual(evidence.classify("pytest -q", [("p", "s", "pytest -q")])[0]["check_of"], "p#s")

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
        _bash("s1", "git commit -m 'x'", repo)
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

    def task(self, model="claude-opus-5-5", verify=True, ok=True, edits=4):
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
        return self.cli.send("stop", self.ev)

    def learns(self):
        from athos import eval as ev
        return [e for e in ev.events() if e.get("type") == "learn"]


class AutonomousSaveTest(_HookedTask):
    """A frontier task, then the model's `athos save --auto`."""

    def test_a_qualifying_frontier_task_with_strong_evidence_saves_a_candidate(self):
        asked = self.task()
        line = asked["hookSpecificOutput"]["additionalContext"]
        self.assertIn("save --auto", line)
        self.assertEqual(len(line.splitlines()), 1)                         # one short line: the person sees it
        self.assertLess(len(line), 200)
        done = self.cli.run_athos("save", "--auto", stdin=PIECE, cwd=self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("as a candidate of demo", done.stdout)
        [piece] = store.all_pieces()
        self.assertEqual((piece.status, piece.projects, piece.learned_by, piece.visibility, piece.risk),
                         ("candidate", ["demo"], "claude-opus-5-5", "project", "normal"))
        self.assertIn("verify:unittest:ok", piece.evidence)
        self.assertTrue(any(e.startswith("task:") for e in piece.evidence))
        decisions = [(e["decision"], e["reason"]) for e in self.learns()]
        self.assertEqual(decisions, [("asked", "strong_evidence"), ("saved", "strong_evidence")])
        self.assertEqual(self.learns()[-1]["checks"], 2)

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
        self.assertEqual(self.learns()[-1]["reason"], "model_saved_nothing")

    def test_an_existing_piece_is_never_changed_autonomously(self):
        old = store.create("Old", "old", "x", projects=["demo"])
        self.task()
        done = self.cli.run_athos("save", "--auto", stdin=PIECE.replace("---\ntitle", f"---\nid: {old.id}\ntitle"),
                                  cwd=self.work)
        self.assertIn("new pieces only", done.stderr)
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
