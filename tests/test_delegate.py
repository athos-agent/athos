import tempfile
from pathlib import Path

from athos import delegate, eval as ev, store
from tests.helpers import TempHome


def fake_ollama(*replies):
    """Stands in for `delegate.chat`: the n-th call gets the n-th reply (as a message), and every conversation it was
    sent is kept, copied, for the test to inspect."""
    conversations = []

    def reply_next(model, messages):
        conversations.append([dict(m) for m in messages])
        return {"message": replies[len(conversations) - 1], "prompt_eval_count": 100, "eval_count": 10}
    return reply_next, conversations


def tool_call(name, **args):
    return {"function": dict(name=name, arguments=args)}


def asks(*calls):
    """A model turn that only calls tools."""
    return {"content": "", "tool_calls": list(calls)}


def allow_all(_what):
    return True


class DelegateTest(TempHome):
    """`athos delegate` against a fake Ollama, in a throwaway project folder."""

    def setUp(self):
        super().setUp()
        self.piece = store.create(title="Cut a release", when="release a new version",
                                  body="Tag message `greet X.Y.Z`.")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.cwd = Path(folder.name)

    def read(self, rel: str) -> str | None:
        """A file of (or next to) the project folder, or None when it was never written."""
        path = self.cwd / rel
        return path.read_text() if path.exists() else None

    def run_task(self, chat, request="x", **options):
        options.setdefault("out", lambda _line: None)
        return delegate.delegate(self.piece.id, request, "tiny:1b", cwd=self.cwd, chat_fn=chat, **options)

    def test_the_model_works_from_the_piece_and_the_run_is_logged_as_local(self):
        chat, sent = fake_ollama(asks(tool_call("write_file", path="VERSION", content="0.2.0\n")),
                                 asks(tool_call("run", command="cat VERSION")),
                                 {"content": "Released 0.2.0.", "tool_calls": []})
        result = self.run_task(chat, "release 0.2.0", yes=True)
        self.assertEqual(self.read("VERSION"), "0.2.0\n")
        system_prompt, last_tool_result = sent[0][0]["content"], sent[2][-1]["content"]
        self.assertIn(self.piece.body, system_prompt)
        self.assertIn("exit code 0\n0.2.0", last_tool_result)
        self.assertEqual((result["summary"], result["steps"], result["tokens"]["total"]), ("Released 0.2.0.", 3, 330))
        logged = ev.tasks()[0]
        expected = {"platform": "local", "model": "tiny:1b", "pieces": [self.piece.id], "result": "unevaluated"}
        self.assertEqual({key: logged[key] for key in expected}, expected)   # marked later with `athos mark`
        by_model = ev.report()["models"]
        self.assertEqual([m["platform"] for m in by_model], ["local"])

    def test_without_yes_and_without_a_terminal_nothing_runs(self):
        chat, sent = fake_ollama(asks(tool_call("run", command="touch made")), {"content": "ok"})
        self.run_task(chat)
        self.assertIsNone(self.read("made"))
        self.assertIn("did not allow", sent[1][-1]["content"])

    def test_paths_that_leave_the_project_are_refused(self):
        answer = delegate.call_tool("write_file", {"path": "../escape", "content": "x"}, self.cwd, allow_all)
        self.assertIn("outside the project", answer)
        self.assertIsNone(self.read("../escape"))

    def test_the_run_is_cut_at_the_step_limit(self):
        chat, _ = fake_ollama(*(asks(tool_call("read_file", path=f"f{n}")) for n in range(3)))
        self.assertIn("stopped after 3 steps", self.run_task(chat, yes=True, max_steps=3)["summary"])

    def test_an_unknown_piece_is_an_error(self):
        never_called = lambda *_: self.fail("no model should be asked")  # noqa: E731
        self.assertRaises(LookupError, delegate.delegate, "nope", "x", cwd=self.cwd, chat_fn=never_called)

    def test_a_model_going_round_in_circles_is_stopped(self):
        chat, sent = fake_ollama(*[asks(tool_call("run", command="true"))] * 10)
        self.assertIn("repeated the same step", self.run_task(chat, yes=True)["summary"])
        self.assertEqual(len(sent), delegate.REPEATS)

    def test_an_edit_changes_one_snippet_and_keeps_the_rest(self):
        changelog = self.cwd / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [0.1.0]\n")
        edit = {"path": "CHANGELOG.md", "old": "# Changelog\n\n", "new": "# Changelog\n\n## [0.2.0]\n\n"}
        self.assertEqual(delegate.call_tool("edit_file", edit, self.cwd, allow_all), "edited CHANGELOG.md")
        self.assertEqual(changelog.read_text(), "# Changelog\n\n## [0.2.0]\n\n## [0.1.0]\n")
        missing = {"path": "CHANGELOG.md", "old": "nope", "new": ""}
        self.assertIn("exactly once", delegate.call_tool("edit_file", missing, self.cwd, allow_all))

    def test_long_output_is_clipped_and_unknown_tools_are_named(self):
        (self.cwd / "big.txt").write_text("y" * (delegate.OUTPUT_LIMIT + 7))
        clipped = delegate.call_tool("read_file", {"path": "big.txt"}, self.cwd, allow_all)
        self.assertTrue(clipped.endswith("… (7 more chars)"))
        self.assertTrue(delegate.call_tool("fly", {}, self.cwd, allow_all).startswith("unknown tool fly"))
