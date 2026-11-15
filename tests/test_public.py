"""Privacy in a repository marked public (`.athos.toml` with `public = true`): every piece that is not that project's
is treated as private there (never loaded, never named in an index, log.md or any hook output, even when the request
names its project), and a profile piece only when the person allowed it in public. All data here is synthetic."""

import contextlib
import io
import json
from pathlib import Path

from athos import cli, control, paths, session, store
from tests.test_routing import SECRET, Folders, events, log_text, piece


class PublicRepositoryTest(Folders):
    def setUp(self):
        super().setUp()
        piece("alpha-release", "Ship the alpha release", "shipping the alpha release", ["alpha"])
        piece("beta-report", "Write the beta weekly report", "writing the beta weekly report", ["beta"])
        piece("habit-commits", "Write small commits", "writing small commits for the weekly report", [])
        piece("habit-tests", "Run the tests first", "running the tests before the weekly report", [])
        control.profile_add(["habit-commits", "habit-tests"])
        self.root = Path(self.folder("alpha"))
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        self.e = {"session_id": "pub1", "cwd": str(self.root)}

    def everything_written(self):
        return "".join(f.read_text(errors="ignore") for f in Path(self.home).rglob("*")
                       if f.is_file() and f.suffix in (".md", ".jsonl", ".json") and "know-how" not in f.parts)

    def test_another_projects_piece_never_loads_nor_is_named_even_when_the_request_names_it(self):
        added = self.hook("prompt", {**self.e, "prompt": f"write the beta weekly report {SECRET}"})
        self.assertEqual(added, "")
        (r,) = events("route")
        self.assertEqual((r["chosen"], r["named_projects"], r["named_count"], r["public"]), ([], [], 1, True))
        self.assertGreaterEqual(r["private_held"], 1)
        self.assertNotIn("beta-report", json.dumps(r))
        self.assertNotIn("beta", log_text())
        # The same request in a repository that is not marked public loads it (the request names the project).
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = false\n')
        added = self.hook("prompt", {**self.e, "prompt": "write the beta weekly report"})
        self.assertIn("Write the beta weekly report", added)

    def test_profile_pieces_need_the_persons_leave_to_load_in_public(self):
        self.assertEqual(control.public_ids(), [])
        pool, why = control.select(store.all_pieces(), str(self.root), "")
        self.assertEqual([p.id for p in pool], ["alpha-release"])                # the project's own, nothing else
        control.profile_allow_public(["habit-tests"])
        pool, _ = control.select(store.all_pieces(), str(self.root), "")
        self.assertEqual(sorted(p.id for p in pool), ["alpha-release", "habit-tests"])
        with self.assertRaises(ValueError):
            control.profile_allow_public(["beta-report"])                        # not in the profile
        control.profile_remove(["habit-tests"])                                  # leaving the profile ends the leave
        self.assertEqual(control.public_ids(), [])
        # Outside a public repository the profile loads as before.
        pool, _ = control.select(store.all_pieces(), self.folder("gamma"), "")
        self.assertEqual(sorted(p.id for p in pool), ["habit-commits"])

    def test_session_start_and_the_frontier_index_name_nothing_from_elsewhere(self):
        told = self.hook("session-start", {**self.e, "model": "claude-opus-5-5"})
        self.assertIn("alpha-release", told)
        for other in ("beta-report", "Write the beta weekly report", "habit-commits", "habit-tests"):
            self.assertNotIn(other, told)
        self.assertIn("never loaded here: this repository is marked public", told)
        index = self.hook("prompt", {**self.e, "prompt": "ship the alpha release", "model": "claude-opus-5-5"})
        self.assertIn("`alpha-release`", index)
        self.assertNotIn("habit-", index)
        self.assertNotIn("beta-report", index)

    def test_show_list_and_the_tool_hook_keep_other_projects_out(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["show", "beta-report"]), 1)
            self.assertEqual(cli.main(["show", "alpha-release"]), 0)
            cli.main(["list"])
        self.assertIn("marked public", err.getvalue())
        self.assertNotIn("beta-report", out.getvalue())
        self.assertIn("alpha-release", out.getvalue())
        self.assertIn("3 piece(s) of other projects not listed", out.getvalue())
        self.hook("prompt", {**self.e, "prompt": "unrelated words"})
        self.hook("tool", {**self.e, "tool_name": "Bash", "tool_input": {"command": "athos show beta-report"}})
        self.assertEqual(session.load("pub1").get("task_loaded"), [])
        self.assertEqual(events("piece_opened"), [])
        self.assertNotIn("beta-report", self.everything_written())


class DeclareTest(Folders):
    """`athos public` writes the marker in one step; the audit asks for it when a repository is pushed to a
    code-hosting site and says nothing about its visibility (from the local git configuration only)."""

    def setUp(self):
        super().setUp()
        import subprocess
        self.root = Path(self.folder("gamma"))
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "remote", "add", "origin", "git@github.com:example/demo.git"],
                       check=True)

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def audit_rule(self):
        from athos import audit
        evs = [{"type": "route", "session_id": "d1", "task_id": "t1", "project": "gamma", "chosen": []}]
        return next(r for r in audit.check("d1", evs, [], cwd=str(self.root))["rules"]
                    if r["rule"] == "public_not_declared")

    def test_the_audit_asks_and_one_command_answers(self):
        self.assertEqual(paths.code_remotes(self.root), ["github.com"])
        r = self.audit_rule()
        self.assertEqual((r["status"], r["found"][0]["pushed_to"]), ("flagged", "github.com"))
        code, out = self.run_cli("public", "status")
        self.assertIn("not declared", out)
        self.assertIn("pushed to github.com", out)
        code, out = self.run_cli("public")
        self.assertEqual(code, 0)
        mark = paths.marker(self.root)
        self.assertEqual((mark["name"], mark["public"], Path(mark["file"]).name), ("gamma", True, paths.MARKER))
        self.assertEqual(self.audit_rule()["status"], "clean")
        # The reverse keeps the name and any other line the person wrote.
        (self.root / paths.MARKER).write_text('name = "gamma-app"\n# mine\npublic = true\n')
        self.run_cli("public", "off")
        self.assertEqual((self.root / paths.MARKER).read_text(), 'name = "gamma-app"\n# mine\npublic = false\n')
        self.assertEqual(self.audit_rule()["status"], "clean")    # still gamma: the new name was never accepted
        self.assertFalse(paths.is_public(self.root))
        paths.accept_name(self.root)
        self.assertEqual(self.audit_rule()["status"], "not_evaluated")    # now the project is called gamma-app

    def test_a_repository_with_no_hosted_remote_is_not_asked_about(self):
        import subprocess
        subprocess.run(["git", "-C", str(self.root), "remote", "set-url", "origin", "/srv/git/demo.git"], check=True)
        self.assertEqual(paths.code_remotes(self.root), [])
        self.assertEqual(self.audit_rule()["status"], "clean")


CALLER = ("## #draft\n**When:** drafting the alpha release notes.\n**Do:** write the notes.\n"
          "**Calls:** [[beta-secret]]\n\n## #check\n**When:** after drafting.\n**Do:** read them again.\n"
          "**If:** the notes mention money → [[beta-ledger]]\n")


class HandOverTest(Folders):
    """A hand-over (`**Calls:**` / `**If:**`) brings a page only from the pieces this session may see: never another
    project's private page, never anything of another project in a repository marked public."""

    def setUp(self):
        super().setUp()
        piece("alpha-notes", "Draft the alpha release notes", "drafting the alpha release notes", ["alpha"],
              body=CALLER)
        piece("beta-secret", "Beta secret steps", "the beta secret steps", ["beta"], visibility="private",
              body="## #s\n**When:** at s.\n**Do:** the zebra quartz marmalade.\n")
        piece("beta-ledger", "Beta ledger", "the beta ledger", ["beta"],
              body="## #l\n**When:** at l.\n**Do:** the ledger thing.\n")
        self.root = Path(self.folder("alpha"))

    def written(self):
        return "".join(f.read_text(errors="ignore") for f in Path(self.home).rglob("*")
                       if f.is_file() and "know-how" not in f.parts)

    def test_a_private_page_of_another_project_never_comes_along(self):
        added = self.hook("prompt", {"session_id": "h1", "cwd": str(self.root),
                                     "prompt": "draft the alpha release notes"})
        self.assertIn("Draft the alpha release notes", added)
        self.assertNotIn("zebra quartz", added)
        self.assertNotIn("Beta secret steps", added)
        (r,) = events("route")
        self.assertNotIn("beta-secret", r["handed_over"])
        self.assertNotIn("beta-secret", self.written())

    def test_in_a_public_repository_nothing_of_another_project_comes_along(self):
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        for sid, model in (("h2", None), ("h3", "claude-opus-5-5")):
            payload = {"session_id": sid, "cwd": str(self.root), "prompt": "draft the alpha release notes"}
            if model:
                self.hook("session-start", {"session_id": sid, "cwd": str(self.root), "model": model})
            added = self.hook("prompt", payload)
            self.assertIn("alpha-notes", added)
            # The caller's own body links to them (the person wrote that); their titles and steps never come along.
            for other in ("Beta secret steps", "Beta ledger", "zebra quartz", "the ledger thing", "`beta-"):
                self.assertNotIn(other, added)
        for r in events("route"):
            self.assertEqual(r["handed_over"], [])
            self.assertNotIn("beta-", json.dumps(r["offered"]))
        written = self.written()
        self.assertNotIn("beta-secret", written)
        self.assertNotIn("beta-ledger", written)

    def test_outside_a_public_repository_another_projects_shared_page_still_comes_along_when_named(self):
        added = self.hook("prompt", {"session_id": "h4", "cwd": str(self.root),
                                     "prompt": "draft the alpha release notes for beta"})
        self.assertIn("Beta ledger", added)                # named in the request: in scope, so it may come along


class SaveByIdTest(Folders):
    """`athos save` with the `id:` of a piece that may not be named in a public repository changes nothing and answers
    as for an id that does not exist."""

    def setUp(self):
        super().setUp()
        piece("alpha-release", "Ship the alpha release", "shipping the alpha release", ["alpha"])
        piece("beta-report", "Write the beta weekly report", "writing the beta weekly report", ["beta"])
        self.root = Path(self.folder("alpha"))
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = true\n')

    def save(self, text, *flags):
        import sys
        from unittest import mock
        out = io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), \
                mock.patch.object(sys, "stdin", io.StringIO(text)):
            code = cli.main(["save", *flags])
        return code, out.getvalue()

    def test_another_projects_id_is_refused_like_a_missing_one(self):
        before = store.get("beta-report").path.read_bytes()
        body = "---\nid: {id}\nnote: tweak\n---\n## #one\n**When:** now.\n**Do:** zebra quartz marmalade.\n"
        code, out = self.save(body.format(id="beta-report"))
        self.assertEqual(code, 1)
        self.assertEqual(store.get("beta-report").path.read_bytes(), before)
        self.assertNotIn("Write the beta weekly report", out)
        self.assertNotIn("zebra", out)
        code2, out2 = self.save(body.format(id="no-such-piece"))
        self.assertEqual((code2, out2.replace("no-such-piece", "X")), (code, out.replace("beta-report", "X")))
        self.assertIsNone(store.get("no-such-piece"))
        self.assertEqual(sorted(p.id for p in store.all_pieces()), ["alpha-release", "beta-report"])
        code, out = self.save(body.format(id="alpha-release"))             # its own piece: improved as usual
        self.assertEqual(code, 0, out)
        self.assertEqual(store.get("alpha-release").version, 2)


class ElsewhereTest(Folders):
    def test_installed_agents_are_never_synced_into_a_public_repository(self):
        from athos import capture, wiki
        piece("beta-one", "Beta one", "beta work", ["beta"],
              body="## #b\n**When:** b.\n**Do:** b.\n**Links:** [[beta-two#c]]\n")
        piece("beta-two", "Beta two", "more beta work", ["beta"], body="## #c\n**When:** c.\n**Do:** c.\n")
        repo = Path(self.folder("alpha"))
        target = repo / ".claude" / "agents"
        wiki.remember_install(target, "beta")              # installed there once; the repository is public now
        (repo / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        capture.save_text("---\ntitle: Beta three\nwhen: beta three work\n---\n## #d\n**When:** d.\n**Do:** d.\n",
                          "e1", self.folder("beta"))      # saved from a folder that is not public
        self.assertFalse(list(target.glob("athos-*.md")))

    def test_events_in_a_public_repository_name_no_other_project(self):
        piece("alpha-release", "Ship the alpha release", "shipping the alpha release", ["alpha"])
        piece("habit-ship", "Ship carefully", "shipping the alpha release carefully", ["beta", "gamma"])
        control.profile_add(["habit-ship"])
        control.profile_allow_public(["habit-ship"])
        root = Path(self.folder("alpha"))
        (root / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        e = {"session_id": "ev1", "cwd": str(root)}
        self.hook("prompt", {**e, "prompt": "ship the alpha release carefully"})
        self.hook("tool", {**e, "tool_name": "Bash", "tool_input": {"command": "athos show habit-ship"}})
        (r,) = events("route")
        self.assertIn("habit-ship", [c["piece"] for c in r["candidates"]])
        for row in [*r["candidates"], *events("piece_opened")]:
            self.assertFalse({"beta", "gamma"} & set(row.get("projects") or []), row)
        self.assertNotIn("gamma", log_text())
