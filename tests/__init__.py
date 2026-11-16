"""The tests run in a folder of their own, not in the checkout.

Many of them call the command line without naming a folder, and Athos reads the marker (`.athos.toml`) of the folder
it runs in: a checkout marked public would make those tests run under the public-repository rule. A test that needs
a particular folder changes into it itself.
"""

import atexit
import os
import shutil
import tempfile

_folder = tempfile.mkdtemp(prefix="athos-tests-")
os.chdir(_folder)
atexit.register(shutil.rmtree, _folder, ignore_errors=True)
