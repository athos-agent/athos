"""State files several processes write at once (sessions, pieces, the profile, the selection, the config): written in
one step, updated under a lock, and never read as empty when they cannot be read. All data here is synthetic."""

import json
import os
import subprocess
import sys
from pathlib import Path

from athos import control, paths, session, start, store
from tests.helpers import TempHome

ROOT = str(Path(__file__).resolve().parents[1])


def run_all(code: str, n: int) -> None:
    """`n` Python processes running `code` at once (each gets its number as argv[1])."""
    procs = [subprocess.Popen([sys.executable, "-c", code, str(i)], cwd=ROOT, env=dict(os.environ),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(n)]
    for p in procs:
        out, err = p.communicate(timeout=120)
        if p.returncode:
            raise AssertionError(err.decode(errors="ignore")[-2000:])


class ConcurrentTest(TempHome):
    def test_several_processes_updating_one_session_lose_nothing(self):
        session.update("shared", start=True)
        run_all("import sys\nfrom athos import session\nn = sys.argv[1]\n"
                "for j in range(40):\n    session.update('shared', **{f'k{n}_{j}': j})\n", 6)
        state = json.loads(paths.sessions().joinpath("shared.json").read_text())
        missing = [f"k{n}_{j}" for n in range(6) for j in range(40) if f"k{n}_{j}" not in state]
        self.assertEqual(missing, [])
        self.assertTrue(state["start"])

    def test_a_piece_is_never_read_half_written(self):
        big = "## #a\n**When:** at a.\n**Do:** " + "the long thing " * 6000 + "\n"
        store._write(store.Piece(id="big", title="Big page", when="big work", body=big, projects=["alpha"],
                                 created="2026-11-01", last_used="2026-11-01", origin={"platform": "t", "model": "t"},
                                 status="candidate", confidence="0.50"))
        writer = ("import sys\nfrom athos import store\n"
                  "for j in range(150):\n    store.set_meta('big', confidence=f'0.{10 + j % 80:02d}')\n")
        reader = ("import sys\nfrom pathlib import Path\nfrom athos import store, paths\nbad = 0\n"
                  "for j in range(600):\n"
                  "    text = (paths.know_how() / 'big.md').read_text()\n"
                  "    p = store.parse(text)\n"
                  "    bad += p.id != 'big' or 'the long thing' not in p.body\n"
                  "sys.exit(1 if bad else 0)\n")
        procs = [subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=dict(os.environ),
                                  stderr=subprocess.PIPE) for code in (writer, writer, reader, reader)]
        codes = [p.wait(timeout=120) for p in procs]
        self.assertEqual(codes, [0, 0, 0, 0])


class UnreadableTest(TempHome):
    """A state file that cannot be read is an error, never an empty state written back over it."""

    def test_a_damaged_session_is_not_overwritten(self):
        f = paths.sessions() / "s1.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('{"model": "claude-opus-5-5", "saved": ["a"')
        with self.assertRaises(paths.StateUnreadable):
            session.update("s1", tools_since_capture=1)
        self.assertEqual(f.read_text(), '{"model": "claude-opus-5-5", "saved": ["a"')

    def test_a_damaged_profile_is_not_overwritten(self):
        store._write(store.Piece(id="g1", title="G", when="g", body="b", created="2026-11-01",
                                 last_used="2026-11-01", origin={}))
        paths.profile_file().parent.mkdir(parents=True, exist_ok=True)
        paths.profile_file().write_text('{"pieces": ["x", "y"')
        with self.assertRaises(ValueError):
            control.profile_add(["g1"])
        self.assertEqual(paths.profile_file().read_text(), '{"pieces": ["x", "y"')

    def test_a_damaged_config_is_not_overwritten(self):
        start.config_file().parent.mkdir(parents=True, exist_ok=True)
        start.config_file().write_text('{"lang": "es", "autolearn": {')
        start.note_language("que de la el en los las por para con una como esta")      # a hook: must not raise
        self.assertEqual(start.config_file().read_text(), '{"lang": "es", "autolearn": {')

    def test_writes_leave_no_temporary_files(self):
        session.update("s2", a=1)
        control.set_selection("all")
        self.assertEqual(sorted(f.name for f in paths.sessions().iterdir() if f.name.endswith(".tmp")), [])
        self.assertEqual(json.loads(paths.selection_file().read_text()), {"mode": "all"})

    def test_the_status_reads_a_damaged_session_without_writing_it(self):
        import contextlib
        import io
        from athos import cli
        cli._remember_session({"cwd": self.home, "session_id": "s3"})
        f = paths.sessions() / "s3.json"
        f.write_text("{not json")
        out = io.StringIO()
        with contextlib.chdir(self.home), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["status", "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["loaded"], [])
        self.assertEqual(f.read_text(), "{not json")
