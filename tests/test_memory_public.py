"""In a repository marked public, no memory command prints anything of another project or names a piece that may not
be named there, whatever a stored page says; and the model pass never sees a private piece. All data here is
synthetic."""

import contextlib
import io
import json

from athos import cli, memory, paths, store
from athos.memory import cycle
from tests.test_memory_cycle import MemoryCase, stamp, task, write

HUSH_TITLE = "Hush the quiet ledger"


class PublicMemoryTest(MemoryCase):
    def setUp(self):
        super().setUp()
        store._write(store.Piece(id="hush", title=HUSH_TITLE, when="the quiet ledger", body="## #one\n**Do:** it.\n",
                                 projects=["beta"], visibility="private", created="2026-11-01",
                                 last_used="2026-11-01", origin={"platform": "test", "model": "test"}))
        store._write(store.Piece(id="general-habit", title="A general habit", when="always", body="## #one\n",
                                 projects=[], created="2026-11-01", last_used="2026-11-01",
                                 origin={"platform": "test", "model": "test"}))
        # beta worked in a public repository long ago: its route events are archived by the first cycle.
        old = [{"type": "route", "request_kind": "person", "project": "beta", "public": True, "chosen": [],
                "delivery": None, "at": stamp(44)}]
        old += task("b-old", 44, project="beta", pieces=("hush", "general-habit", "report"), result="ok")
        log = paths.events_file()
        log.write_text("".join(json.dumps(r) + "\n" for r in old) + log.read_text())
        write([{"type": "route", "request_kind": "person", "project": "gamma", "chosen": [], "delivery": None,
                "request_sha": "bbbbbbbbbbbb", "at": stamp(2)}])

    def run_in(self, folder, *argv):
        out = io.StringIO()
        with contextlib.chdir(folder), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_a_public_projects_page_names_only_what_may_be_named_there(self):
        cycle.run()
        (self.beta / paths.MARKER).write_text('name = "beta"\npublic = true\n')
        code, text = self.run_in(self.beta, "memory", "project")
        self.assertEqual(code, 0)
        self.assertIn("# Working in beta", text)
        self.assertNotIn(HUSH_TITLE, text)
        self.assertNotIn("hush", text)
        self.assertNotIn("general-habit", text)
        self.assertIn("`report`", text)
        # The page on disk is not trusted either: one that names them is filtered at read time.
        page = memory.projects_dir() / "beta.md"
        page.write_text(page.read_text() + f"\n- `hush` — {HUSH_TITLE}\n- `ship` from alpha\n")
        _code, text = self.run_in(self.beta, "memory", "project")
        self.assertNotIn(HUSH_TITLE, text)
        self.assertNotIn("`ship`", text)

    def test_the_stored_page_of_a_public_project_already_hides_them(self):
        cycle.run()
        text = (memory.projects_dir() / "beta.md").read_text()
        self.assertNotIn(HUSH_TITLE, text)               # beta's public flag survives its route events' archiving
        self.assertNotIn("general-habit", text)

    def test_findings_in_a_public_repository_keep_to_this_project(self):
        cycle.run()
        (self.alpha / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        code, text = self.run_in(self.alpha, "memory", "findings")
        self.assertEqual(code, 0)
        found = json.loads(text)
        self.assertEqual({r["project"] for r in found["no_piece"]}, {"alpha"})
        self.assertNotIn("gamma", text)
        self.assertNotIn("beta", text)
        self.assertNotIn("report", text)


class EveryMemoryCommandTest(PublicMemoryTest):
    """Every output of every `athos memory` command and of `athos dream --cycle`, text and JSON, in a repository
    marked public: neither another project nor a piece that may not be named there appears, even when the model pass
    (a stub, no model is called) worked on another project."""

    COMMANDS = [["memory"], ["memory", "--json"], ["memory", "cycle"], ["memory", "cycle", "--json"],
                ["memory", "cycle", "--model"], ["memory", "cycle", "--model", "--json"], ["memory", "check"],
                ["memory", "check", "--json"], ["memory", "rebuild"], ["memory", "rebuild", "--json"],
                ["memory", "findings"], ["memory", "project"], ["memory", "project", "beta"], ["dream", "--cycle"],
                ["dream", "--cycle", "--json"]]

    def test_no_command_names_another_project_or_a_hidden_piece(self):
        from unittest import mock
        from athos import verify
        from athos.memory import dream_model

        def runner(prompt, folder, model, timeout, cap):
            return {"ok": True, "cost_usd": 0.01, "text": json.dumps(
                {"project_page": "beta works with hush", "merge": [], "rules": [
                    {"piece": "report", "kind": "avoid", "text": "skip it"}]})}
        cycle.run()
        (self.alpha / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        seen = []
        with mock.patch.object(dream_model, "_sessions_idle", return_value=True), \
                mock.patch.object(dream_model, "_choose_project", return_value="beta"), \
                mock.patch.object(verify, "claude_runner", side_effect=runner), \
                mock.patch.object(verify, "reserve", return_value=(True, "", 0.5, "r1")), \
                mock.patch.object(verify, "settle"), mock.patch.object(verify, "note_run"):
            for argv in self.COMMANDS:
                _code, text = self.run_in(self.alpha, *argv)
                seen.append(argv)
                for name in ("beta", "hush", HUSH_TITLE, "report", "gamma"):
                    self.assertNotIn(name, text, f"{' '.join(argv)} printed {name}")
        self.assertEqual(len(seen), len(self.COMMANDS))
