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


def git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True)


def commit_all(root):
    git("-C", str(root), "add", "-A")
    git("-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "x",
        "--allow-empty")


class FindTest(TempHome):
    """The marker is found from any folder of the repository, and fails closed: a marker Athos can find says public
    even where git cannot help (no git, a worktree, a nested repository)."""

    def setUp(self):
        super().setUp()
        self.root = Path(self.home) / "alpha"
        (self.root / "src" / "deep").mkdir(parents=True)
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = true\n')

    def test_a_subfolder_without_git_finds_the_marker_above(self):
        deep = self.root / "src" / "deep"                       # no repository at all
        self.assertTrue(paths.is_public(deep))
        self.assertEqual(paths.project_of(deep), "alpha")

    def test_a_subfolder_finds_it_when_git_cannot_run(self):
        git("init", "-q", str(self.root))
        deep = self.root / "src" / "deep"
        with mock.patch.object(paths.subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertTrue(paths.is_public(deep))
            self.assertEqual(paths.project_of(deep), "alpha")
        with mock.patch.object(paths.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 5)):
            self.assertTrue(paths.is_public(deep))

    def test_a_worktree_falls_back_to_the_main_worktrees_marker(self):
        git("init", "-q", str(self.root))
        (self.root / ".git" / "info").mkdir(exist_ok=True)
        (self.root / ".git" / "info" / "exclude").write_text(paths.MARKER + "\n")   # untracked, as people keep it
        commit_all(self.root)
        wt = Path(self.home) / "elsewhere" / "feature"
        git("-C", str(self.root), "worktree", "add", "-q", str(wt))
        self.assertFalse((wt / paths.MARKER).exists())
        self.assertTrue(paths.is_public(wt))
        self.assertTrue(paths.is_public(wt / "src"))
        self.assertEqual(paths.project_of(wt), "alpha")
        with mock.patch.object(paths.subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertTrue(paths.is_public(wt / "src"))         # read from the worktree's .git file

    def test_a_nested_repository_inside_a_public_one_is_public(self):
        git("init", "-q", str(self.root))
        inner = self.root / "vendor" / "lib"
        inner.mkdir(parents=True)
        git("init", "-q", str(inner))
        self.assertTrue(paths.is_public(inner))
        self.assertEqual(paths.project_of(inner), "lib")          # its own name: the outer marker is not its own

    def test_a_marker_that_cannot_be_read_is_public(self):
        (self.root / paths.MARKER).write_text("this is = not toml [\n")
        mark = paths.marker(self.root)
        self.assertTrue(mark.get("public"))
        self.assertTrue(mark.get("unreadable"))
        self.assertEqual(paths.project_of(self.root), "alpha")
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = "true"\n')    # a string, not a boolean
        self.assertTrue(paths.is_public(self.root))
        with without_tomllib():
            (self.root / paths.MARKER).write_text("public = yes\n")
            self.assertTrue(paths.is_public(self.root))
        (self.root / paths.MARKER).write_bytes(b"\xff\xfe\x00broken")
        self.assertTrue(paths.is_public(self.root))


class NameTest(TempHome):
    """A marker's `name` comes from whoever wrote the repository: it is honoured only when it is the folder's own
    name, or once the person accepted it for that folder on this machine. `public = true` always holds."""

    def setUp(self):
        super().setUp()
        self.root = Path(self.home) / "cloned"
        self.root.mkdir()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def test_a_name_other_than_the_folders_is_ignored_until_the_person_accepts_it(self):
        (self.root / paths.MARKER).write_text('name = "secret-project"\n')
        self.assertEqual(paths.project_of(self.root), "cloned")
        self.assertEqual(paths.marker(self.root).get("name_ignored"), "secret-project")
        code, out = self.run_cli("public", "status")
        self.assertIn("secret-project", out)
        self.assertIn("public name", out)
        code, out = self.run_cli("public", "name")
        self.assertEqual(code, 0)
        self.assertEqual(paths.project_of(self.root), "secret-project")
        self.assertFalse(list(self.root.glob("*acknowledged*")))            # kept under the Athos home only
        (self.root / paths.MARKER).write_text('name = "another"\n')         # changed again: asked again
        self.assertEqual(paths.project_of(self.root), "cloned")

    def test_public_holds_whatever_the_name(self):
        (self.root / paths.MARKER).write_text('name = "secret-project"\npublic = true\n')
        self.assertTrue(paths.is_public(self.root))
        self.assertEqual(paths.project_of(self.root), "cloned")

    def test_the_folders_own_name_needs_no_acceptance(self):
        (self.root / paths.MARKER).write_text('name = "cloned"\n')
        self.assertEqual(paths.project_of(self.root), "cloned")
        self.assertNotIn("name_ignored", paths.marker(self.root))

    def test_the_audit_says_when_a_name_is_ignored(self):
        from athos import audit
        (self.root / paths.MARKER).write_text('name = "secret-project"\n')
        evs = [{"type": "route", "session_id": "n1", "task_id": "t1", "project": "cloned", "chosen": []}]
        r = next(r for r in audit.check("n1", evs, [], cwd=str(self.root))["rules"]
                 if r["rule"] == "marker_name_ignored")
        self.assertEqual(r["status"], "flagged")
        self.assertIn("public name", r["found"][0]["fix"])


class DeclareWritesTest(TempHome):
    """`athos public` reports success only when the marker it wrote reads back as it said."""

    def setUp(self):
        super().setUp()
        self.root = Path(self.home) / "alpha"
        self.root.mkdir()
        git("init", "-q", str(self.root))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_keys_go_before_the_first_table(self):
        (self.root / paths.MARKER).write_text('name = "alpha"\n\n[tool]\nkey = 1\n')
        code, out, err = self.run_cli("public")
        self.assertEqual(code, 0, err)
        self.assertIs(paths.marker(self.root).get("public"), True)
        text = (self.root / paths.MARKER).read_text()
        self.assertLess(text.index("public = true"), text.index("[tool]"))
        self.assertIn("key = 1", text)
        code, out, err = self.run_cli("public", "off")
        self.assertEqual(code, 0, err)
        self.assertIs(paths.marker(self.root).get("public"), False)

    def test_a_public_inside_a_table_is_not_the_markers(self):
        (self.root / paths.MARKER).write_text('[tool]\npublic = false\n')
        code, out, err = self.run_cli("public")
        self.assertEqual(code, 0, err)
        self.assertIs(paths.marker(self.root).get("public"), True)
        self.assertIn("[tool]\npublic = false", (self.root / paths.MARKER).read_text())

    def test_a_string_is_replaced_by_a_boolean(self):
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = "true"\n')
        code, out, err = self.run_cli("public")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.root / paths.MARKER).read_text(), 'name = "alpha"\npublic = true\n')
        self.assertNotIn("unreadable", paths.marker(self.root))

    def test_a_marker_that_cannot_be_read_is_left_alone_and_said_to_be_public(self):
        broken = "this is = not toml [\n"
        (self.root / paths.MARKER).write_text(broken)
        for action in ([], ["off"]):
            code, out, err = self.run_cli("public", *action)
            self.assertEqual(code, 1)
            self.assertIn("cannot be read", err)
            self.assertIn("treats this repository as public", err)
            self.assertEqual((self.root / paths.MARKER).read_text(), broken)
        code, out, err = self.run_cli("public", "status")
        self.assertIn("cannot be read", out)

    def test_it_fails_loudly_when_the_file_does_not_read_back(self):
        with mock.patch.object(paths, "_loads_marker", return_value={}):
            code, out, err = self.run_cli("public")
        self.assertEqual(code, 1)
        self.assertIn("did not take effect", err)
        self.assertEqual(out, "")


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
