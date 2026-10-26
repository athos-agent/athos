import tempfile
from pathlib import Path

from athos import delegate, eval as ev, store
from tests.helpers import TempHome


def scripted(*replies):
    """A fake Ollama: each call returns the next reply and keeps the messages it was sent."""
    seen = []

    def chat(model, messages):
        seen.append([dict(m) for m in messages])
        msg = replies[len(seen) - 1]
        return {"message": msg, "prompt_eval_count": 100, "eval_count": 10}
    return chat, seen


def call(name, **args):
    return {"function": {"name": name, "arguments": args}}


class DelegateTest(TempHome):
    def setUp(self):
        super().setUp()
        self.piece = store.create("Cut a release", "release a new version", "Tag message `greet X.Y.Z`.")
        self._dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()
        super().tearDown()

    def test_the_model_works_with_the_piece_and_the_task_is_recorded_as_local(self):
        chat, seen = scripted({"content": "", "tool_calls": [call("write_file", path="VERSION", content="0.2.0\n")]},
                              {"content": "", "tool_calls": [call("run", command="cat VERSION")]},
                              {"content": "Released 0.2.0."})
        r = delegate.delegate(self.piece.id, "release 0.2.0", "tiny:1b", cwd=self.cwd, yes=True, out=lambda _: None,
                              chat_fn=chat)
        self.assertEqual((self.cwd / "VERSION").read_text(), "0.2.0\n")
        self.assertIn("Tag message `greet X.Y.Z`.", seen[0][0]["content"])
        self.assertIn("exit code 0\n0.2.0", seen[2][-1]["content"])
        self.assertEqual((r["summary"], r["steps"], r["tokens"]["total"]), ("Released 0.2.0.", 3, 330))
        t = ev.tasks()[0]
        self.assertEqual((t["platform"], t["model"], t["pieces"], t["result"]),
                         ("local", "tiny:1b", [self.piece.id], "unevaluated"))
        self.assertEqual(ev.report()["models"][0]["platform"], "local")

    def test_nothing_runs_without_permission(self):
        chat, seen = scripted({"content": "", "tool_calls": [call("run", command="touch made")]}, {"content": "ok"})
        delegate.delegate(self.piece.id, "x", "tiny:1b", cwd=self.cwd, out=lambda _: None, chat_fn=chat)
        self.assertFalse((self.cwd / "made").exists())
        self.assertIn("did not allow", seen[1][-1]["content"])

    def test_files_outside_the_project_are_refused(self):
        out = delegate.call_tool("write_file", {"path": "../escape", "content": "x"}, self.cwd, lambda _: True)
        self.assertIn("outside the project", out)
        self.assertFalse((self.cwd.parent / "escape").exists())

    def test_it_stops_after_the_step_limit(self):
        chat, _ = scripted(*[{"content": "", "tool_calls": [call("read_file", path=f"f{i}")]} for i in range(3)])
        r = delegate.delegate(self.piece.id, "x", "tiny:1b", cwd=self.cwd, yes=True, max_steps=3, out=lambda _: None,
                              chat_fn=chat)
        self.assertIn("stopped after 3 steps", r["summary"])

    def test_unknown_piece(self):
        with self.assertRaises(LookupError):
            delegate.delegate("nope", "x", cwd=self.cwd, chat_fn=lambda *a: {})

    def test_a_model_repeating_itself_is_stopped(self):
        again = {"content": "", "tool_calls": [call("run", command="true")]}
        chat, seen = scripted(*[again] * 10)
        r = delegate.delegate(self.piece.id, "x", "tiny:1b", cwd=self.cwd, yes=True, out=lambda _: None,
                              chat_fn=chat)
        self.assertIn("repeated the same step", r["summary"])
        self.assertEqual(len(seen), delegate.REPEATS)

    def test_edits_keep_the_rest_of_the_file(self):
        f = self.cwd / "CHANGELOG.md"
        f.write_text("# Changelog\n\n## [0.1.0]\n")
        out = delegate.call_tool("edit_file", {"path": "CHANGELOG.md", "old": "# Changelog\n\n",
                                               "new": "# Changelog\n\n## [0.2.0]\n\n"}, self.cwd, lambda _: True)
        self.assertEqual(out, "edited CHANGELOG.md")
        self.assertEqual(f.read_text(), "# Changelog\n\n## [0.2.0]\n\n## [0.1.0]\n")
        self.assertIn("exactly once", delegate.call_tool("edit_file", {"path": "CHANGELOG.md", "old": "nope", "new": ""},
                                                         self.cwd, lambda _: True))
