"""Baseten Model APIs as a delegation backend (Meta's open-weights Muse Spark Open). No network: HTTP is faked."""

import contextlib
import io
import os
import tempfile
import urllib.request
from pathlib import Path
from unittest import mock

from athos import bench, cli, delegate, eval as ev, paths, replay, store
from athos.adapters import baseten, meta
from tests.helpers import TempHome
from tests.test_meta import fake_api, reply


class BasetenTest(TempHome):
    def setUp(self):
        super().setUp()
        self._keys = {k: os.environ.pop(k, None) for k in ("BASETEN_API_KEY", "MODEL_API_KEY")}
        # The person's real ~/.athos/.env must never be read by a test.
        self._nohome = mock.patch.object(meta.Path, "home", return_value=Path(self.home) / "nobody")
        self._nohome.start()

    def tearDown(self):
        self._nohome.stop()
        for k, v in self._keys.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        super().tearDown()

    def test_key_from_the_environment_or_the_env_file_and_never_meta_s(self):
        self.assertIsNone(baseten.api_key())
        (paths.home() / ".env").write_text("MODEL_API_KEY=k-meta\nexport BASETEN_API_KEY=\"k-file\"\n")
        self.assertEqual(baseten.api_key(), "k-file")
        self.assertEqual(meta.api_key(), "k-meta")
        os.environ["BASETEN_API_KEY"] = "k-env"
        self.assertEqual(baseten.api_key(), "k-env")

    def test_no_key_sends_nothing_and_names_the_variable(self):
        urlopen, sent = fake_api(reply("done"))
        with self.assertRaises(PermissionError) as e:
            baseten.chat(baseten.DEFAULT_MODEL, [{"role": "user", "content": "hi"}], urlopen=urlopen)
        self.assertIn("BASETEN_API_KEY", str(e.exception))
        self.assertEqual(sent, [])

    def test_the_cli_says_which_variable_is_missing(self):
        piece = store.create("Cut a release", "release a new version", "Bump VERSION.")
        err = io.StringIO()
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("no network")), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["delegate", piece.id, "Release 0.2.0", "--backend", "baseten", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("BASETEN_API_KEY", err.getvalue())

    def test_a_delegated_task_runs_in_athos_loop_and_is_recorded_as_baseten(self):
        os.environ["BASETEN_API_KEY"] = "k-1"
        piece = store.create("Cut a release", "release a new version", "Tag message `greet X.Y.Z`.")
        urlopen, sent = fake_api(
            reply("", [("edit_file", {"path": "VERSION", "old": "0.1.0", "new": "0.2.0"})]),
            reply("Bumped to 0.2.0."))
        with tempfile.TemporaryDirectory() as d, mock.patch.object(urllib.request, "urlopen", urlopen), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            (Path(d) / "VERSION").write_text("0.1.0\n")
            cwd = os.getcwd()
            os.chdir(d)
            try:
                code = cli.main(["delegate", piece.id, "Release 0.2.0", "--backend", "baseten", "--yes"])
            finally:
                os.chdir(cwd)
            self.assertEqual((Path(d) / "VERSION").read_text(), "0.2.0\n")
        self.assertIn(code, (0, None))
        req = sent[0]
        self.assertEqual(req["url"], "https://inference.baseten.co/v1/chat/completions")
        self.assertEqual(req["headers"]["Authorization"], "Bearer k-1")
        body = req["body"]
        self.assertEqual((body["model"], body["reasoning_effort"]), ("meta-models/muse-spark-open-1026", "low"))
        self.assertEqual([t["function"]["name"] for t in body["tools"]], ["run", "read_file", "edit_file", "write_file"])
        self.assertEqual(sent[1]["body"]["messages"][-1]["tool_call_id"], "call_0")
        self.assertNotIn("k-1", out.getvalue())
        self.assertIn("baseten / meta-models/muse-spark-open-1026", out.getvalue())
        t = ev.tasks()[-1]
        self.assertEqual((t["platform"], t["model"], t["pieces"]),
                         ("baseten", "meta-models/muse-spark-open-1026", [piece.id]))

    def test_model_flag_overrides_the_default(self):
        args = cli.argparse.Namespace(backend="baseten", model="meta-models/muse-spark-open")
        platform, model, chat_fn = cli._delegation_backend(args)
        self.assertEqual((platform, model, chat_fn), ("baseten", "meta-models/muse-spark-open", baseten.chat))

    def test_replay_and_by_step_and_bench_know_baseten(self):
        platform, model, _ask = replay.backend("baseten")
        self.assertEqual((platform, model), ("baseten", baseten.DEFAULT_MODEL))
        self.assertEqual(delegate.parse_spec("baseten"), ("baseten", baseten.DEFAULT_MODEL))
        self.assertEqual(delegate.parse_spec("baseten:meta-models/muse-spark-open"),
                         ("baseten", "meta-models/muse-spark-open"))
        self.assertEqual(delegate.spec_of("baseten", baseten.DEFAULT_MODEL), "baseten")
        self.assertIn("baseten", bench.AGENTS)
        self.assertIs(bench.RUNNERS["baseten"], bench.run_baseten)

    def test_a_replay_sends_no_tools(self):
        os.environ["BASETEN_API_KEY"] = "k-1"
        urlopen, sent = fake_api(reply("an answer"))
        with mock.patch.object(urllib.request, "urlopen", urlopen):
            _p, model, ask = replay.backend("baseten")
            self.assertEqual(ask(model, "system", "user"), "an answer")
        self.assertNotIn("tools", sent[0]["body"])

    def test_an_http_error_names_baseten(self):
        import urllib.error
        e = urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b"bad key"))
        self.assertIn("Baseten Model APIs refused the request (HTTP 401)",
                      cli._model_error(e, "baseten", baseten.DEFAULT_MODEL))
