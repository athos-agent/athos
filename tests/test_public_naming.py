"""In a repository marked public no command names another project's piece: every subcommand is either run here and
checked, or listed as one that prints no piece of the store (with why), so a new command cannot be forgotten. All data
here is synthetic."""

import argparse
import contextlib
import io
import json
from pathlib import Path
from unittest import mock

from athos import cli, control, eval as ev, paths, store
from tests.test_routing import Folders, piece

FOREIGN = ("beta-hidden", "Hidden beta title")              # never printed in the public repository
PRIVATE = ("alpha-private", "Private alpha title")          # this project's, but private: never printed there either
PROFILE = ("habit-general", "General habit title")          # a profile piece not allowed in public

# Run in the public repository and checked: (argv, why it may name pieces).
CHECKED = [
    ["list"], ["audit"], ["audit", "--json"], ["audit", "--last", "5"], ["audit", "--last", "5", "--json"],
    ["profile"], ["profile", "--json"], ["profile", "--untagged"], ["profile", "--untagged", "--json"],
    ["report"], ["report", "--json"], ["wiki"], ["wiki", "--json"], ["wiki", "agents"],
    ["status"], ["status", "--json"], ["status", "--ui"], ["privacy"], ["privacy", "--json"],
    ["journal"], ["load"], ["dream", "--dry-run"], ["dream", "--dry-run", "--json"], ["curate"],
    ["export", "--guild", "{out}"], ["export", "{out}"], ["memory"], ["memory", "--json"], ["memory", "findings"],
    ["memory", "project"],
]
# Commands that take a piece id, run with each piece that may not be named here: the answer is the one an id that does
# not exist gets ({id} stands for it), and no title, step or other id of the store comes out.
BY_ID = [["show", "{id}"], ["verify", "{id}"], ["route", "{id}"], ["route", "{id}", "--json"], ["dismiss", "{id}"],
         ["revert", "{id}"], ["test", "{id}"], ["share", "{id}"], ["delegate", "{id}", "do the thing"],
         ["merge", "{id}", "{out}"], ["export", "--guild", "{out}", "--piece", "{id}"]]
# Refused outright in the public repository, with the same answer for an id that exists elsewhere and one that doesn't.
REFUSED = [["audit", "--show"], ["audit", "--project", "beta"], ["journal", "--project", "beta"],
           ["memory", "project", "beta"]]
# Subcommands that print no piece of the store, or are not run here (with why).
EXEMPT = {
    "add": "adds a page from the gallery by its own name",
    "bench": "runs on throwaway stores of public cases; --replay/--from-store print counts only",
    "codex": "installs or removes the Codex plugin",
    "connector": "sets up connectors, by connector name",
    "desktop": "starts Claude Desktop's server",
    "doctor": "versions of the installed agents",
    "embed": "turns meaning on or off",
    "gallery": "builds the gallery pages from the repository's own examples",
    "hook": "the hooks: covered by the hook tests of a public repository",
    "import": "imports other agents' sessions, prints counts",
    "library": "starts the local library server",
    "mark": "marks the last task good, corrected or failed",
    "mcp": "the MCP server: covered by its own tests",
    "merge": "merges two pieces the person names",
    "opencode": "installs or removes the OpenCode plugin",
    "project": "writes this project's own pages into the repository (only what may load there)",
    "public": "this repository's marker",
    "repair": "corrects polluted statistics, prints counts",
    "save": "saves the person's piece: covered by the save tests of a public repository",
    "shadow": "turns background shadowing on or off",
    "start": "first run: language and profession",
    "step": "the agent reports its step in this session",
    "tiers": "model tiers",
    "watch": "the live trail of this folder's session (trail.view keeps to what may load there: TrailTest)",
}


def subcommands() -> set[str]:
    for a in cli._parser()._actions:
        if isinstance(a, argparse._SubParsersAction):
            return set(a.choices)
    return set()


class EveryCommandTest(Folders):
    def setUp(self):
        super().setUp()
        piece("alpha-release", "Ship the alpha release", "shipping the alpha release", ["alpha"],
              body="## #ship\n**When:** shipping.\n**Do:** ship it.\n**Links:** [[beta-hidden#s]]\n")
        piece(*FOREIGN, "the hidden beta work", ["beta"], body="## #s\n**When:** at s.\n**Do:** the s thing.\n")
        piece(*PRIVATE, "the private alpha work", ["alpha"], visibility="private")
        piece(*PROFILE, "the general habit", [])
        control.profile_add(["habit-general"])
        self.root = Path(self.folder("alpha"))
        (self.root / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        # Activity elsewhere: a session in beta that loaded and saved its piece, and one here.
        for sid, project, cwd, pid in (("sb", "beta", self.folder("beta"), "beta-hidden"),
                                       ("sa", "alpha", str(self.root), "alpha-release")):
            ev.append({"type": "task_start", "task_id": f"t-{sid}", "session_id": sid, "platform": "claude-code",
                       "model": "claude-opus-5-5", "project": project, "at": "2026-11-15T10:00:00+00:00",
                       "request": "", "request_chars": 5})
            ev.append({"type": "route", "task_id": f"t-{sid}", "session_id": sid, "project": project,
                       "chosen": [pid], "candidates": [{"piece": pid, "score": 3.0, "projects": [project]}],
                       "scope_reason": "auto:project", "at": "2026-11-15T10:00:01+00:00", "v": "0.1.1"})
            ev.append({"type": "task_end", "task_id": f"t-{sid}", "session_id": sid, "at": "2026-11-15T10:01:00+00:00",
                       "duration_s": 60, "model": "claude-opus-5-5", "pieces": [pid], "saved": [pid]})
            ev.append({"type": "mark", "task_id": f"t-{sid}", "result": "ok", "at": "2026-11-15T10:02:00+00:00"})
            ev.log_line("route", project, f"loaded {pid} · 10 chars")
        cli._remember_session({"cwd": str(self.root), "session_id": "sa"})
        from athos import session
        session.update("sa", loaded=["alpha-release", "beta-hidden"], task_why={"beta-hidden": []},
                       task_route=["alpha-release", "beta-hidden"], task_loaded=["alpha-release"], last_saved={"id": "beta-hidden", "title": FOREIGN[1]})

    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), \
                mock.patch("athos.connect.versions", return_value={"agents": {}, "behind": []}):
            try:
                code = cli.main(argv)
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue()

    def test_every_subcommand_is_checked_or_exempt(self):
        covered = {argv[0] for argv in CHECKED + REFUSED + BY_ID}
        self.assertEqual(subcommands() - covered - set(EXEMPT), set(), "classify the new command here")

    def test_no_command_names_what_may_not_load_here(self):
        out_dir = Path(self.home) / "guild-out"
        for argv in CHECKED:
            argv = [a.replace("{out}", str(out_dir)) for a in argv]
            _code, text = self.run_cli(argv)
            for words in (*FOREIGN, *PRIVATE, *PROFILE):
                self.assertNotIn(words, text, f"`athos {' '.join(argv)}` printed {words!r}")
        written = "".join(f.read_text(errors="ignore") for f in out_dir.rglob("*") if f.is_file()) \
            if out_dir.exists() else ""
        for words in (FOREIGN[1], PRIVATE[1], PROFILE[1], "the s thing"):      # an own page may link to one by id
            self.assertNotIn(words, written)
        self.assertFalse(list(out_dir.rglob("beta-hidden*")))

    def test_commands_that_take_an_id_answer_as_for_a_missing_one(self):
        out_dir = str(Path(self.home) / "by-id-out")
        for argv in BY_ID:
            def run(pid):
                code, text = self.run_cli([a.replace("{id}", pid).replace("{out}", out_dir) for a in argv])
                return code, text.replace(pid, "{id}")
            missing = run("no-such-piece")
            for pid in (FOREIGN[0], PRIVATE[0], PROFILE[0]):
                got = run(pid)
                self.assertEqual(got, missing, f"`athos {' '.join(argv)}` with {pid}")
                for words in (FOREIGN[1], PRIVATE[1], PROFILE[1], "the s thing"):
                    self.assertNotIn(words, got[1])
        self.assertFalse(Path(out_dir).exists() and any(Path(out_dir).rglob("*.md")))

    def test_the_audit_refuses_what_would_name_other_projects(self):
        for argv in REFUSED:
            code, text = self.run_cli(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn("marked public", text)
            self.assertNotIn("beta-hidden", text)

    def test_a_piece_elsewhere_and_a_missing_one_get_the_same_answer(self):
        _c1, foreign = self.run_cli(["show", "beta-hidden"])
        _c2, missing = self.run_cli(["show", "no-such-piece"])
        self.assertEqual(foreign.replace("beta-hidden", "X"), missing.replace("no-such-piece", "X"))


class TrailTest(Folders):
    def test_the_pane_of_a_public_session_names_nothing_else_wherever_it_is_drawn(self):
        from athos import trail
        piece("alpha-release", "Ship the alpha release", "shipping the alpha release", ["alpha"],
              body="## #ship\n**When:** shipping.\n**Do:** ship it.\n**Calls:** [[beta-hidden]]\n"
                   "**Links:** [[beta-hidden#s]]\n")
        piece(*FOREIGN, "the hidden beta work", ["beta"], body="## #s\n**When:** at s.\n**Do:** the s thing.\n")
        state = {"task_loaded": ["alpha-release"], "task_why": {"alpha-release": []}, "public": True,
                 "project": "alpha"}
        drawn = json.dumps(trail.view(state))
        self.assertIn("alpha-release", drawn)
        for words in (*FOREIGN, "the s thing"):
            self.assertNotIn(words, drawn)
        self.assertIn("the s thing", json.dumps(trail.view({**state, "public": False})))
