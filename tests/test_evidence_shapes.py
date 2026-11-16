"""Evidence must not depend on how the model phrases its shell commands: commits are seen by watching HEAD, and
the classifier reads heredocs, line continuations, sequences, groups and comments. The command shapes below are the
ones a real session ran (a heredoc that edits a file followed by the validation run, a commit whose message comes
on stdin from a heredoc, read-only chains joined with `;`). Everything here is offline and synthetic."""

import os
import subprocess
import time
import unittest

from athos import evidence, session
from tests.helpers import TempHome

GIT = ["git", "-c", "user.email=a@example.com", "-c", "user.name=a"]


def _event(sid, cmd, cwd, ok=True, stdout="", tool_use_id="c1", agent=None):
    event = {"session_id": sid, "cwd": cwd, "tool_name": "Bash", "tool_input": {"command": cmd},
             "tool_use_id": tool_use_id, "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False}}
    if agent:
        event["agent_id"] = agent
    if not ok:
        event = {**event, "error": "Exit code 1\n" + stdout}
        event.pop("tool_response")
    return event


EDIT_THEN_VALIDATE = ("python3 - <<'EOF'\n"
                      "import pathlib\n"
                      "p = pathlib.Path('src/list.ts')\n"
                      "# npm test && git commit -m fake   <- data, not a command\n"
                      "p.write_text(p.read_text().replace('];', \"  'new',\\n];\"))\n"
                      "EOF\n"
                      "npm test")
COMMIT_FROM_STDIN = ("git add src/list.ts && git commit -q -F - <<'EOF'\n"
                     "Add an entry to the list\n"
                     "\n"
                     "pytest; npm test\n"
                     "EOF")


class ShapesTest(unittest.TestCase):
    def kinds(self, cmd):
        return [(s["label"], s["owns_success"], s["owns_failure"]) for s in evidence.classify(cmd)]

    def test_a_heredoc_body_is_data_and_the_command_goes_on_after_its_terminator(self):
        self.assertEqual(self.kinds(EDIT_THEN_VALIDATE), [("test", True, True)])
        self.assertEqual(evidence.classify(EDIT_THEN_VALIDATE)[0]["rule"], "last_in_sequence")

    def test_a_command_on_the_heredocs_own_line_runs_after_it(self):
        cmd = "python3 - <<'EOF' && npm test\nprint('pytest')\nEOF"
        self.assertEqual(self.kinds(cmd), [("test", True, False)])

    def test_a_dash_heredoc_and_an_unquoted_one(self):
        cmd = "cat > notes.txt <<-END\n\tpytest\n\tEND\npytest -q"
        self.assertEqual(self.kinds(cmd), [("pytest", True, True)])
        cmd = "cat > notes.txt <<END\nnpm test\nEND\nnpm run lint; echo done"
        self.assertEqual(self.kinds(cmd), [("lint", False, False)])

    def test_two_heredocs_and_a_herestring(self):
        cmd = "cat <<A <<'B'\nmake test\nA\nmake test\nB\nmake test"
        self.assertEqual(self.kinds(cmd), [("test", True, True)])
        self.assertEqual(self.kinds("grep x <<< 'pytest'; pytest"), [("pytest", True, True)])

    def test_the_commit_message_heredoc_is_not_read_as_commands(self):
        self.assertEqual(evidence.classify(COMMIT_FROM_STDIN), [])

    def test_validation_followed_by_a_commit_from_stdin(self):
        cmd = "npm test && git add a.ts && git commit -q -F - <<'EOF'\nmsg\n\nnpm run build\nEOF"
        self.assertEqual(self.kinds(cmd), [("test", True, False)])

    def test_line_continuations(self):
        self.assertEqual(self.kinds("pytest \\\n  -q \\\n  tests/test_x.py"), [("pytest", True, True)])
        self.assertEqual(self.kinds("cd app && \\\n npm test"), [("test", True, True)])

    def test_sequences_the_last_command_owns_the_status(self):
        self.assertEqual(self.kinds("ls; wc -l a.ts; npm test"), [("test", True, True)])
        self.assertEqual(self.kinds("npm test; ls"), [("test", False, False)])
        self.assertEqual(self.kinds("ls || true; npm test"), [("test", True, True)])
        self.assertEqual(self.kinds("ls\n\nnpm test\n"), [("test", True, True)])
        self.assertEqual(self.kinds("npm test || echo failed"), [("test", False, False)])
        self.assertEqual(self.kinds("ls && npm test"), [("test", True, False)])

    def test_groups(self):
        self.assertEqual(self.kinds("(cd app && npm test)"), [("test", True, True)])     # cd is setup
        self.assertEqual(self.kinds("(cd app; npm test)"), [("test", True, True)])
        self.assertEqual(self.kinds("(npm test; ls)"), [("test", False, False)])
        self.assertEqual(self.kinds("(cd app && npm test) | tail -3"), [("test", False, False)])
        self.assertEqual(self.kinds("{ ls; npm test; }"), [("test", True, True)])
        self.assertEqual(self.kinds("echo $(pytest --version) && ls"), [])
        self.assertEqual(self.kinds("(npm test) && git status"), [("test", True, False)])

    def test_comments(self):
        self.assertEqual(self.kinds("# run the suite\nnpm test"), [("test", True, True)])
        self.assertEqual(self.kinds("ls  # npm test"), [])
        self.assertEqual(self.kinds("npm test # the suite"), [("test", True, True)])

    def test_read_only_chains_have_no_verification(self):
        cmd = "athos show some-piece; ls; ls benchmark; wc -l src/list.ts; git log --stat -3 | head -40"
        self.assertEqual(evidence.classify(cmd), [])

    def test_a_validate_script_is_a_check(self):
        self.assertEqual(evidence.kind_of("npm run validate"), ("check", "validate"))
        self.assertEqual(evidence.kind_of("pnpm run check"), ("check", "check"))

    def test_an_unterminated_heredoc_is_all_data(self):
        self.assertEqual(evidence.classify("cat <<EOF\npytest\nnpm test"), [])


class ShapesOnToolTest(TempHome):
    """The shapes through the tool hook: a verification after a heredoc is recorded strong when it is last."""

    def setUp(self):
        super().setUp()
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})

    def test_validation_after_a_heredoc_edit_is_strong(self):
        evidence.on_tool(_event("s1", EDIT_THEN_VALIDATE, self.home, stdout="Tests: 3 passed, 3 total"), "s1")
        [item] = evidence.of_task("t1")
        self.assertEqual((item["type"], item["strength"], item["rule"]), ("verify", "strong", "last_in_sequence"))

    def test_a_command_that_mentions_athos_is_still_read(self):
        evidence.on_tool(_event("s1", "athos show some-piece; npm test", self.home, stdout="ok"), "s1")
        [item] = evidence.of_task("t1")
        self.assertEqual(item["strength"], "strong")

    def test_a_failed_sequence_whose_last_command_is_the_verification_is_a_strong_failure(self):
        evidence.on_tool(_event("s1", "ls; npm test", self.home, ok=False), "s1", failed=True)
        [item] = evidence.of_task("t1")
        self.assertEqual((item["ok"], item["strength"], item["polarity"]), (False, "strong", "negative"))

    def test_a_non_last_verification_stays_weak_when_the_call_succeeds(self):
        evidence.on_tool(_event("s1", "npm test; ls", self.home), "s1")
        [item] = evidence.of_task("t1")
        self.assertEqual(item["strength"], "weak")
        self.assertEqual(evidence.qualifies(evidence.of_task("t1"))[0], False)


class RunnerSummaryTest(TempHome):
    """A piped or non-last run whose output carries its runner's own summary, in a format Athos parses exactly."""

    def setUp(self):
        super().setUp()
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})

    def item(self, cmd, out, ok=True):
        found = evidence.on_tool(_event("s1", cmd, self.home, ok=ok, stdout=out), "s1", failed=not ok)
        return found[-1] if found else None

    def test_pytest_piped_into_tail_with_a_clean_summary_is_strong(self):
        it = self.item("pytest -q 2>&1 | tail -5", "....\n4 passed in 0.12s\n")
        self.assertEqual((it["strength"], it["polarity"], it["rule"]), ("strong", "positive", "runner_summary:pytest"))
        it = self.item("python3 -m pytest 2>&1 | tail -3", "==== 3 passed, 1 skipped in 1.02s ====")
        self.assertEqual(it["rule"], "runner_summary:pytest")

    def test_unittest_jest_and_vitest(self):
        it = self.item("python3 -m unittest 2>&1 | tail -4", "....\n----\nRan 4 tests in 0.1s\n\nOK\n")
        self.assertEqual(it["rule"], "runner_summary:unittest")
        it = self.item("npx jest 2>&1 | tail -5; ls", "Test Suites: 2 passed, 2 total\nTests:       5 passed, 5 total\n")
        self.assertEqual(it["rule"], "runner_summary:jest")
        it = self.item("npx vitest run | tail -4", " Test Files  1 passed (1)\n      Tests  3 passed (3)\n")
        self.assertEqual(it["rule"], "runner_summary:vitest")

    def test_a_summary_with_failures_is_a_strong_failure_even_when_tail_succeeded(self):
        it = self.item("pytest -q | tail -3", "F...\n1 failed, 3 passed in 0.2s\n")
        self.assertEqual((it["ok"], it["strength"], it["polarity"]), (False, "strong", "negative"))
        self.assertEqual(evidence.qualifies(evidence.of_task("t1"))[0], False)
        it = self.item("python3 -m unittest | tail -3", "Ran 4 tests in 0.1s\n\nFAILED (failures=1)\n")
        self.assertEqual((it["ok"], it["polarity"]), (False, "negative"))

    def test_anything_ambiguous_stays_weak(self):
        cases = [
            ("npm test | tail -5", "Tests:       5 passed, 5 total"),                 # the runner is not named
            ("pytest -q | grep -v FAIL", "4 passed in 0.1s"),                        # not a pure filter
            ("pytest -q | tail -1; pytest -q tests/b | tail -1", "4 passed in 0.1s\n2 passed in 0.1s"),  # two runs
            ("pytest -q | tail -5", "4 passed in 0.1s\n4 passed in 0.1s"),           # two summaries
            ("pytest -q > out.txt; tail -3 out.txt", "4 passed in 0.1s"),            # output not seen directly
            ("pytest -q | tail -5; echo '9 passed in 0.1s'", "4 passed in 0.1s"),    # something else prints
            ("pytest -q | tail -5", "no summary here"),
            ("pytest -q | tail -5", "0 passed in 0.1s"),
        ]
        for cmd, out in cases:
            it = self.item(cmd, out)
            self.assertEqual(it["strength"], "weak", cmd)

    def test_a_failed_call_is_never_upgraded_by_a_clean_summary(self):
        it = self.item("pytest -q | tail -3; npm run build", "4 passed in 0.1s\nbuild failed", ok=False)
        self.assertEqual([i["ok"] for i in evidence.of_task("t1")], [False, False])
        self.assertEqual(evidence.qualifies(evidence.of_task("t1"))[0], False)
        self.assertEqual(it["polarity"], "negative")


class CommitObservedTest(TempHome):
    """A commit is recorded when HEAD moved during the call, whatever the command said."""

    def setUp(self):
        super().setUp()
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5"})
        self.repo = os.path.join(self.home, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        self.commit("first")

    def commit(self, msg, *extra, date=None):
        env = dict(os.environ)
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run([*GIT, "commit", "-q", "--allow-empty", "-m", msg, *extra], cwd=self.repo, check=True, env=env)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def call(self, cmd, action, ok=True, agent=None):
        """Stamp the call's start, run `action` (what the command does to the repository), then end the call."""
        stamp = evidence.start_stamp(self.repo)
        stamp["at"] = time.time()
        action()
        return evidence.on_tool(_event("s1", cmd, self.repo, ok=ok, agent=agent), "s1", failed=not ok, started=stamp)

    def types(self):
        return [i["type"] for i in evidence.of_task("t1")]

    def test_a_commit_whose_message_came_from_a_heredoc(self):
        [item] = self.call(COMMIT_FROM_STDIN, lambda: self.commit("Add an entry"))
        self.assertEqual((item["type"], item["strength"], item["polarity"]), ("commit", "strong", "positive"))
        self.assertEqual(item["sha"], self.git("rev-parse", "HEAD")[:12])
        self.assertEqual(item["basis"], "head_moved")

    def test_a_commit_made_by_a_script_or_an_alias(self):
        items = self.call("./scripts/release.sh", lambda: (self.commit("one"), self.commit("two")))
        self.assertEqual([i["type"] for i in items], ["commit", "commit"])

    def test_nothing_to_commit_and_a_read_only_command(self):
        self.assertEqual(self.call("git commit -m x", lambda: None), [])
        self.assertEqual(self.call("git log -3 | head", lambda: None), [])

    def test_amend_is_one_commit(self):
        [item] = self.call("git commit --amend --no-edit", lambda: self.commit("first, again", "--amend"))
        self.assertEqual((item["type"], item.get("amend")), ("commit", True))

    def test_reset_backwards_is_revert_like_and_never_a_commit(self):
        self.commit("second")
        [item] = self.call("git reset --hard HEAD~1", lambda: self.git("reset", "-q", "--hard", "HEAD~1"))
        self.assertEqual((item["type"], item["strength"], item["polarity"], item["basis"]),
                         ("revert", "strong", "negative", "head_moved_back"))
        self.assertEqual(self.types(), ["revert"])        # the text heuristic does not add a second one

    def test_reset_sideways_is_a_rewrite_not_a_commit(self):
        self.commit("second")
        base = self.git("rev-parse", "HEAD~1")
        self.git("branch", "other", base)
        self.git("checkout", "-q", "other")
        self.commit("elsewhere", date="2001-01-01T00:00:00")
        self.git("checkout", "-q", "main")
        target = self.git("rev-parse", "other")
        items = self.call("git reset --hard other", lambda: self.git("reset", "-q", "--hard", target))
        self.assertNotIn("commit", [i["type"] for i in items])
        self.assertIn("rewrite", [i["type"] for i in items])

    def test_a_rebase_rewrites_without_counting_commits(self):
        self.commit("mine", date="2001-01-01T00:00:00")
        self.git("checkout", "-q", "-b", "up", "HEAD~1")
        self.commit("upstream", date="2001-01-02T00:00:00")
        self.git("checkout", "-q", "main")
        items = self.call("git rebase up", lambda: self.git("rebase", "-q", "up"))
        self.assertNotIn("commit", [i["type"] for i in items])

    def test_checkout_of_another_branch_is_no_commit_and_no_revert(self):
        self.git("branch", "old")
        self.commit("second", date="2001-01-01T00:00:00")
        self.assertEqual(self.call("git checkout old", lambda: self.git("checkout", "-q", "old")), [])
        self.assertEqual(self.call("git checkout main", lambda: self.git("checkout", "-q", "main")), [])

    def test_a_new_branch_with_a_commit(self):
        items = self.call("git checkout -b feature && git commit -m x",
                          lambda: (self.git("checkout", "-q", "-b", "feature"), self.commit("on feature")))
        self.assertEqual([i["type"] for i in items], ["commit"])

    def test_a_pull_that_fast_forwards_brings_others_commits_not_ours(self):
        self.git("checkout", "-q", "-b", "remote-ish")
        self.commit("someone else's", date="2001-01-01T00:00:00")
        self.git("checkout", "-q", "main")
        self.assertEqual(self.call("git merge --ff-only remote-ish",
                                   lambda: self.git("merge", "-q", "--ff-only", "remote-ish")), [])

    def test_a_subagents_call_is_not_recorded(self):
        self.assertEqual(self.call("git commit -m x", lambda: self.commit("by a subagent"), agent="a1"), [])

    def test_a_commit_while_a_subagent_was_working_is_weak(self):
        def act():
            session.update("s1", subagent_at=time.time())
            self.commit("whose?")
        [item] = self.call("sleep 1", act)
        self.assertEqual((item["type"], item["strength"]), ("commit", "weak"))

    def test_a_repository_with_no_commits_yet(self):
        fresh = os.path.join(self.home, "fresh")
        os.makedirs(fresh)
        subprocess.run(["git", "init", "-q"], cwd=fresh, check=True)
        stamp = evidence.start_stamp(fresh)
        self.assertEqual(stamp.get("head"), "")
        stamp["at"] = time.time()
        subprocess.run([*GIT, "commit", "-q", "--allow-empty", "-m", "root"], cwd=fresh, check=True)
        [item] = evidence.on_tool(_event("s1", "git commit -m root", fresh), "s1", started=stamp)
        self.assertEqual(item["type"], "commit")

    def test_a_failed_call_that_still_committed(self):
        items = self.call("git commit -m x && npm test", lambda: self.commit("committed, then tests failed"),
                          ok=False)
        self.assertEqual([(i["type"], i["polarity"]) for i in items], [("verify", "negative"), ("commit", "positive")])
        self.assertEqual(evidence.qualifies(evidence.of_task("t1"))[0], False)   # the failure counts against it

    def test_outside_a_repository_nothing_is_stamped(self):
        outside = os.path.join(self.home, "plain")
        os.makedirs(outside)
        self.assertEqual(evidence.start_stamp(outside), {})

    def test_the_stamp_reads_packed_refs_and_a_detached_head(self):
        self.git("pack-refs", "--all")
        self.assertEqual(evidence.start_stamp(self.repo), {"head": self.git("rev-parse", "HEAD"),
                                                           "branch": "refs/heads/main"})
        self.git("checkout", "-q", "--detach")
        self.assertEqual(evidence.start_stamp(self.repo), {"head": self.git("rev-parse", "HEAD"), "branch": ""})

    def test_a_worktree(self):
        other = os.path.join(self.home, "wt")
        self.git("worktree", "add", "-q", "-b", "side", other)
        self.assertEqual(evidence.start_stamp(other), {"head": self.git("rev-parse", "HEAD"),
                                                       "branch": "refs/heads/side"})

    def test_the_stamp_is_cheap(self):
        evidence.start_stamp(self.repo)
        t0 = time.perf_counter()
        for _ in range(10):
            evidence.start_stamp(self.repo)
        per_call = (time.perf_counter() - t0) / 10
        self.assertLess(per_call, 0.01)             # files only: no git process


if __name__ == "__main__":
    unittest.main()
