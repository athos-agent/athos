import os
import tempfile
from pathlib import Path
from unittest import mock

from athos import eval as ev
from athos.adapters import opencode
from tests.helpers import TempHome


class OpenCodeTest(TempHome):
    def test_install_writes_the_plugin_with_the_athos_command_and_uninstall_removes_it(self):
        with tempfile.TemporaryDirectory() as cfg, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": cfg}):
            f = opencode.install(Path("/opt/athos/bin/athos"))
            self.assertEqual(f, Path(cfg) / "opencode" / "plugins" / "athos.js")
            text = f.read_text()
            self.assertIn('"/opt/athos/bin/athos"', text)
            self.assertNotIn("__ATHOS__", text)
            self.assertIn("export const AthosPlugin", text)
            self.assertTrue(opencode.uninstall())
            self.assertFalse(f.exists())
            self.assertFalse(opencode.uninstall())

    def test_a_task_takes_the_tokens_and_model_the_platform_sends(self):
        ev.task_start({"session_id": "s1", "prompt": "review the lease", "cwd": self.home}, "opencode")
        rec = ev.task_end({"session_id": "s1", "model": "meta/muse-spark-1.3",
                           "tokens": {"input": 120, "output": 30, "cache_read": 50, "cache_write": 0}})
        self.assertEqual(rec["model"], "meta/muse-spark-1.3")
        self.assertEqual(rec["tokens"]["input"], 120)
        self.assertIn(("opencode", "OpenCode"), ev.AGENTS)
