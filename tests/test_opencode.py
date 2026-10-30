import json
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
            # The sidebar: compiled, beside plugins/, listed in tui.json next to the person's own TUI plugins.
            tui = Path(cfg) / "opencode" / "tui.json"
            tui.write_text('{"plugin": ["file:///theirs"], "theme": "x"}')
            opencode.install(Path("/opt/athos/bin/athos"))
            side = Path(cfg) / "opencode" / "athos-sidebar" / "index.js"
            self.assertIn('"/opt/athos/bin/athos"', side.read_text())
            self.assertIn("sidebar_content", side.read_text())
            cfgj = json.loads(tui.read_text())
            self.assertEqual(cfgj["plugin"], ["file:///theirs", side.parent.as_uri()])
            self.assertEqual(cfgj["theme"], "x")
            self.assertTrue(opencode.uninstall())
            self.assertFalse(f.exists())
            self.assertFalse(side.exists())
            self.assertEqual(json.loads(tui.read_text())["plugin"], ["file:///theirs"])
            self.assertFalse(opencode.uninstall())

    def test_a_task_takes_the_tokens_and_model_the_platform_sends(self):
        ev.task_start({"session_id": "s1", "prompt": "review the lease", "cwd": self.home}, "opencode")
        rec = ev.task_end({"session_id": "s1", "model": "meta/muse-spark-1.3",
                           "tokens": {"input": 120, "output": 30, "cache_read": 50, "cache_write": 0}})
        self.assertEqual(rec["model"], "meta/muse-spark-1.3")
        self.assertEqual(rec["tokens"]["input"], 120)
        self.assertIn(("opencode", "OpenCode"), ev.AGENTS)
