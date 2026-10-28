import os
import tempfile
import unittest


class TempHome(unittest.TestCase):
    """Each test gets its own ATHOS_HOME, so nothing touches the real store."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ATHOS_HOME")
        self._old_codex = os.environ.get("CODEX_HOME")
        self._old_xdg = os.environ.get("XDG_DATA_HOME")
        self._old_skills = os.environ.get("ATHOS_SKILLS_DIR")
        os.environ["ATHOS_HOME"] = self._tmp.name
        os.environ["CODEX_HOME"] = os.path.join(self._tmp.name, "codex-home")      # never the user's real ~/.codex
        os.environ["XDG_DATA_HOME"] = os.path.join(self._tmp.name, "xdg-data")     # nor their Muse Code sessions
        os.environ["ATHOS_SKILLS_DIR"] = os.path.join(self._tmp.name, "agents-skills")  # nor their exported skills
        self.home = self._tmp.name

    def tearDown(self):
        for key, old in (("ATHOS_HOME", self._old), ("CODEX_HOME", self._old_codex), ("XDG_DATA_HOME", self._old_xdg),
                         ("ATHOS_SKILLS_DIR", self._old_skills)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        self._tmp.cleanup()
