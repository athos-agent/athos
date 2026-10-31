import json
import os
import subprocess
import sys
from pathlib import Path

from athos import capture, trail
from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")
PIECE = """---
title: Cut a release
when: cut a release of the package
---
## #bump
**When:** starting.
**Do:** bump the version.

## #tag
**When:** after the bump.
**Do:** tag and push.
"""


class TrailTest(TempHome):
    def run_athos(self, *args, stdin=""):
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=self.home, env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli",
                                                  "GIT_CONFIG_GLOBAL": os.path.join(self.home, "gitconfig")})

    def hook(self, event, payload):
        r = self.run_athos("hook", event, stdin=json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def status(self):
        r = self.run_athos("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_a_task_walks_its_piece_step_by_step_and_shows_what_ran_beside_it(self):
        self.run_athos("save", stdin=PIECE)
        ev = {"session_id": "t1", "cwd": self.home}
        self.hook("session-start", ev)
        ctx = self.hook("prompt", {**ev, "prompt": "cut a release of the package"})
        self.assertIn("athos step <piece-id>#<statement_id>", ctx["hookSpecificOutput"]["additionalContext"])
        t = self.status()["trail"]
        self.assertEqual([s["state"] for s in t["pieces"][0]["steps"]], ["ahead", "ahead"])
        self.assertEqual(self.run_athos("step", "cut-a-release#bump").stdout.strip(), "ok")
        self.run_athos("step", "#tag")                                 # the piece the task follows, by default
        self.run_athos("step", "--new", "announce it in the channel")
        self.hook("tool", {**ev, "tool_name": "Agent", "tool_input": {"subagent_type": "Explore",
                                                                      "description": "find the changelog"}})
        self.hook("tool", {**ev, "tool_name": "Skill", "tool_input": {"skill": "pdf"}})
        t = self.status()["trail"]
        self.assertEqual([(s["id"], s["state"]) for s in t["pieces"][0]["steps"]], [("bump", "done"), ("tag", "now")])
        self.assertEqual(t["new"], ["announce it in the channel"])
        self.assertEqual(t["beside"], [{"kind": "agent", "name": "Explore", "why": "find the changelog"},
                                       {"kind": "skill", "name": "pdf"}])
        self.hook("stop", ev)
        self.assertEqual(self.status()["trail"]["pieces"][0]["steps"][1]["state"], "done")
        events = [json.loads(x) for x in (Path(self.home) / "events.jsonl").read_text().splitlines()]
        self.assertEqual(sum(1 for e in events if e.get("type") == "trail"), 5)
        self.hook("prompt", {**ev, "prompt": "something else entirely"})           # a new task starts a new trail
        self.assertFalse(self.status()["trail"]["busy"])

    def test_a_piece_the_agent_opens_on_its_own_joins_the_trail(self):
        self.run_athos("save", stdin=PIECE)
        ev = {"session_id": "t2", "cwd": self.home}
        self.hook("prompt", {**ev, "prompt": "unrelated words here"})
        self.hook("tool", {**ev, "tool_name": "Bash", "tool_input": {"command": "athos show cut-a-release"}})
        p = self.status()["trail"]["pieces"][0]
        self.assertEqual((p["id"], p["how"]), ("cut-a-release", "read"))

    def test_adjust_from_the_pane_improves_the_piece_and_starts_no_task(self):
        ev = {"session_id": "t3", "cwd": self.home}
        out = self.hook("prompt", {**ev, "prompt": "Athos · ajustar cut-a-release#tag: firmá el tag"})
        self.assertIn("[Adjust]", out["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(capture.is_adjust_prompt("Athos · adjust x#y: z"))

    def test_the_greeting_follows_the_hour_and_the_language(self):
        self.assertTrue(trail.greeting("es", 9).startswith("Buen día"))
        self.assertTrue(trail.greeting("en", 15).startswith("Good afternoon"))
        self.assertTrue(trail.greeting("es", 23).startswith("Buenas noches"))
        Path(self.home, "config.json").write_text(json.dumps({"name": "Ana María"}))
        self.assertEqual(trail.greeting("es", 9), "Buen día, Ana")

    def test_statement_ids_may_have_hyphens(self):
        from athos import store, wiki
        p = store.create("Pub", "publish", "## #subir-version\n**Do:** bump.\n\n## #tag\n**Do:** tag. [[pub#subir-version]]")
        self.assertEqual([s.id for s in wiki.statements(p)], ["subir-version", "tag"])
        self.assertEqual(wiki.LINK.findall(p.body), [("pub", "subir-version")])

    def test_a_step_reads_as_its_action(self):
        self.assertEqual(trail.label("con el contrato a la vista.", "resumir en cinco líneas: partes, objeto, plazo.", "x"),
                         "Resumir en cinco líneas")
        self.assertEqual(trail.label("al empezar.", "leer solo caso.md, nunca cliente/.", "x"), "Leer solo caso.md, nunca cliente/")
        self.assertEqual(trail.label("deciding where to keep the key.", "", "key"), "Deciding where to keep the key")
        self.assertTrue(trail.label("", "a " * 80, "x").endswith("…"))
        self.assertEqual(trail.label("", "", "native_harness"), "Native harness")

    def test_steps_find_the_task_when_each_hook_has_its_own_session(self):
        # Muse Code gives every hook call its own session id; the folder keeps the request's.
        self.run_athos("save", stdin=PIECE)
        self.hook("prompt", {"session_id": "req", "cwd": self.home, "prompt": "cut a release of the package"})
        self.hook("tool", {"session_id": "other", "cwd": self.home, "tool_name": "Skill", "tool_input": {"skill": "pdf"}})
        self.run_athos("step", "cut-a-release#bump")
        self.hook("stop", {"session_id": "another", "cwd": self.home})
        t = self.status()["trail"]
        self.assertEqual(t["pieces"][0]["steps"][0]["state"], "done")
        self.assertEqual(t["beside"], [{"kind": "skill", "name": "pdf"}])

    def test_the_tool_hook_records_steps_a_sandbox_kept_from_athos(self):
        self.run_athos("save", stdin=PIECE)
        ev = {"session_id": "sb", "cwd": self.home}
        self.hook("prompt", {**ev, "prompt": "cut a release of the package"})
        cmd = "'/x/bin/athos' step cut-a-release#bump && /x/bin/athos step --new 'announce it'"
        self.hook("tool", {**ev, "tool_name": "Bash", "tool_input": {"command": cmd}})
        self.hook("tool", {**ev, "tool_name": "Bash", "tool_input": {"command": cmd}})      # repeated: no duplicates
        t = self.status()["trail"]
        self.assertEqual(t["pieces"][0]["steps"][0]["state"], "now")
        self.assertEqual(t["new"], ["announce it"])

    def test_no_ask_after_a_task_that_only_walked_an_existing_piece(self):
        self.run_athos("save", stdin=PIECE)
        ev = {"session_id": "fw", "cwd": self.home}
        req = "cut a release of the package:\\n1. bump\\n2. tag\\n3. push"          # a numbered list in the request
        self.hook("prompt", {**ev, "prompt": req})
        for _ in range(6):
            self.hook("tool", {**ev, "tool_name": "Edit", "tool_input": {"file_path": "x"}})
        self.run_athos("step", "cut-a-release#bump")
        self.assertIsNone(self.hook("stop", ev))
        self.hook("prompt", {**ev, "prompt": req})                                   # a new step: worth asking
        for _ in range(6):
            self.hook("tool", {**ev, "tool_name": "Edit", "tool_input": {"file_path": "x"}})
        self.run_athos("step", "cut-a-release#bump")
        self.run_athos("step", "--new", "announce it")
        self.assertIsNotNone(self.hook("stop", ev))


class SandboxedStepTest(TempHome):
    def test_a_step_the_sandbox_cannot_write_still_answers_ok(self):
        # Muse Code asked the person to approve every `athos step` outside its sandbox when the command failed.
        import argparse
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        from athos import cli
        out = io.StringIO()
        with mock.patch.object(cli, "_current_session", return_value={"session_id": "s"}), \
                mock.patch.object(cli.trail, "step", side_effect=PermissionError("sandbox")), redirect_stdout(out):
            rc = cli.cmd_step(argparse.Namespace(ref="deal#facts", new=None))
        self.assertEqual((rc, out.getvalue().strip()), (0, "ok"))
