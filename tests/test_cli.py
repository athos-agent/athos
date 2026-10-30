import unittest
import shlex
import json
import os
import subprocess
import sys
from pathlib import Path

from athos import store
from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")


class CliTest(TempHome):
    def run_athos(self, *args, stdin="", cwd=None, env=None):
        # Headless by default (like `claude -p`): the hooks then ask the model, as an interactive session would offer.
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=cwd or self.home,
                              env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli", **(env or {})})

    def hook(self, event, payload):
        r = self.run_athos("hook", event, stdin=json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_the_whole_cycle_through_the_hooks(self):
        ev = {"session_id": "s1", "cwd": self.home, "transcript_path": None}
        self.assertIsNone(self.hook("session-start", {**ev, "model": "claude-opus-5-5"}))     # empty store: silent
        for _ in range(5):
            self.hook("tool", ev)
        stop = self.hook("stop", ev)                                  # Claude Code: feedback, not a "hook error"
        self.assertIn("athos save", stop["hookSpecificOutput"]["additionalContext"])
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

    def test_an_interactive_claude_code_session_offers_a_button_instead(self):
        ev = {"session_id": "i1", "cwd": self.home, "transcript_path": None}
        r = self.run_athos("hook", "prompt", stdin=json.dumps({**ev, "prompt": "release it"}),
                           env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(r.returncode, 0, r.stderr)
        for _ in range(5):
            self.run_athos("hook", "tool", stdin=json.dumps({**ev, "tool_name": "Edit"}),
                           env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        r = self.run_athos("hook", "stop", stdin=json.dumps(ev), env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(r.stdout.strip(), "")                          # nothing for the model to read
        from athos import session as sess
        self.assertEqual(sess.load("i1")["offer"]["reason"], "work")

    def test_the_save_button_request_gets_the_instruction_out_of_sight_and_starts_no_task(self):
        from athos import capture, eval as ev
        out = self.hook("prompt", {"session_id": "b1", "cwd": self.home, "prompt": capture.SAVE_PROMPT["en"]})
        self.assertIn("athos save", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual([e for e in ev.events() if e["type"] == "task_start"], [])

    def test_codex_still_gets_a_stop_block(self):
        ev = {"session_id": "s1", "cwd": self.home, "transcript_path": None}
        for _ in range(5):
            self.hook("tool", ev)
        r = self.run_athos("hook", "stop", "--platform", "codex", stdin=json.dumps(ev))
        self.assertEqual(json.loads(r.stdout)["decision"], "block")

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


class StartTest(TempHome):
    """A first run for people who don't program: language, profession, example ways of working."""

    def run_cli(self, args):
        r = subprocess.run([sys.executable, ATHOS, *args], capture_output=True, text=True, cwd=self.home,
                           env=dict(os.environ), stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_bare_athos_greets_instead_of_failing(self):
        out = self.run_cli([])
        self.assertIn("athos start", out)

    def test_start_installs_the_profession_examples_in_the_chosen_language(self):
        from athos import start
        out = self.run_cli(["start", "--lang", "es", "--profile", "law"])
        self.assertIn("Agregué 2 formas de trabajar", out)
        self.assertIn("pestaña Code", out)
        self.assertEqual(start.lang(), "es")
        ids = {p.id for p in store.all_pieces()}
        self.assertIn("revisar-un-contrato-con-tu-checklist", ids)
        self.assertEqual(start.config()["profile"], "law")
        again = self.run_cli(["start", "--lang", "es", "--profile", "law"])        # never overwrites the person's
        self.assertIn("ya estaban", again)

    def test_every_starter_is_a_clean_wiki_page_that_leaves_decisions_to_the_person(self):
        from athos import start, wiki
        for lang in start.LANGS:
            for prof in ("law", "sports"):
                files = start.starters(lang, prof)
                self.assertGreaterEqual(len(files), 2, (lang, prof))
                for f in files:
                    meta, body = store.parse_frontmatter(f.read_text())
                    self.assertTrue(meta.get("id") and meta.get("title") and meta.get("when"), f)
                    self.assertIn("## #", body)
        for lang in start.LANGS:
            for prof in ("law", "sports"):
                start.install(lang, prof)
        lint = wiki.lint()
        self.assertEqual((lint["broken"], lint["duplicate_ids"], lint["old_format"]), ([], [], []))

    def test_a_spanish_request_loads_its_piece_alone(self):
        from athos import load, start
        start.install("es", "law")
        start.install("es", "sports")
        got = [p.id for p in load.relevant("planificá la semana de entrenamiento de este atleta", store.all_pieces())]
        self.assertEqual(got, ["planificar-la-semana-de-entrenamiento"])


class CommandNameTest(TempHome):
    def test_lines_say_plain_athos_when_the_shell_finds_it(self):
        from unittest import mock
        from athos import cli
        with mock.patch("shutil.which", return_value=str(cli.ME)):
            self.assertEqual(cli._cmd(), "athos")
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(cli._cmd(), shlex.quote(str(cli.ME)))
        # A launcher pointing at this installation counts; another (older) installation on PATH doesn't.
        mine, other = Path(self.home) / "mine", Path(self.home) / "other"
        mine.write_text(f'#!/bin/sh\nexec python3 "{cli.ME}" "$@"\n')
        other.write_text('#!/bin/sh\nexec python3 "/elsewhere/.athos/app/bin/athos" "$@"\n')
        with mock.patch("shutil.which", return_value=str(mine)):
            self.assertEqual(cli._cmd(), "athos")
        with mock.patch("shutil.which", return_value=str(other)):
            self.assertEqual(cli._cmd(), shlex.quote(str(cli.ME)))           # no version: can't tell it has `step`
        # An installation one version behind, with `athos step`, is fine: no full path with the user name.
        app = Path(self.home) / "app"
        (app / ".claude-plugin").mkdir(parents=True)
        (app / ".claude-plugin" / "plugin.json").write_text('{"version": "0.1.50"}')
        behind = Path(self.home) / "behind"
        behind.write_text(f'#!/bin/sh\nexec python3 "{app}/bin/athos" "$@"\n')
        with mock.patch("shutil.which", return_value=str(behind)):
            self.assertEqual(cli._cmd(), "athos")
        (app / ".claude-plugin" / "plugin.json").write_text('{"version": "0.1.40"}')
        with mock.patch("shutil.which", return_value=str(behind)):
            self.assertEqual(cli._cmd(), shlex.quote(str(cli.ME)))           # older than `step`
