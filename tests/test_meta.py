import io
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from athos import delegate, eval as ev, paths, store
from athos.adapters import meta
from tests.helpers import TempHome


def reply(content="", calls=(), prompt=100, completion=10):
    return {"model": "muse-spark-1.3", "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
            "choices": [{"message": {"content": content, "tool_calls": [
                {"id": f"call_{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
                for i, (n, a) in enumerate(calls)] or None}}]}


def fake_api(*replies):
    """A fake Meta Model API: each request gets the next reply; the requests are kept."""
    sent = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        sent.append({"headers": dict(req.header_items()), "body": json.loads(req.data)})
        return Resp(json.dumps(replies[len(sent) - 1]).encode())
    return urlopen, sent


class MetaTest(TempHome):
    def setUp(self):
        super().setUp()
        self._key = os.environ.pop("MODEL_API_KEY", None)

    def tearDown(self):
        if self._key is not None:
            os.environ["MODEL_API_KEY"] = self._key
        super().tearDown()

    def test_key_from_the_environment_or_athos_env_file(self):
        with mock.patch.object(meta.Path, "home", return_value=Path(self.home) / "nobody"):
            self.assertIsNone(meta.api_key())
        (paths.home() / ".env").write_text("# Meta\nexport MODEL_API_KEY='k-file'\n")
        self.assertEqual(meta.api_key(), "k-file")

    def test_a_store_of_its_own_still_finds_the_persons_key(self):
        user = Path(self.home) / "user"
        (user / ".athos").mkdir(parents=True)
        (user / ".athos" / ".env").write_text("MODEL_API_KEY=k-user\n")
        with mock.patch.object(meta.Path, "home", return_value=user):
            self.assertEqual(meta.api_key(), "k-user")
        os.environ["MODEL_API_KEY"] = "k-env"
        self.assertEqual(meta.api_key(), "k-env")

    def test_no_key_sends_nothing(self):
        urlopen, sent = fake_api(reply("done"))
        with mock.patch.object(meta.Path, "home", return_value=Path(self.home) / "nobody"), \
                self.assertRaises(PermissionError):
            meta.chat("muse-spark-1.3", [{"role": "user", "content": "hi"}], urlopen=urlopen)
        self.assertEqual(sent, [])

    def test_tool_results_are_tied_to_the_calls_they_answer(self):
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "a", "function": {"name": "read_file", "arguments": {"path": "x"}}},
                    {"id": "b", "function": {"name": "run", "arguments": {"command": "ls"}}}]},
                {"role": "tool", "tool_name": "read_file", "content": "X"},
                {"role": "tool", "tool_name": "run", "content": "exit code 0"}]
        out = meta.to_openai(msgs)
        self.assertEqual(out[2]["tool_calls"][0]["function"]["arguments"], '{"path": "x"}')
        self.assertEqual([m.get("tool_call_id") for m in out[3:]], ["a", "b"])
        self.assertIsNone(out[2]["content"])

    def test_the_reply_comes_back_in_the_loops_shape(self):
        r = meta.from_openai(reply("", [("run", {"command": "pytest -q"})], prompt=543, completion=168))
        self.assertEqual(r["message"]["tool_calls"][0]["function"], {"name": "run", "arguments": {"command": "pytest -q"}})
        self.assertEqual((r["prompt_eval_count"], r["eval_count"]), (543, 168))

    def test_a_delegated_task_runs_in_athos_loop_and_is_recorded_as_meta(self):
        os.environ["MODEL_API_KEY"] = "k-1"
        piece = store.create("Cut a release", "release a new version", "Tag message `greet X.Y.Z`.")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "VERSION").write_text("0.1.0\n")
            urlopen, sent = fake_api(
                reply("", [("edit_file", {"path": "VERSION", "old": "0.1.0", "new": "0.2.0"})]),
                reply("Bumped to 0.2.0."))
            r = delegate.delegate(piece.id, "Release 0.2.0", "muse-spark-1.3", cwd=Path(d), yes=True,
                                  out=lambda *_: None, platform="meta",
                                  chat_fn=lambda m, msgs: meta.chat(m, msgs, urlopen=urlopen))
            self.assertEqual((Path(d) / "VERSION").read_text(), "0.2.0\n")
        body = sent[0]["body"]
        self.assertEqual((body["model"], body["reasoning_effort"], body["max_tokens"]), ("muse-spark-1.3", "low", 4000))
        self.assertIn("Tag message `greet X.Y.Z`.", body["messages"][0]["content"])
        self.assertEqual(sent[0]["headers"]["Authorization"], "Bearer k-1")
        self.assertEqual(sent[1]["body"]["messages"][-1]["tool_call_id"], "call_0")
        t = next(t for t in ev.tasks() if t["task_id"] == r["task_id"])
        self.assertEqual((t["platform"], t["model"], t["pieces"]), ("meta", "muse-spark-1.3", [piece.id]))
        self.assertEqual((r["summary"], r["tokens"]["total"]), ("Bumped to 0.2.0.", 220))
