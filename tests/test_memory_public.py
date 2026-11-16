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
