import os
import tempfile
import unittest

# Environment variables a test must never let point at the user's real data, each mapped to the folder (inside the
# test's temporary home) it is redirected to. None means the temporary home itself.
_SANDBOXED_ENV = {
    "ATHOS_HOME": None,                         # the know-how store
    "CODEX_HOME": "codex-home",                 # Codex sessions and skills (~/.codex)
    "XDG_DATA_HOME": "xdg-data",                # Muse Code sessions
    "ATHOS_SKILLS_DIR": "agents-skills",        # exported skills
    "XDG_CONFIG_HOME": "xdg-config",            # OpenCode plugins
}


class TempHome(unittest.TestCase):
    """Base class that runs every test against a fresh temporary ATHOS_HOME (available as `self.home`), with the
    other agents' folders redirected under it too. Whatever the environment held before is put back afterwards."""

    def setUp(self):
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = self._home_dir.name
        self._saved_env = {name: os.environ.get(name) for name in _SANDBOXED_ENV}
        for name, sub in _SANDBOXED_ENV.items():
            os.environ[name] = self.home if sub is None else os.path.join(self.home, sub)

    def tearDown(self):
        for name, before in self._saved_env.items():
            if before is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = before
        self._home_dir.cleanup()
