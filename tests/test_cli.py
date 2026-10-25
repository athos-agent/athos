import json
import os
import subprocess
import sys
from pathlib import Path

from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")


class CliTest(TempHome):
    def run_athos(self, *args, stdin="", cwd=None):
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=cwd or self.home, env=dict(os.environ))

    def hook(self, event, payload):
        r = self.run_athos("hook", event, stdin=json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_the_whole_cycle_through_the_hooks(self):
        ev = {"session_id": "s1", "cwd": self.home, "transcript_path": None}
        self.assertIsNone(self.hook("session-start", {**ev, "model": "claude-opus-5-5"}))     # empty store: silent
        for _ in range(5):
            self.hook("tool", ev)
        stop = self.hook("stop", ev)
        self.assertEqual(stop["decision"], "block")
        piece = "---\ntitle: Bump a version\nwhen: releasing a new version of a package\n---\nEdit pyproject."
        r = self.run_athos("save", stdin=piece)                       # what Claude runs, from the session's cwd
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("saved bump-a-version", r.stdout)
        saved = (Path(self.home) / "know-how" / "bump-a-version.md").read_text()
        self.assertIn("model: claude-opus-5-5", saved)
        start = self.hook("session-start", {"session_id": "s2", "cwd": self.home})
        self.assertIn("bump-a-version", start["hookSpecificOutput"]["additionalContext"])
        ctx = self.hook("prompt", {"session_id": "s2", "cwd": self.home, "prompt": "release a new version please"})
        self.assertIn("Edit pyproject.", ctx["hookSpecificOutput"]["additionalContext"])

    def test_a_broken_event_never_breaks_the_session(self):
        r = self.run_athos("hook", "prompt", stdin="not json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    def test_commands(self):
        self.run_athos("save", stdin="---\ntitle: A\nwhen: aaa bbb\n---\nbody")
        self.assertIn("1 piece(s)", self.run_athos("list").stdout)
        self.assertIn("title: A", self.run_athos("show", "a").stdout)
        self.assertIn("pieces a", self.run_athos("load", "pieces", "a").stdout)
        self.assertEqual(self.run_athos("load", "pieces", "zzz").returncode, 1)
        out = Path(self.home) / "exported"
        self.assertIn("exported 1", self.run_athos("export", str(out)).stdout)
        self.assertTrue((out / "a.md").is_file())

    def test_show_inside_a_session_marks_the_piece_loaded(self):
        self.run_athos("save", stdin="---\ntitle: A\nwhen: aaa bbb\n---\nbody")
        self.hook("session-start", {"session_id": "s9", "cwd": self.home})
        self.run_athos("show", "a")
        from athos import session
        self.assertEqual(session.load("s9")["loaded"], ["a"])

    def test_status_for_the_terminal(self):
        ev = {"session_id": "s5", "cwd": self.home}
        self.hook("session-start", ev)
        self.hook("prompt", {**ev, "prompt": "release a new version"})
        self.run_athos("save", stdin="---\ntitle: Release\nwhen: release a new version\n---\nBump.")
        self.hook("stop", ev)
        s = json.loads(self.run_athos("status", "--json").stdout)
        self.assertEqual((s["pieces"], s["to_mark"]), (1, 1))
        self.assertEqual(s["last"]["saved"], ["release"])
        self.assertEqual(s["last"]["result"], "unevaluated")
        self.run_athos("mark", "g")
        s = json.loads(self.run_athos("status", "--json").stdout)
        self.assertEqual((s["to_mark"], s["last"]["result"]), (0, "ok"))

    def test_save_explains_a_read_only_store(self):
        os.chmod(self.home, 0o500)
        try:
            r = self.run_athos("save", stdin="---\ntitle: A\nwhen: aaa\n---\nbody", cwd="/")
        finally:
            os.chmod(self.home, 0o700)
        self.assertEqual(r.returncode, 1)
        self.assertIn("writable_roots", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
