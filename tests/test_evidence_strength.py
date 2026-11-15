"""What counts as strong evidence that work was checked: only a command that really verified something, whose own
exit status the hook saw, and never one that ran nothing, ran in the background, or asked a runner for its version.
Everything here is offline and synthetic."""

import os
import subprocess
import unittest

from athos import evidence, session, store
from tests.helpers import TempHome


def _bash(sid, cmd, cwd, ok=True, stdout="", background=False):
    event = {"session_id": sid, "cwd": cwd, "tool_name": "Bash", "tool_input": {"command": cmd},
             "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False}}
    if background:
        event["tool_input"]["run_in_background"] = True
        event["tool_response"]["backgroundTaskId"] = "b1"
    if not ok:
        event = {**event, "error": "Exit code 1\n" + stdout}
        event.pop("tool_response")
    return evidence.on_tool(event, sid, failed=not ok)


class NothingVerifiedTest(unittest.TestCase):
    def test_info_and_dry_run_flags_verify_nothing(self):
        for cmd in ["pytest --version", "pytest --help", "pytest --collect-only", "pytest --co -q", "npm test -- --help",
                    "cargo test --no-run", "make -n test", "make --dry-run check", "go test -h ./...", "tox --version",
                    "jest --listTests", "python3 -m unittest --help", "mypy --version", "eslint --help src"]:
            self.assertIsNone(evidence.kind_of(cmd), cmd)

    def test_a_longer_word_is_not_the_runner(self):
        for cmd in ["pytest-watch", "make test-clean", "make check-format-config", "npm run build-storybook-docs-x"]:
            found = evidence.kind_of(cmd)
            self.assertFalse(found and found[1] in ("pytest", "test", "check"), cmd)
        self.assertIsNone(evidence.kind_of("pytest-watch"))
        self.assertIsNone(evidence.kind_of("make test-clean"))

    def test_a_fixer_is_not_a_check(self):
        for cmd in ["npm run lint:fix", "eslint --fix src", "ruff check --fix .", "npm run lint -- --fix"]:
            self.assertIsNone(evidence.kind_of(cmd), cmd)

    def test_excluding_the_tests_is_not_a_test_run(self):
        self.assertNotEqual((evidence.kind_of("gradle build -x test") or ("",))[0], "test")
        self.assertNotEqual((evidence.kind_of("./gradlew assemble --exclude-task test") or ("",))[0], "test")

    def test_a_comment_runs_nothing(self):
        self.assertEqual(evidence.classify("true # && pytest"), [])
        self.assertEqual(evidence.classify("echo hi  # pytest"), [])
        self.assertEqual(len(evidence.classify("pytest -q '#not a comment'")), 1)

    def test_a_check_that_is_not_a_verification_is_not_runnable(self):
        piece = store.Piece(id="p", title="t", when="w", body="## #s\n**When:** x.\n**Do:** y.\n"
                                                                "**Check:** `git status` is clean\n")
        self.assertEqual(evidence.checks_of(piece), [])
        self.assertEqual(evidence.classify("git status --short", [("p", "s", "git status")]), [])
        good = store.Piece(id="q", title="t", when="w", body="## #s\n**When:** x.\n**Do:** y.\n"
                                                              "**Check:** `pytest -q tests/test_x.py` passes\n")
        self.assertEqual(evidence.checks_of(good), [("s", "pytest -q tests/test_x.py")])

    def test_the_revert_pattern_matches_only_throwing_work_away(self):
        for cmd in ["git restore --staged x.py", "git revert --abort", "git revert --quit",
                    "git reset --hard origin/main", "git reset --hard @{u}", "git restore --staged -- a b"]:
            self.assertIsNone(evidence._REVERT.match(evidence._bare(cmd)), cmd)
        for cmd in ["git revert HEAD", "git reset --hard", "git reset --hard HEAD~1", "git checkout -- x.py",
                    "git restore x.py", "git restore --staged --worktree x.py", "git checkout ."]:
            self.assertIsNotNone(evidence._REVERT.match(evidence._bare(cmd)), cmd)

    def test_a_commit_helper_is_not_a_commit(self):
        for cmd in ["git commit-tree abc -m x", "git commit --help", "git commit -h", "git commit --dry-run -m x"]:
            self.assertIsNone(evidence._COMMIT.match(evidence._bare(cmd)), cmd)
        self.assertIsNotNone(evidence._COMMIT.match(evidence._bare("git commit -m 'x'")))


class ZeroTestsTest(TempHome):
    def setUp(self):
        super().setUp()
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})

    def test_a_run_of_no_test_is_not_strong(self):
        for out in ["Ran 0 tests in 0.000s\n\nOK", "collected 0 items\n\n=== no tests ran in 0.01s ===",
                    "?   \texample.com/x\t[no test files]", "running 0 tests\n\ntest result: ok. 0 passed",
                    "No tests found, exiting with code 0", "  0 passing (2ms)"]:
            label_cmd = {"Ran": "python3 -m unittest", "collected": "pytest", "?": "go test ./...",
                         "running": "cargo test", "No": "npx jest", " ": "npx mocha"}[out.split()[0] if out[0] != " "
                                                                                      else " "]
            [item] = _bash("s1", label_cmd, self.home, stdout=out)
            self.assertEqual(item["strength"], "weak", out)
            self.assertIn("no test ran", item["why_weak"])
        self.assertEqual(evidence.qualifies(evidence.of_task("t1")), (False, "no_strong_evidence"))

    def test_a_run_that_counts_tests_stays_strong(self):
        [item] = _bash("s1", "python3 -m unittest", self.home, stdout="Ran 4 tests in 0.1s\n\nOK")
        self.assertEqual(item["strength"], "strong")
        [item] = _bash("s1", "go test ./...", self.home, stdout="?   \tx/a\t[no test files]\nok  \tx/b\t0.01s")
        self.assertEqual(item["strength"], "strong")

    def test_a_background_run_is_no_evidence(self):
        self.assertEqual(_bash("s1", "pytest -q", self.home, background=True), [])
        self.assertEqual(evidence.of_task("t1"), [])


class FailedChainTest(TempHome):
    def setUp(self):
        super().setUp()
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})

    def test_a_failed_chain_with_a_verification_blocks_until_a_later_pass(self):
        _bash("s1", "pytest -q", self.home, stdout="3 passed")
        _bash("s1", "pytest && npm run build", self.home, ok=False)
        self.assertEqual(evidence.qualifies(evidence.of_task("t1"))[0], False)
        _bash("s1", "pytest -q", self.home, stdout="3 passed")
        self.assertEqual(evidence.qualifies(evidence.of_task("t1")), (True, "strong_evidence"))

    def test_a_piped_failure_blocks_too(self):
        _bash("s1", "pytest -q", self.home, stdout="3 passed")
        _bash("s1", "pytest 2>&1 | tail -5", self.home, ok=False)
        self.assertEqual(evidence.qualifies(evidence.of_task("t1"))[0], False)

    def test_a_failure_without_any_verification_in_it_does_not(self):
        _bash("s1", "pytest -q", self.home, stdout="3 passed")
        _bash("s1", "ls missing-folder", self.home, ok=False)
        self.assertEqual(evidence.qualifies(evidence.of_task("t1")), (True, "strong_evidence"))


class ItemCapTest(TempHome):
    def test_strong_items_are_never_dropped(self):
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})
        for _ in range(evidence.ITEMS_CAP + 5):
            evidence.note_reaction("t1", "ok")                 # weak: these may be capped
        _bash("s1", "pytest -q", self.home, stdout="3 passed")
        _bash("s1", "pytest -q", self.home, ok=False)
        items = evidence.of_task("t1")
        self.assertEqual([i["ok"] for i in items if i["type"] == "verify"], [True, False])
        self.assertEqual(evidence.qualifies(items), (False, "last_verification_failed"))
        self.assertLessEqual(sum(1 for i in items if i["strength"] == "weak"), evidence.ITEMS_CAP)


class CommitTest(TempHome):
    def setUp(self):
        super().setUp()
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})
        self.repo = os.path.join(self.home, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=a", "commit", "-q",
                        "--allow-empty", "-m", "x"], cwd=self.repo, check=True)

    def test_a_commit_that_did_not_own_the_success_is_not_recorded(self):
        for cmd in ["git commit -m x || true", "git commit -m x; echo done", "git commit --help"]:
            self.assertEqual([i["type"] for i in _bash("s1", cmd, self.repo)], [], cmd)


if __name__ == "__main__":
    unittest.main()
