"""The one thing the person sees of Athos (athos/indicator.py): learning, collaborating or idle, computed in one place,
recorded as a `ui` event only when it changes; and, in the minimal interface (the default), no line from the hooks
that the person reads. All data here is synthetic."""

import io
import json
import os
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from athos import cli, evidence, indicator, session
from tests.test_audit import HookCase, events, piece

BODY = "## #one\n**When:** at the start.\n**Do:** the first thing, as the team does it.\n"
FRONTIER, APPLY = "claude-opus-5-5", "claude-haiku-5-5"
UNITTEST = {"tool_name": "Bash", "tool_input": {"command": "python3 -m unittest -q"},
            "tool_response": {"stdout": "OK", "stderr": "", "interrupted": False}}
# An interactive Claude Code session: what the person sees is what this file checks.
INTERACTIVE = {"CLAUDE_CODE_ENTRYPOINT": "cli"}


def working(model, **more):
    """A session state with a task in progress."""
    return {"model": model, "task_id": "t1", "task_end": None, "task_loaded": [], "task_opened": [],
            "work_since_capture": 0, **more}


class StateTest(HookCase):
    """Each case of the definition, on a session state written by hand."""

    def state(self, st, sid="u1"):
        session.save(sid, st)
        return indicator.compute(sid)

    def test_nothing_known_is_idle(self):
        self.assertEqual(indicator.compute(None), ("idle", "no_session"))
        self.assertEqual(self.state({}), ("idle", "no_task"))

    def test_a_piece_given_to_an_apply_model_is_collaborating_while_the_task_runs(self):
        st = working(APPLY, task_loaded=["ship"], task_delivery="piece")
        self.assertEqual(self.state(st), ("collaborating", "piece_delivered"))
        self.assertEqual(self.state({**st, "task_end": {"task_id": "t1"}}), ("idle", "between_tasks"))

    def test_a_piece_a_frontier_model_opened_is_collaborating(self):
        st = working(FRONTIER, task_loaded=["ship"], task_opened=["ship"], task_delivery="index")
        self.assertEqual(self.state(st), ("collaborating", "piece_opened"))

    def test_offered_in_the_index_but_not_opened_is_not_collaborating(self):
        st = working(FRONTIER, task_offered=["ship"], task_delivery="index")
        self.assertEqual(self.state(st), ("idle", "nothing_in_use"))

    def test_a_frontier_task_gathering_evidence_is_learning(self):
        evidence.add("t1", {"type": "verify", "strength": "strong", "polarity": "positive", "ok": True})
        self.assertEqual(self.state(working(FRONTIER)), ("learning", "gathering_evidence"))
        self.assertEqual(self.state(working(FRONTIER, work_since_capture=0), "u2"), ("learning", "gathering_evidence"))

    def test_a_frontier_task_doing_work_is_learning_and_a_read_only_one_is_not(self):
        self.assertEqual(self.state(working(FRONTIER, work_since_capture=2)), ("learning", "task_with_work"))
        self.assertEqual(self.state(working(FRONTIER), "u2"), ("idle", "nothing_in_use"))

    def test_collaborating_wins_over_learning(self):
        evidence.add("t1", {"type": "verify", "strength": "strong", "polarity": "positive", "ok": True})
        st = working(FRONTIER, task_loaded=["ship"], task_opened=["ship"], work_since_capture=3)
        self.assertEqual(self.state(st), ("collaborating", "piece_opened"))

    def test_an_apply_model_never_learns(self):
        self.assertEqual(self.state(working(APPLY, work_since_capture=5)), ("idle", "nothing_in_use"))
        self.assertEqual(self.state(working("unknown", work_since_capture=5), "u2"), ("idle", "nothing_in_use"))

    def test_switched_off_is_idle(self):
        st = working(FRONTIER, work_since_capture=5)
        Path(self.home, "config.json").write_text(json.dumps({"autolearn": {"on": False}}))
        self.assertEqual(self.state(st), ("idle", "nothing_in_use"))
        Path(self.home, "config.json").write_text("{}")
        with mock.patch.dict(os.environ, {"ATHOS_CAPTURE": "off"}):
            self.assertEqual(self.state(st), ("idle", "nothing_in_use"))
        with mock.patch.dict(os.environ, {"ATHOS_HOOKS": "off"}):
            self.assertEqual(self.state({**st, "task_loaded": ["ship"]}), ("idle", "off"))

    def test_a_verifier_this_session_started_is_learning_until_it_ends(self):
        from athos import verify
        ended = {**working(FRONTIER), "task_end": {"task_id": "t1"}}
        since = time.time()
        verify.root().mkdir(parents=True, exist_ok=True)
        verify._lock().write_text("1")
        self.assertEqual(self.state({**ended, "verifying_since": since}), ("learning", "verifying"))
        self.assertEqual(self.state(ended, "u2"), ("idle", "between_tasks"))       # another session's run
        verify.release_lock()
        self.assertEqual(self.state({**ended, "verifying_since": since}), ("idle", "between_tasks"))
        verify._lock().write_text("1")                                               # an older run, still going
        self.assertEqual(self.state({**ended, "verifying_since": since + 60}), ("idle", "between_tasks"))

    def test_a_save_the_stop_line_asked_for_is_learning_until_that_turn_ends(self):
        ended = {**working(FRONTIER), "task_end": {"task_id": "t1"}}
        ask = {"task_id": "t1", "answered": False, "ask": "stop"}
        self.assertEqual(self.state({**ended, "auto_ask": ask}), ("learning", "save_asked"))
        self.assertEqual(self.state({**ended, "auto_ask": {**ask, "closed": True}}), ("idle", "between_tasks"))
        self.assertEqual(self.state({**ended, "auto_ask": {**ask, "ask": "guide"}}), ("idle", "between_tasks"))

    def test_a_task_that_stopped_moving_long_ago_is_not_shown(self):
        session.save("u1", working(APPLY, task_loaded=["ship"], task_delivery="piece"))
        old = time.time() - indicator.STALE_S - 5
        os.utime(session._file("u1"), (old, old))
        self.assertEqual(indicator.compute("u1"), ("idle", "stale_task"))


class EventsTest(HookCase):
    def test_one_ui_event_per_change_and_none_while_it_stays(self):
        session.save("u1", working(APPLY, task_loaded=["ship"], task_delivery="piece"))
        for _ in range(5):
            indicator.observe("u1")
        mark = indicator._file("u1").stat().st_mtime_ns
        for _ in range(5):
            indicator.observe("u1")
        self.assertEqual(indicator._file("u1").stat().st_mtime_ns, mark)          # polls write nothing
        session.update("u1", task_end={"task_id": "t1"})
        indicator.observe("u1")
        indicator.observe("u1")
        self.assertEqual([(e["from"], e["state"], e["why"]) for e in events("ui")],
                         [("idle", "collaborating", "piece_delivered"), ("collaborating", "idle", "between_tasks")])

    def test_status_carries_the_state_and_the_ui_poll_only_the_state_in_the_minimal_interface(self):
        sid = "u1"
        cwd = str(self.alpha)
        cli._remember_session({"cwd": cwd, "session_id": sid})
        session.save(sid, working(APPLY, task_loaded=["ship"], task_delivery="piece"))
        with mock.patch.object(os, "getcwd", return_value=cwd):
            full = cli.status()
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["status", "--ui"])
            brief = json.loads(out.getvalue())
            self.classic()
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["status", "--ui"])
            classic = json.loads(out.getvalue())
        self.assertEqual((full["state"], full["why"], full["ui"]), ("collaborating", "piece_delivered", "minimal"))
        self.assertEqual(set(brief), {"state", "why", "ui", "lang"})
        self.assertEqual((classic["ui"], classic["state"]), ("classic", "collaborating"))
        self.assertIn("trail", classic)
        self.assertEqual(len(events("ui")), 1)

    def test_the_interface_is_read_from_the_environment_then_the_config(self):
        self.assertEqual(indicator.mode(), "minimal")
        Path(self.home, "config.json").write_text(json.dumps({"ui": "classic"}))
        self.assertEqual(indicator.mode(), "classic")
        with mock.patch.dict(os.environ, {"ATHOS_UI": "minimal"}):
            self.assertEqual(indicator.mode(), "minimal")
        Path(self.home, "config.json").write_text(json.dumps({"ui": "fancy"}))
        self.assertEqual(indicator.mode(), "minimal")


def visible(answer):
    """What of a hook's answer the person reads in Claude Code: anything but extra context of the hooks whose context
    is hidden (SessionStart, UserPromptSubmit, PostToolUse, PostToolUseFailure)."""
    if answer is None:
        return None
    hidden = {"SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure"}
    spec = answer.get("hookSpecificOutput") or {}
    if set(answer) == {"hookSpecificOutput"} and spec.get("hookEventName") in hidden:
        return None
    return answer


class _Session(HookCase):
    """A whole session through the hooks, in this process, in an interactive Claude Code session."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, INTERACTIVE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ev = {"session_id": "h1", "cwd": str(self.alpha), "transcript_path": None}
        self.answers = []

    def send(self, name, **payload):
        out = self.hook(name, {**self.ev, **payload})
        self.answers.append((name, out))
        return out

    def states(self):
        return [(e["from"], e["state"]) for e in events("ui")]

    def seen(self):
        return [(name, visible(a)) for name, a in self.answers if visible(a) is not None]


class HandRunTest(_Session):
    """The exit criteria: the hooks, run by hand, move the state and write one `ui` event per change."""

    def test_idle_learning_idle_on_a_frontier_task_with_evidence(self):
        self.send("session-start", model=FRONTIER)
        self.send("prompt", prompt="fix the parser and add a test", model=FRONTIER)
        self.assertEqual(indicator.compute("h1")[0], "idle")
        self.send("tool", tool_name="Edit", tool_input={"file_path": "x.py"})
        self.send("tool", **UNITTEST)
        self.assertEqual(indicator.compute("h1"), ("learning", "gathering_evidence"))
        self.send("tool", **UNITTEST)
        self.send("stop", model=FRONTIER)
        self.assertEqual(self.states(), [("idle", "learning"), ("learning", "idle")])
        self.assertEqual(self.seen(), [])

    def test_idle_collaborating_idle_on_an_apply_model_given_a_piece(self):
        piece("ship-release", "Ship a release with the checklist", "shipping a release of the app", ["alpha"], BODY)
        self.send("session-start", model=APPLY)
        self.send("prompt", prompt="please ship the release of the app", model=APPLY)
        self.assertEqual(indicator.compute("h1"), ("collaborating", "piece_delivered"))
        self.send("tool", tool_name="Edit", tool_input={"file_path": "x.py"})
        self.send("stop", model=APPLY)
        self.send("prompt", prompt="what time is it", model=APPLY)                    # nothing matched
        self.send("stop", model=APPLY)
        self.assertEqual(self.states(), [("idle", "collaborating"), ("collaborating", "idle")])
        self.assertEqual(self.seen(), [])

    def test_idle_collaborating_idle_on_a_frontier_model_opening_a_piece(self):
        piece("ship-release", "Ship a release with the checklist", "shipping a release of the app", ["alpha"], BODY)
        self.send("session-start", model=FRONTIER)
        self.send("prompt", prompt="please ship the release of the app", model=FRONTIER)
        self.assertEqual(indicator.compute("h1")[0], "idle")                          # only offered in the index
        self.send("tool", tool_name="Bash", tool_input={"command": "athos show ship-release"})
        self.assertEqual(indicator.compute("h1"), ("collaborating", "piece_opened"))
        self.send("tool", tool_name="Edit", tool_input={"file_path": "x.py"})
        self.send("tool", **UNITTEST)                                                  # collaborating wins
        self.send("stop", model=FRONTIER)
        self.assertEqual(self.states(), [("idle", "collaborating"), ("collaborating", "idle")])
        self.assertEqual(self.seen(), [])


PIECE = """---
title: Change the parser safely
when: changing the parser of this project
---
## #test_first
**When:** before touching the parser.
**Do:** add a failing case to `tests/test_parser.py`.
**Check:** `python3 -m unittest tests.test_parser`
"""


class SilentTest(_Session):
    """In the minimal interface, nothing a hook answers reaches the person's eyes: not on the learn path, the save
    path or the verify path, in Claude Code or in the other agents."""

    def frontier_task(self):
        self.send("session-start", model=FRONTIER)
        self.send("prompt", prompt="fix the parser and add a test", model=FRONTIER)
        for _ in range(4):
            self.send("tool", tool_name="Edit", tool_input={"file_path": "x.py"})
        self.send("tool", **UNITTEST)

    def test_learn_path_the_stop_hook_records_and_says_nothing(self):
        self.frontier_task()
        self.assertIsNone(self.send("stop", model=FRONTIER))
        learn = [e for e in events() if e.get("type") == "learn"]
        self.assertEqual([(e["decision"], e["ask"]) for e in learn], [("qualified", "guide")])
        self.send("prompt", prompt="thanks", model=FRONTIER)
        self.assertEqual(self.seen(), [])
        # The audit says whether the model saves on its own: here it qualified and saved nothing.
        from athos import audit
        report = audit.check("h1", [e for e in events() if e.get("session_id") == "h1"], cwd=str(self.alpha))
        learning = report["summary"]["learning"]
        self.assertEqual((learning["qualified"], learning["saved"], learning["saved_nothing"],
                          learning["without_guide"]), (1, 0, 1, 0))
        self.assertIn("learning on its own: 0 saved · 1 task(s) qualified",
                      audit.render({"sessions": [{**report, "anomalies": 0}]}))

    def test_save_and_verify_path_say_nothing_to_the_person(self):
        from athos import verify
        self.frontier_task()
        out = io.StringIO()
        spawned = []
        with mock.patch.object(os, "getcwd", return_value=str(self.alpha)), redirect_stdout(out), \
                mock.patch.object(verify, "spawn", side_effect=lambda *a, **k: spawned.append(a) or True), \
                mock.patch("sys.stdin", io.StringIO(PIECE)):
            cli.main(["save", "--auto"])
        self.assertIn("as a candidate of alpha", out.getvalue())                       # the model's tool output
        self.assertTrue(spawned)
        self.assertTrue(session.load("h1").get("verifying_since"))
        self.send("tool", tool_name="Bash", tool_input={"command": "athos save --auto <<'EOF'"})
        verify.root().mkdir(parents=True, exist_ok=True)
        verify._lock().write_text("1")                                                  # the verifier runs
        self.assertIsNone(self.send("stop", model=FRONTIER))
        self.assertEqual(indicator.compute("h1"), ("learning", "verifying"))
        verify.release_lock()
        indicator.observe("h1")
        self.assertEqual(self.states(), [("idle", "learning"), ("learning", "idle")])
        self.assertEqual(self.seen(), [])

    def test_the_persons_own_save_path_offers_nothing_in_sight(self):
        # A model of unknown tier keeps the save from before tiers: in the classic interface the band offers [Save];
        # in the minimal one the task is only recorded as worth offering.
        self.send("session-start")
        self.send("prompt", prompt="fix the parser and add a test")
        for _ in range(5):
            self.send("tool", tool_name="Edit", tool_input={"file_path": "x.py"})
        self.assertIsNone(self.send("stop"))
        self.assertEqual(self.seen(), [])
        opening = self.answers[0][1]["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("[Save]", opening)
        self.assertNotIn("Stop hook asks", opening)

    def test_other_agents_get_no_stop_line_either(self):
        self.send("session-start")
        self.send("prompt", prompt="fix the parser and add a test")
        for _ in range(5):
            self.send("tool", tool_name="Edit", tool_input={"file_path": "x.py"})
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(self.ev))), redirect_stdout(out):
            cli.hook("stop", "codex")
        self.assertEqual(out.getvalue().strip(), "")

    def test_the_classic_interface_keeps_the_old_lines(self):
        self.classic()
        Path(self.home, "config.json").write_text(json.dumps({"autolearn": {"ask": "stop"}}))
        self.frontier_task()
        said = visible(self.send("stop", model=FRONTIER))
        self.assertIn("save --auto", said["hookSpecificOutput"]["additionalContext"])

    def test_the_stop_line_is_a_setting_independent_of_the_interface(self):
        Path(self.home, "config.json").write_text(json.dumps({"autolearn": {"ask": "stop"}}))
        self.frontier_task()
        self.assertIsNotNone(visible(self.send("stop", model=FRONTIER)))


class OffersTest(HookCase):
    """The offers the model would pass on to the person (a cheaper model, the overnight review, a rule from an edit)
    stay out of the minimal interface; the MCP panel no longer opens on its own."""

    def test_the_trail_panel_does_not_open_unasked_in_desktops_chat(self):
        from athos import mcp
        with mock.patch.object(mcp, "draws_apps", return_value=True):
            tools = {t["name"]: t for t in mcp.tools()}
            self.assertNotIn("_meta", tools["athos_find"])
            self.assertNotIn("_meta", tools["athos_done"])
            self.assertEqual(tools["athos_library"]["_meta"]["ui"]["resourceUri"], mcp.LIBRARY_URI)
            self.classic()
            tools = {t["name"]: t for t in mcp.tools()}
            self.assertEqual(tools["athos_find"]["_meta"]["ui"]["resourceUri"], mcp.UI_URI)
