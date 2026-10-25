import os
import tempfile
import unittest


class TempHome(unittest.TestCase):
    """Each test gets its own ATHOS_HOME, so nothing touches the real store."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ATHOS_HOME")
        os.environ["ATHOS_HOME"] = self._tmp.name
        self.home = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ATHOS_HOME", None)
        else:
            os.environ["ATHOS_HOME"] = self._old
        self._tmp.cleanup()
