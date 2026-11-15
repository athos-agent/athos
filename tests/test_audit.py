"""The audit log (route, edit_seen, model, trigger, hook_error events and log.md), `athos audit` and
its rules. All data here is synthetic."""

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from athos import audit, cli, eval as ev, load, store
from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")
SECRET = "zebra quartz marmalade"            # words that must never reach the audit log


def piece(pid, title, when, projects=(), body="## #one\n**When:** at the start.\n**Do:** the first thing.\n"):
    p = store.Piece(id=pid, title=title, when=when, body=body, projects=list(projects), created="2026-11-01",
                    last_used="2026-11-01", origin={"platform": "test", "model": "test"})
    store._write(p)
    return p


def write_events(rows):
    path = Path(os.environ["ATHOS_HOME"]) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def events(kind=None):
    return [e for e in ev.events() if kind is None or e.get("type") == kind]


def log_text():
    try:
        return ev.log_file().read_text()
    except OSError:
        return ""


class HookCase(TempHome):
    """Runs the hooks in this process, with the event on a fake stdin, in folders named after projects."""

    def setUp(self):
        super().setUp()
        self.alpha = Path(self.home) / "alpha"
        self.beta = Path(self.home) / "beta"
        self.alpha.mkdir()
        self.beta.mkdir()

    def hook(self, name, payload):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out):
            cli.hook(name)
        text = out.getvalue().strip()
        return json.loads(text) if text else None


class RouteEventTest(HookCase):
    def setUp(self):
        super().setUp()
        piece("ship-release", "Ship a release with the checklist", "shipping a release of the app", ["alpha"])
        piece("write-report", "Write the weekly report", "writing the weekly report for the team", ["beta"])

    def test_one_route_per_request_with_and_without_a_match_and_no_request_text(self):
        ev_ = {"session_id": "s1", "cwd": str(self.alpha)}
        self.hook("prompt", {**ev_, "prompt": f"please ship the release of the app {SECRET}"})
        self.hook("prompt", {**ev_, "prompt": f"what time is it {SECRET}"})
        routes = events("route")
        self.assertEqual(len(routes), 2)
        hit, miss = routes
        self.assertEqual(hit["chosen"], ["ship-release"])
        self.assertEqual(hit["candidates"][0]["piece"], "ship-release")
        self.assertTrue(hit["candidates"][0]["kept"])
        self.assertEqual(hit["candidates"][0]["reason"], "chosen")
        self.assertIsInstance(hit["candidates"][0]["shared"], int)
        self.assertGreater(hit["injected_chars"], 0)
        self.assertEqual((hit["mode"], hit["project"], hit["scope_reason"]), ("auto", "alpha", "auto:project"))
        self.assertEqual(hit["thresholds"]["min_score"], load.MIN_SCORE)
        self.assertEqual(hit["request_chars"], len(f"please ship the release of the app {SECRET}"))
        self.assertEqual(len(hit["request_sha"]), 12)
        self.assertEqual(hit["task_id"], [e for e in events("task_start")][0]["task_id"])
        self.assertEqual(miss["chosen"], [])
        self.assertEqual(miss["injected_chars"], 0)
        self.assertEqual(miss["request_kind"], "person")
        for e in events():
            if e["type"] in audit.AUDIT_TYPES:
                self.assertNotIn("zebra", json.dumps(e))
        log = log_text()
        self.assertNotIn("zebra", log)
        heads = [line for line in log.splitlines() if line.startswith("## [")]
        self.assertTrue(any(" route | alpha | loaded ship-release" in line for line in heads), log)
        self.assertTrue(any(line.endswith("route | alpha | none · scope auto:project") for line in heads), log)

    def test_a_harness_message_is_routed_as_such_and_its_share_trigger_marked_not_the_persons(self):
        ev_ = {"session_id": "s2", "cwd": str(self.alpha)}
        self.hook("prompt", {**ev_, "prompt": "<agent-message from=\"x\">share this way of working in the gallery "
                                              f"{SECRET}</agent-message>"})
        (r,) = events("route")
        self.assertEqual((r["request_kind"], r["wrapper"], r["chosen"]), ("harness", "agent-message", []))
        (t,) = events("trigger")
        self.assertEqual((t["trigger"], t["from_person"], t["wrapper"]), ("share", False, "agent-message"))
        self.assertNotIn("zebra", json.dumps(t))
        self.assertIn("trigger | alpha | share · harness text <agent-message>", log_text())

    def test_the_save_button_records_a_trigger_from_the_person(self):
        self.hook("prompt", {"session_id": "s3", "cwd": str(self.alpha),
                             "prompt": "Athos · save: keep this task as a way of working"})
        (t,) = events("trigger")
        self.assertEqual((t["trigger"], t["from_person"]), ("save", True))
        self.assertEqual(events("route"), [])          # a button's request is not a request to route

    def test_a_project_without_pieces_says_so_in_the_scope(self):
        gamma = Path(self.home) / "gamma"
        gamma.mkdir()
        self.hook("prompt", {"session_id": "s4", "cwd": str(gamma), "prompt": "write the weekly report for the team"})
        (r,) = events("route")
        self.assertEqual(r["scope_reason"], "auto:no-own-pieces")      # only the profile, which is empty here
        self.assertEqual((r["chosen"], r["in_scope"]), ([], 0))
        self.assertIn("route | gamma | none · scope auto:no-own-pieces", log_text())
        self.assertNotIn("write-report", log_text())   # another project's piece is never named in log.md
        # Naming the other project brings its piece, which log.md counts without naming.
        self.hook("prompt", {"session_id": "s4", "cwd": str(gamma),
                             "prompt": "write the weekly report for the team, as in beta"})
        r = events("route")[-1]
        self.assertEqual((r["scope_reason"], r["chosen"]), ("auto:no-own-pieces+named", ["write-report"]))
        self.assertIn("1 piece(s) of another project", log_text())
        self.assertNotIn("write-report", log_text())

    def test_a_swallowed_exception_is_recorded_without_its_message(self):
        with mock.patch.object(load, "on_prompt", side_effect=KeyError(SECRET)):
            self.hook("prompt", {"session_id": "s5", "cwd": str(self.alpha), "prompt": "hello there"})
        (e,) = events("hook_error")
        self.assertEqual((e["hook"], e["error"]), ("prompt", "KeyError"))
        self.assertNotIn("zebra", json.dumps(e))
        self.assertNotIn("zebra", log_text())

    def test_model_events_say_where_the_model_was_read(self):
        self.hook("session-start", {"session_id": "s6", "cwd": str(self.alpha), "model": "model-a"})
        self.hook("prompt", {"session_id": "s6", "cwd": str(self.alpha), "prompt": "ship the release"})
        models = events("model")
        self.assertEqual([(m["model"], m["source"]) for m in models], [("model-a", "event"), ("model-a", "session")])

    def test_model_event_reads_the_transcripts_latest_reply(self):
        transcript = Path(self.home) / "t.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"model": "model-b"}}) + "\n")
        self.hook("session-start", {"session_id": "s7", "cwd": str(self.alpha), "model": "model-a"})
        self.hook("prompt", {"session_id": "s7", "cwd": str(self.alpha), "prompt": "ship the release",
                             "transcript_path": str(transcript)})
        last = events("model")[-1]
        self.assertEqual((last["model"], last["seen_in_transcript"]), ("model-a", "model-b"))
        report = audit.check("s7", ev.events(), transcripts=False)
        rule = next(r for r in report["rules"] if r["rule"] == "model_inconsistent")
        self.assertEqual(rule["status"], "flagged")

    def test_session_start_names_the_log_and_the_audit_command_in_one_line(self):
        out = self.hook("session-start", {"session_id": "s8", "cwd": str(self.alpha)})
        text = out["hookSpecificOutput"]["additionalContext"]
        hint = [line for line in text.splitlines() if "audit --session s8" in line]
        self.assertEqual(len(hint), 1)
        self.assertIn("log.md", hint[0])

    def test_routing_is_the_same_with_and_without_the_trace(self):
        pieces = store.all_pieces()
        for prompt in ("ship the release of the app", "weekly report", "nothing here", ""):
            self.assertEqual([p.id for p in load.relevant(prompt, pieces, meaning=False)],
                             [p.id for p in load.decide(prompt, pieces, meaning=False)[0]])


class EditSeenTest(TempHome):
    """The edit detector's decisions, through the real hooks in a child process."""

    def run_athos(self, *args, stdin="", cwd=None):
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=cwd or self.home, env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})

    def test_a_snapshot_and_an_attribution_each_leave_an_edit_seen_without_file_names(self):
        work = Path(self.home) / "work"
        work.mkdir()
        self.run_athos("save", stdin="---\ntitle: Review a services contract\nwhen: review a services contract\n"
                                     "---\n## #penalties\n**When:** reading.\n**Do:** list each penalty.\n",
                       cwd=str(work))              # saved in this project, so it belongs to it
        e = {"session_id": "s1", "cwd": str(work)}
        self.run_athos("hook", "prompt", stdin=json.dumps({**e, "prompt": "review a services contract"}))
        f = work / "secret-client-report.md"
        f.write_text("Penalties:\n- ten percent\n")
        self.run_athos("hook", "tool", stdin=json.dumps({**e, "tool_name": "Write",
                                                         "tool_input": {"file_path": str(f)}}))
        f.write_text("Penalties:\n- 10% per week, never more than 30%\n")
        self.run_athos("hook", "prompt", stdin=json.dumps({**e, "prompt": "thanks, next one"}))
        seen = events("edit_seen")
        self.assertEqual([(s["decision"], s["source"], s["attributed_to"]) for s in seen],
                         [("snapshot", "agent_tool", "agent"), ("attributed", "outside", "person")])
        self.assertEqual(seen[1]["basis"], [])
        self.assertEqual(seen[1]["piece_basis"], "first_task_piece")
        self.assertEqual(seen[0]["file_sha"], seen[1]["file_sha"])
        for s in seen:
            self.assertNotIn("secret-client", json.dumps(s))
        self.assertNotIn("secret-client", log_text())
        self.assertIn("edit_seen | work | a file change given to the person (basis: none", log_text())


class LogFileTest(TempHome):
    def test_lines_have_a_fixed_prefix_and_the_file_rotates_past_its_cap(self):
        with mock.patch.object(ev, "LOG_CAP", 200):
            for i in range(10):
                ev.log_line("route", "alpha", f"none · line {i}")
        lines = log_text().splitlines()
        self.assertTrue(all(line.startswith("## [") and " route | alpha | none · line " in line for line in lines))
        self.assertTrue((ev.log_file().with_name("log.1.md")).exists())
        self.assertLess(len(log_text()), 400)


# ------------------------------------------------------------------------------------------------ one rule each
T0 = "2026-11-10T10:00:00.000+00:00"
T1 = "2026-11-10T10:05:00.000+00:00"


def start(tid, sid="s", project="alpha", model="model-a", request="hello", chars=None):
    return {"type": "task_start", "task_id": tid, "session_id": sid, "project": project, "model": model, "at": T0,
            "request": request[:120], "request_chars": len(request) if chars is None else chars}


def end(tid, pieces=(), sid="s", model="model-a"):
    return {"type": "task_end", "task_id": tid, "session_id": sid, "pieces": list(pieces), "saved": [],
            "model": model, "at": T1}


def routed(tid, sid="s", chosen=(), named=(), reason="auto:project", injected=0, v="0.1.110"):
    return {"type": "route", "task_id": tid, "session_id": sid, "project": "alpha", "scope_reason": reason,
            "named_projects": list(named), "chosen": list(chosen), "injected_chars": injected,
            "thresholds": {"inject_cap": 8000}, "request_kind": "person", "at": T0, "v": v}


class RulesTest(TempHome):
    def setUp(self):
        super().setUp()
        piece("a1", "Alpha thing", "alpha work", ["alpha"])
        piece("b1", "Beta thing", "beta work", ["beta"])
        piece("g1", "General thing", "any work")

    def rule(self, rows, name, show=False, versions=None):
        write_events(rows)
        report = audit.run(session="s", show=show, versions=versions, transcripts=False)
        (s,) = report["sessions"]
        return next(r for r in s["rules"] if r["rule"] == name)

    def test_other_project_load(self):
        r = self.rule([start("t1"), routed("t1", chosen=["b1"]), end("t1", ["b1"])], "other_project_load")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        self.assertEqual(r["found"][0]["piece"], "a piece of another project")
        r = self.rule([start("t1"), routed("t1", chosen=["b1"]), end("t1", ["b1"])], "other_project_load", show=True)
        self.assertEqual(r["found"][0]["piece"], "b1")
        r = self.rule([start("t1"), routed("t1", chosen=["b1"], named=["beta"]), end("t1", ["b1"])],
                      "other_project_load")
        self.assertEqual(r["status"], "clean")
        r = self.rule([start("t1"), routed("t1", chosen=["a1", "g1"]), end("t1", ["a1", "g1"])], "other_project_load")
        self.assertEqual(r["status"], "clean")

    def test_other_project_load_on_old_data_is_partial(self):
        r = self.rule([start("t1", request="like we did in beta"), end("t1", ["b1"])], "other_project_load")
        self.assertEqual(r["status"], "partial")
        r = self.rule([start("t1", request="do it"), end("t1", ["b1"])], "other_project_load")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))

    def test_load_without_own_pieces(self):
        rows = [start("t1", project="gamma"), end("t1", ["b1"])]
        rows[0]["project"] = "gamma"
        r = self.rule(rows, "load_without_own_pieces")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        r = self.rule([start("t1"), routed("t1", chosen=["b1"], reason="auto:project-without-pieces")],
                      "load_without_own_pieces")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        r = self.rule([start("t1"), routed("t1", chosen=["a1"])], "load_without_own_pieces")
        self.assertEqual(r["status"], "clean")
        # Since 0.1.111 such a project sees the profile: a profile piece is fine, an unnamed other project's isn't.
        r = self.rule([start("t1"), routed("t1", chosen=["g1"], reason="auto:no-own-pieces")],
                      "load_without_own_pieces")
        self.assertEqual(r["status"], "clean")
        r = self.rule([start("t1"), routed("t1", chosen=["b1"], named=["beta"], reason="auto:no-own-pieces+named")],
                      "load_without_own_pieces")
        self.assertEqual(r["status"], "clean")

    def test_edit_without_basis(self):
        seen = {"type": "edit_seen", "session_id": "s", "task_id": "t1", "attributed_to": "person", "basis": [],
                "piece": "a1", "at": T0}
        r = self.rule([start("t1"), seen], "edit_without_basis")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        r = self.rule([start("t1"), {**seen, "basis": ["changed_between_tool_calls"]}], "edit_without_basis")
        self.assertEqual(r["status"], "clean")
        old = {"type": "learned_from_edit", "session_id": "s", "task_id": "t1", "piece": "a1", "at": T0}
        r = self.rule([start("t1"), old], "edit_without_basis")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))

    def test_model_inconsistent(self):
        r = self.rule([start("t1"), end("t1"), start("t2", model="model-b"), end("t2", model="model-b")],
                      "model_inconsistent")
        self.assertEqual(r["status"], "flagged")
        r = self.rule([start("t1"), end("t1")], "model_inconsistent")
        self.assertEqual(r["status"], "not_evaluated")      # no model events and no transcript

    def test_model_inconsistent_against_an_old_sessions_transcript(self):
        projects = Path(self.home) / "claude" / "projects" / "-x"
        projects.mkdir(parents=True)
        (projects / "s.jsonl").write_text(json.dumps({"type": "assistant", "timestamp": "2026-11-10T10:02:00Z",
                                                      "message": {"model": "model-b"}}) + "\n")
        write_events([start("t1"), end("t1")])
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(Path(self.home) / "claude")}):
            (s,) = audit.run(session="s")["sessions"]
        r = next(r for r in s["rules"] if r["rule"] == "model_inconsistent")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        self.assertEqual(r["found"][0]["transcript"], ["model-b"])

    def test_injected_over_cap(self):
        r = self.rule([start("t1"), routed("t1", chosen=["a1"], injected=9000)], "injected_over_cap")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        r = self.rule([start("t1"), routed("t1", chosen=["a1"], injected=900)], "injected_over_cap")
        self.assertEqual(r["status"], "clean")
        r = self.rule([start("t1"), end("t1", ["a1"])], "injected_over_cap")
        self.assertEqual(r["status"], "partial")             # estimated from today's pieces

    def test_trigger_not_from_person(self):
        trig = {"type": "trigger", "session_id": "s", "trigger": "share", "from_person": False,
                "wrapper": "agent-message", "at": T0}
        r = self.rule([start("t1"), routed("t1"), trig], "trigger_not_from_person")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        r = self.rule([start("t1"), routed("t1"), {**trig, "from_person": True}], "trigger_not_from_person")
        self.assertEqual(r["status"], "clean")
        r = self.rule([start("t1"), end("t1")], "trigger_not_from_person")
        self.assertEqual(r["status"], "not_evaluated")

    def test_version_mismatch(self):
        r = self.rule([start("t1"), routed("t1", v="0.1.110"), routed("t1", v="0.1.111")], "version_mismatch")
        self.assertEqual(r["status"], "flagged")
        installed = {"agents": {"claude-code": "0.1.110", "path": "0.1.96"}}
        r = self.rule([start("t1"), end("t1")], "version_mismatch", versions=installed)
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        same = {"agents": {"claude-code": "0.1.110", "path": "0.1.110"}}
        r = self.rule([start("t1"), routed("t1")], "version_mismatch", versions=same)
        self.assertEqual(r["status"], "clean")
        r = self.rule([start("t1"), end("t1")], "version_mismatch")
        self.assertEqual(r["status"], "not_evaluated")

    def test_weak_evidence_learning(self):
        learn = {"type": "learn", "session_id": "s", "task_id": "t1", "decision": "saved", "piece": "a1",
                 "evidence": ["model_opinion"], "at": T0}
        r = self.rule([start("t1"), learn], "weak_evidence_learning")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        r = self.rule([start("t1"), {**learn, "evidence": ["tests_passed", "model_opinion"]}], "weak_evidence_learning")
        self.assertEqual(r["status"], "clean")
        r = self.rule([start("t1")], "weak_evidence_learning")
        self.assertEqual(r["status"], "not_evaluated")

    def test_private_piece_named(self):
        r = self.rule([start("t1")], "private_piece_named")
        self.assertEqual(r["status"], "clean")                 # no private piece in the store
        p = store.get("b1")
        p.visibility = "private"
        store._write(p)
        r = self.rule([start("t1"), routed("t1", chosen=["a1"])], "private_piece_named")
        self.assertEqual(r["status"], "clean")
        r = self.rule([start("t1"), {**routed("t1"), "candidates": [{"piece": "b1", "score": 3.0}]}],
                      "private_piece_named")
        self.assertEqual((r["status"], r["count"]), ("flagged", 1))
        self.assertNotIn("b1", json.dumps(r))                  # counted, never named

    def test_picking_sessions_and_the_command(self):
        write_events([start("t1", sid="s-one"), start("t2", sid="s-two", project="beta"),
                      {**start("t3", sid="s-three"), "at": "2026-11-11T00:00:00+00:00"}])
        self.assertEqual(list(audit.pick(ev.events(), session="s-tw")), ["s-two"])
        self.assertEqual(list(audit.pick(ev.events(), project="alpha")), ["s-one", "s-three"])
        self.assertEqual(list(audit.pick(ev.events())), ["s-three"])
        self.assertEqual(list(audit.pick(ev.events(), last=2)), ["s-two", "s-three"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("athos.connect.versions", return_value={"agents": {}}):
            cli.main(["audit", "--project", "alpha", "--json"])
        report = json.loads(out.getvalue())
        self.assertEqual([s["summary"]["session_id"] for s in report["sessions"]], ["s-one", "s-three"])
        self.assertEqual({r["rule"] for r in report["rules"]}, {name for name, _ in audit.RULES})
