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
    "CLAUDE_CONFIG_DIR": "claude-config",       # Claude Code's settings (the default model a session guesses from)
}


_OUTER_SESSION = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "ATHOS_SESSION_ID",
                  "CODEX_THREAD_ID", "CODEX_SANDBOX", "MUSE_PLUGIN_ID", "OPENCODE",
                  # the outer Claude Code process and model: a guessed model must come from the test, not from them
                  "CLAUDE_PID", "ANTHROPIC_MODEL", "CLAUDE_PROJECT_DIR")


class TempHome(unittest.TestCase):
    """Base class that runs every test against a fresh temporary ATHOS_HOME (available as `self.home`), with the
    other agents' folders redirected under it too. Whatever the environment held before is put back afterwards."""

    def setUp(self):
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = self._home_dir.name
        self._saved_env = {name: os.environ.get(name) for name in (*_SANDBOXED_ENV, "ATHOS_SPAWN", "ATHOS_UI",
                                                                   *_OUTER_SESSION)}
        # A test runs as no agent's command unless it says so: the variables an agent session sets in its shell
        # (when the suite itself runs inside one) would make every `athos save` a model's.
        for name in _OUTER_SESSION:
            os.environ.pop(name, None)
        for name, sub in _SANDBOXED_ENV.items():
            os.environ[name] = self.home if sub is None else os.path.join(self.home, sub)
        # The interface the person gets is the default one (minimal) unless a test asks for the classic one.
        os.environ.pop("ATHOS_UI", None)
        # No test may start a real background model run (the independent verifier, a replay): spawning is off, and
        # a test that checks a spawn passes its own stub.
        os.environ["ATHOS_SPAWN"] = "off"

    def classic(self):
        """The classic interface (ATHOS_UI=classic) for the rest of this test, child processes included: the band,
        the toasts and the lines the person reads that the minimal interface keeps out of sight."""
        os.environ["ATHOS_UI"] = "classic"

    def tearDown(self):
        for name, before in self._saved_env.items():
            if before is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = before
        self._home_dir.cleanup()
