"""The `athos` command run as the agents run it: a separate process, with the event JSON on stdin for the hooks."""

import json
import os
import shlex
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from athos import store
from tests.helpers import TempHome

LAUNCHER = Path(__file__).resolve().parent.parent / "bin" / "athos"
TAGGING = "---\ntitle: Tag a release\nwhen: tagging a release of the package\n---\nRun `git tag` with the version."


class ThroughTheLauncher(TempHome):
    """Runs bin/athos in a child process inside the test's store. Headless by default (CLAUDE_CODE_ENTRYPOINT=sdk-cli,
    as under `claude -p`), where the stop hook asks the model instead of offering the [Save] button."""

    def run_athos(self, *args, stdin="", cwd=None, env=None):
        child_env = dict(os.environ, CLAUDE_CODE_ENTRYPOINT="sdk-cli")
        child_env.update(env or {})
        return subprocess.run([sys.executable, str(LAUNCHER), *args], input=stdin, text=True, capture_output=True,
                              cwd=cwd or self.home, env=child_env)

    def send(self, event, payload):
        """Send one hook event; give back the JSON it answered with, or None when it stayed silent."""
        done = self.run_athos("hook", event, stdin=json.dumps(payload))
        self.assertEqual(done.returncode, 0, done.stderr)
        answer = done.stdout.strip()
        return json.loads(answer) if answer else None

    @staticmethod
    def context(answer):
        return answer["hookSpecificOutput"]["additionalContext"]


class CliTest(ThroughTheLauncher):
    def test_a_session_saves_know_how_and_the_next_one_gets_it(self):
        first = {"session_id": "s1", "cwd": self.home, "transcript_path": None}
        # Nothing stored yet: the session opens with the saving guide only, so the first task can draft its steps.
        opening = self.context(self.send("session-start", dict(first, model="claude-opus-5-5")))
        self.assertIn("step --new", opening)
        self.assertNotIn("know-how are available", opening)
        self.assertIn("Saving know-how", opening)
        for tool in ["Edit"] * 5:                                   # enough work for the stop hook to ask for a save
            self.send("tool", dict(first, tool_name=tool))
        # Claude Code shows the request to save as feedback for the model, not as a "hook error".
        self.assertIn("athos save", self.context(self.send("stop", first)))
        # The model saves from the session's folder; the page records the model that wrote it.
        saved = self.run_athos("save", stdin="---\ntitle: Bump a version\nwhen: releasing a new version of a "
                                             "package\n---\nEdit pyproject.")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertIn("saved bump-a-version", saved.stdout)
        page = Path(self.home, "know-how", "bump-a-version.md").read_text()
        self.assertIn("model: claude-opus-5-5", page)
        # The next session is told the piece exists, and a matching request brings in its text.
        second = {"session_id": "s2", "cwd": self.home}
        self.assertIn("bump-a-version", self.context(self.send("session-start", second)))
        prompt = self.send("prompt", dict(second, prompt="release a new version please"))
        self.assertIn("Edit pyproject.", self.context(prompt))

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
        out = self.send("prompt", {"session_id": "b1", "cwd": self.home, "prompt": capture.SAVE_PROMPT["en"]})
        self.assertIn("athos save", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual([e for e in ev.events() if e["type"] == "task_start"], [])

    def test_codex_still_gets_a_stop_block(self):
        ev = {"session_id": "s1", "cwd": self.home, "transcript_path": None}
        for _ in range(5):
            self.send("tool", ev)
        r = self.run_athos("hook", "stop", "--platform", "codex", stdin=json.dumps(ev))
        self.assertEqual(json.loads(r.stdout)["decision"], "block")

    def test_unreadable_event_json_leaves_stdout_empty_and_exits_zero(self):
        done = self.run_athos("hook", "prompt", stdin="{ this is not an event")
        self.assertEqual((done.returncode, done.stdout), (0, ""))
        self.assertIn("athos hook prompt:", done.stderr)              # the reason goes to stderr only

    def test_list_show_load_and_export(self):
        self.run_athos("save", stdin=TAGGING)
        listing = self.run_athos("list").stdout
        self.assertIn("1 piece(s)", listing)
        self.assertIn("tag-a-release  v1  Tag a release", listing)
        self.assertIn("Run `git tag`", self.run_athos("show", "tag-a-release").stdout)
        self.assertEqual(self.run_athos("show", "missing").returncode, 1)
        chosen = self.run_athos("load", "pieces", "tag-a-release")
        self.assertIn("pieces tag-a-release", chosen.stdout)
        self.assertIn("loading: pieces tag-a-release", self.run_athos("load").stdout)   # bare: the current choice
        self.assertEqual(self.run_athos("load", "pieces", "no-such-piece").returncode, 1)
        folder = Path(self.home, "exported")
        self.assertIn("exported 1", self.run_athos("export", str(folder)).stdout)
        self.assertTrue(Path(folder, "tag-a-release.md").is_file())
        self.assertEqual(self.run_athos("export").returncode, 1)                # no folder named

    def test_reading_a_piece_during_a_session_counts_as_loading_it(self):
        from athos import session
        self.run_athos("save", stdin=TAGGING)
        self.send("session-start", {"session_id": "reader", "cwd": self.home})
        self.assertEqual(self.run_athos("show", "tag-a-release").returncode, 0)
        self.assertEqual(session.load("reader")["loaded"], ["tag-a-release"])

    def test_status_reports_the_last_task_before_and_after_its_mark(self):
        folder = {"session_id": "s5", "cwd": self.home}

        def snapshot():
            return json.loads(self.run_athos("status", "--json").stdout)

        self.send("session-start", folder)
        self.send("prompt", dict(folder, prompt="release a new version"))
        page = "---\ntitle: Release\nwhen: release a new version\n---\nBump the version, then tag it."
        self.assertEqual(self.run_athos("save", stdin=page).returncode, 0)
        self.send("stop", folder)
        before = snapshot()
        self.assertEqual((before["pieces"], before["to_mark"]), (1, 1))
        self.assertEqual((before["last"]["saved"], before["last"]["improved"]), (["release"], []))
        self.assertEqual(before["last"]["result"], "unevaluated")
        self.assertIn("task", self.run_athos("mark", "g").stdout)
        after = snapshot()
        self.assertEqual((after["to_mark"], after["last"]["result"]), (0, "ok"))
        self.assertIn("1 ways of working", self.run_athos("status").stdout)

    def test_a_save_into_a_read_only_store_says_how_to_allow_it(self):
        os.chmod(self.home, stat.S_IRUSR | stat.S_IXUSR)            # the store as Codex's sandbox sees it
        try:
            refused = self.run_athos("save", stdin=TAGGING, cwd="/")
        finally:
            os.chmod(self.home, stat.S_IRWXU)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("writable_roots", refused.stderr)          # how to let Codex's sandbox write the store
        self.assertNotIn("Traceback", refused.stderr)


class StartTest(TempHome):
    """A first run for people who don't program: language, profession, example ways of working."""

    def run_cli(self, args):
        r = subprocess.run([sys.executable, str(LAUNCHER), *args], capture_output=True, text=True, cwd=self.home,
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
            for prof in ("law", "finance"):
                files = start.starters(lang, prof)
                self.assertGreaterEqual(len(files), 2, (lang, prof))
                for f in files:
                    meta, body = store.parse_frontmatter(f.read_text())
                    self.assertTrue(meta.get("id") and meta.get("title") and meta.get("when"), f)
                    self.assertIn("## #", body)
        for lang in start.LANGS:
            for prof in ("law", "finance"):
                start.install(lang, prof)
        lint = wiki.lint()
        self.assertEqual((lint["broken"], lint["duplicate_ids"], lint["old_format"]), ([], [], []))

    def test_a_spanish_request_loads_its_piece_alone(self):
        from athos import load, start
        start.install("es", "law")
        start.install("es", "journalism")
        got = [p.id for p in load.relevant("verificá esta pista antes de publicarla", store.all_pieces())]
        self.assertEqual(got, ["verificar-una-pista-antes-de-publicar"])


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
        # An installation whose `athos step` works in a sandbox (0.1.75+) is fine: no full path with the user name.
        app = Path(self.home) / "app"
        (app / ".claude-plugin").mkdir(parents=True)
        (app / ".claude-plugin" / "plugin.json").write_text('{"version": "0.1.75"}')
        behind = Path(self.home) / "behind"
        behind.write_text(f'#!/bin/sh\nexec python3 "{app}/bin/athos" "$@"\n')
        with mock.patch("shutil.which", return_value=str(behind)):
            self.assertEqual(cli._cmd(), "athos")
        (app / ".claude-plugin" / "plugin.json").write_text('{"version": "0.1.60"}')
        with mock.patch("shutil.which", return_value=str(behind)):
            self.assertEqual(cli._cmd(), shlex.quote(str(cli.ME)))           # its step fails in a sandbox
