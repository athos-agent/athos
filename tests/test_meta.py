import json
import os
import subprocess
import tempfile
from pathlib import Path

from athos import eval as ev, paths, store
from athos.adapters import meta
from tests.helpers import TempHome


def fake_run(stdout, code=0, stderr=""):
    """A fake agent: keeps the command and environment it was started with, returns the given output."""
    seen = {}

    def run(cmd, cwd=None, env=None, **_):
        seen.update(cmd=cmd, cwd=cwd, env=env, home_exists=Path(env["ATHOS_HOME"]).is_dir())
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)
    return run, seen


CLAUDE_OUT = json.dumps({"result": "Released 0.3.0.", "is_error": False, "num_turns": 7,
                         "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 5000,
                                   "cache_creation_input_tokens": 0},
                         "modelUsage": {"muse-spark-1.3": {}}})

CODEX_OUT = "\n".join(json.dumps(e) for e in [
    {"type": "thread.started"},
    {"type": "item.completed", "item": {"type": "command_execution", "command": "pytest", "exit_code": 0}},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "Done: greet 0.3.0."}},
    {"type": "turn.completed", "usage": {"input_tokens": 900, "cached_input_tokens": 400, "output_tokens": 120}},
])


class MetaTest(TempHome):
    def setUp(self):
        super().setUp()
        self.piece = store.create("Cut a release", "release a new version", "Tag message `greet X.Y.Z`.")
        self._dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self._dir.name)
        self._key = os.environ.pop("MODEL_API_KEY", None)

    def tearDown(self):
        if self._key is not None:
            os.environ["MODEL_API_KEY"] = self._key
        self._dir.cleanup()
        super().tearDown()

    def test_key_from_env_file_in_athos_home(self):
        self.assertIsNone(meta.api_key())
        (paths.home() / ".env").write_text("# Meta\nexport MODEL_API_KEY='k-123'\n")
        self.assertEqual(meta.api_key(), "k-123")
        os.environ["MODEL_API_KEY"] = "k-env"
        self.assertEqual(meta.api_key(), "k-env")

    def test_no_key_runs_nothing(self):
        run, seen = fake_run(CLAUDE_OUT)
        with self.assertRaises(PermissionError):
            meta.delegate(self.piece.id, "Release 0.3.0", cwd=self.cwd, run=run)
        self.assertEqual(seen, {})

    def test_claude_on_meta_is_recorded_with_the_model_that_answered(self):
        os.environ["MODEL_API_KEY"] = "k-1"
        run, seen = fake_run(CLAUDE_OUT)
        r = meta.delegate(self.piece.id, "Release 0.3.0", "claude", cwd=self.cwd, run=run)
        env = seen["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.meta.ai")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "k-1")
        for var in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"):
            self.assertEqual(env[var], "muse-spark-1.3")
        self.assertNotIn("ANTHROPIC_API_KEY", {k for k in env if env[k] == "k-1"})
        # The agent gets a throwaway Athos home with capture off, and only the delegated piece as know-how.
        self.assertNotEqual(env["ATHOS_HOME"], self.home)
        self.assertTrue(seen["home_exists"])
        self.assertEqual(env["ATHOS_CAPTURE"], "off")
        cmd = seen["cmd"]
        self.assertIn("Tag message `greet X.Y.Z`.", cmd[cmd.index("--append-system-prompt") + 1])
        self.assertNotIn("Bash", cmd[cmd.index("--allowedTools") + 1].split())
        self.assertNotIn("k-1", " ".join(cmd))
        t = next(t for t in ev.tasks() if t["task_id"] == r["task_id"])
        self.assertEqual((t["platform"], t["model"], t["pieces"]), ("claude-code", "muse-spark-1.3", [self.piece.id]))
        self.assertEqual(t["tokens"]["total"], 1500)
        self.assertEqual(r["summary"], "Released 0.3.0.")

    def test_yes_lets_claude_run_commands(self):
        os.environ["MODEL_API_KEY"] = "k-1"
        run, seen = fake_run(CLAUDE_OUT)
        meta.delegate(self.piece.id, "Release 0.3.0", "claude", cwd=self.cwd, yes=True, run=run)
        cmd = seen["cmd"]
        self.assertIn("Bash", cmd[cmd.index("--allowedTools") + 1].split())

    def test_codex_on_meta_never_touches_the_users_codex_home(self):
        os.environ["MODEL_API_KEY"] = "k-2"
        run, seen = fake_run(CODEX_OUT)
        r = meta.delegate(self.piece.id, "Release 0.3.0", "codex", "muse-wonder-1.0", cwd=self.cwd, run=run)
        cmd, env = seen["cmd"], seen["env"]
        self.assertEqual(cmd[:2], ["codex", "exec"])
        self.assertIn('model_providers.meta.base_url="https://api.meta.ai/v1"', cmd)
        self.assertIn('model_providers.meta.wire_api="responses"', cmd)
        self.assertEqual(cmd[cmd.index("-m") + 1], "muse-wonder-1.0")
        self.assertTrue(env["CODEX_HOME"].startswith(env["ATHOS_HOME"]))
        self.assertEqual(env["MODEL_API_KEY"], "k-2")
        self.assertIn("Tag message `greet X.Y.Z`.", cmd[-1])
        self.assertTrue(cmd[-1].endswith("Release 0.3.0"))
        t = next(t for t in ev.tasks() if t["task_id"] == r["task_id"])
        self.assertEqual((t["platform"], t["model"]), ("codex", "muse-wonder-1.0"))
        self.assertEqual((r["summary"], r["steps"], t["tokens"]["total"]), ("Done: greet 0.3.0.", 1, 1020))

    def test_an_agent_that_never_reached_the_model_is_not_recorded(self):
        os.environ["MODEL_API_KEY"] = "k-1"
        run, _ = fake_run("", code=1, stderr="API Error: 401 invalid key")
        with self.assertRaisesRegex(RuntimeError, "401"):
            meta.delegate(self.piece.id, "Release 0.3.0", "claude", cwd=self.cwd, run=run)
        self.assertEqual(ev.tasks(), [])
