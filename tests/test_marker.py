"""The project marker (`.athos.toml`): how it is found and read, and what it may decide. All data here is synthetic."""

import builtins
import contextlib
import io
import subprocess
import sys
from pathlib import Path
from unittest import mock

from athos import cli, paths
from tests.helpers import TempHome


@contextlib.contextmanager
def without_tomllib():
    """Run as on a Python older than 3.11, where `import tomllib` fails."""
    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "tomllib":
            raise ModuleNotFoundError("No module named 'tomllib'")
        return real(name, *args, **kwargs)
    saved = sys.modules.pop("tomllib", None)
    with mock.patch.object(builtins, "__import__", refuse):
        try:
            yield
        finally:
            if saved is not None:
                sys.modules["tomllib"] = saved


class OlderPythonTest(TempHome):
    """The hooks run under whatever `python3` the agent finds, which may be older than 3.11 (no tomllib)."""

    def test_the_marker_is_read_without_tomllib(self):
        root = Path(self.home) / "alpha"
        root.mkdir()
        (root / paths.MARKER).write_text('# a comment\nname = "alpha"  # trailing\npublic = true\n\n[extra]\n'
                                         'public = false\n')
        with without_tomllib():
            mark = paths.marker(root)
            self.assertEqual((mark.get("name"), mark.get("public")), ("alpha", True))
            self.assertTrue(paths.is_public(root))
            (root / paths.MARKER).write_text("name = 'alpha'\npublic = false\n")
            self.assertIs(paths.marker(root).get("public"), False)

    def test_a_hook_runs_without_tomllib(self):
        root = Path(self.home) / "alpha"
        root.mkdir()
        (root / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        err = io.StringIO()
        payload = '{"session_id": "s1", "cwd": "%s", "prompt": "hello"}' % root
        with without_tomllib(), mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cli.hook("prompt"), 0)
        self.assertEqual(err.getvalue(), "")
