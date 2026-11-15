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
