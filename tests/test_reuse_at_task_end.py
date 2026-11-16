"""A task's reuses are graded when the task ends (the Stop hook), not when the person's next request arrives: a session
with one request, and the last task of any session, are graded too. The person's next words and edits arrive later and
amend that grading; a task that ended without being graded (a killed session, an older version) is caught up at the
next session start in the same project. Synthetic pieces and events only."""

import json
import os
from unittest import mock

from athos import eval as ev, evidence, grade, session, store
from tests.helpers import TempHome
from tests.test_autolearn import BODY, StubRunner, candidate

PASS = {"type": "verify", "kind": "test", "label": "unittest", "ok": True, "strength": "strong", "polarity": "positive"}


def reuses(pid=None):
    return [e for e in ev.events() if e.get("type") == "reuse" and (pid is None or e.get("piece") == pid)]


def passed_candidate(task="t0"):
    """A learned candidate the verifier passed, written in another session (s0)."""
    from athos import verify
    p = candidate(task=task)
    verify.run(p.id, verify.build_bundle(p, task, None), StubRunner())
    return store.get(p.id)


class _Hooks(TempHome):
    """Single-request headless sessions through the hooks, in a project folder named demo."""

    def setUp(self):
        super().setUp()
        from tests.test_cli import ThroughTheLauncher
        self.cli = ThroughTheLauncher()
        self.cli.home, self.cli.assertEqual = self.home, self.assertEqual
        self.work = os.path.join(self.home, "work", "demo")
        os.makedirs(self.work)

    def reuse_session(self, sid, piece_id, model="claude-opus-5-5", verify=True, stop=True):
        ev_ = {"session_id": sid, "cwd": self.work, "transcript_path": None}
        self.cli.send("session-start", {**ev_, "model": model})
        self.cli.send("prompt", {**ev_, "prompt": "change the parser and add a test"})
        self.cli.send("tool", {**ev_, "tool_name": "Bash", "tool_input": {"command": f"athos show {piece_id}"},
                               "tool_response": {"stdout": "", "stderr": "", "interrupted": False}})
        self.cli.send("tool", {**ev_, "tool_name": "Edit", "tool_input": {"file_path": "x.py"}})
        if verify:
            self.cli.send("tool", {**ev_, "tool_name": "Bash", "tool_input": {"command": "python3 -m unittest -q"},
                                   "tool_response": {"stdout": "OK", "stderr": "", "interrupted": False}})
        if stop:
            self.cli.send("stop", ev_)
        return ev_


class GradedAtTheEndTest(_Hooks):
    def test_a_single_request_session_is_graded_at_its_own_end(self):
        p = passed_candidate()
        self.reuse_session("r1", p.id)
        [e] = reuses(p.id)                                     # no next request came: graded at the Stop hook
        self.assertEqual((e["outcome"], e["tier"], e["session_id"], e["verdict"]), ("clean", "frontier", "r1", "pass"))
        self.assertEqual(e.get("stage"), "stop")

    def test_two_single_request_sessions_verify_the_piece(self):
        p = passed_candidate()
        self.reuse_session("r1", p.id)
        self.assertEqual(store.get(p.id).status, "candidate")
        self.reuse_session("r2", p.id)
        self.assertEqual(store.get(p.id).status, "verified")
        self.assertEqual(len(reuses(p.id)), 2)

    def test_without_strong_evidence_the_reuse_does_not_count(self):
        p = passed_candidate()
        self.reuse_session("r1", p.id, verify=False)
        [e] = reuses(p.id)
        self.assertEqual(e["outcome"], "unverified")

    def test_a_second_stop_of_the_same_task_writes_no_second_reuse(self):
        p = passed_candidate()
        ev_ = self.reuse_session("r1", p.id)
        self.cli.send("stop", {**ev_, "stop_hook_active": True})
        self.assertEqual(len(reuses(p.id)), 1)

    def test_the_next_request_amends_and_never_adds_a_reuse(self):
        p = passed_candidate()
        ev_ = self.reuse_session("r1", p.id)
        before = store.confidence(store.get(p.id))
        self.cli.send("prompt", {**ev_, "prompt": "no funciona, the parser is wrong"})
        mine = reuses(p.id)
        self.assertEqual([e["outcome"] for e in mine], ["clean", "unverified"])
        self.assertEqual(mine[-1]["amends"], "clean")
        self.assertIn("reaction_corrected", mine[-1]["basis"])
        self.assertLess(store.confidence(store.get(p.id)), before)            # words: confidence only
        self.assertEqual(store.get(p.id).status, "candidate")
        self.assertEqual(grade.standing(store.get(p.id))["frontier_clean"], 0)   # one piece of work, one reuse
        self.assertEqual(len(grade.counted_reuses(reuses(p.id))), 1)

    def test_an_apply_model_session_is_graded_at_its_end_too(self):
        p = passed_candidate()
        store.set_status(p.id, "verified", "test")
        self.reuse_session("a1", p.id, model="claude-haiku-5-5")
        [e] = reuses(p.id)
        self.assertEqual(e["tier"], "apply")


class AmendmentTest(TempHome):
    def test_a_person_edit_found_later_turns_a_clean_reuse_into_a_correction(self):
        p = passed_candidate()
        evidence.add("t1", dict(PASS))
        state = {"task_loaded": [p.id], "task_saved": [], "saved": [], "model": "claude-opus-5-5"}
        [first] = grade.finish_task("s1", "t1", state)
        self.assertEqual(first["outcome"], "clean")
        evidence.add("t1", dict(PASS))
        evidence.note_person_edits([{"task_id": "t1", "piece": p.id, "file_sha": "f", "basis": ["changed"]}])
        [second] = grade.finish_task("s1", "t1", state, stage="next_request")
        self.assertEqual((second["outcome"], second["amends"]), ("corrected", "clean"))
        self.assertEqual(grade.finish_task("s1", "t1", state, stage="next_request"), [])   # nothing new: nothing
        self.assertEqual([e["outcome"] for e in grade.counted_reuses(reuses(p.id))], ["corrected"])

    def test_a_verified_piece_promoted_at_the_stop_is_demoted_by_a_later_tied_edit(self):
        p = passed_candidate()
        state = lambda sid: {"task_loaded": [p.id], "task_saved": [], "saved": [], "model": "claude-opus-5-5"}
        for task, sid in (("t1", "s1"), ("t2", "s2")):
            evidence.add(task, dict(PASS))
            grade.finish_task(sid, task, state(sid))
        self.assertEqual(store.get(p.id).status, "verified")
        evidence.note_person_edits([{"task_id": "t2", "piece": p.id, "file_sha": "f", "basis": ["changed"]}])
        grade.finish_task("s2", "t2", state("s2"), stage="next_request")
        self.assertEqual(store.get(p.id).status, "candidate")

    def test_a_piece_improved_later_in_the_same_session_loses_that_reuse(self):
        p = passed_candidate()
        evidence.add("t1", dict(PASS))
        state = {"task_loaded": [p.id], "task_saved": [], "saved": [], "model": "claude-opus-5-5"}
        grade.finish_task("s1", "t1", state)
        grade.finish_task("s1", "t1", {**state, "saved": [p.id]})
        self.assertEqual([e["outcome"] for e in grade.counted_reuses(reuses(p.id))], ["unverified"])

    def test_the_writing_session_and_a_failed_verdict_still_do_not_count(self):
        from athos import verify
        p = candidate(task="t0")
        verify.run(p.id, verify.build_bundle(p, "t0", None), StubRunner(text=json.dumps(
            {c: {"pass": False, "why": "no"} for c in verify.CRITERIA})))
        evidence.add("t1", dict(PASS))
        [e] = grade.finish_task("s1", "t1", {"task_loaded": [p.id], "model": "claude-opus-5-5"})
        self.assertEqual((e["outcome"], e["verdict"]), ("clean", "fail"))
        self.assertEqual(grade.standing(store.get(p.id))["frontier_clean"], 0)     # under a failed verdict
        evidence.add("t2", dict(PASS))
        self.assertEqual(grade.finish_task("s0", "t2", {"task_loaded": [p.id], "saved": [p.id],
                                                        "model": "claude-opus-5-5"}), [])


class CatchUpTest(_Hooks):
    def _ended_ungraded(self, task, sid, piece_id, project="demo", model="claude-opus-5-5"):
        """What an older version, or a session killed before its next request, left: a task that ended, with its
        evidence, and no reuse event."""
        ev.append({"type": "task_start", "task_id": task, "session_id": sid, "platform": "claude-code",
                   "model": model, "project": project, "at": ev._iso(ev.now())})
        evidence.add(task, dict(PASS))
        ev.append({"type": "task_end", "task_id": task, "session_id": sid, "at": ev._iso(ev.now()),
                   "duration_s": 3.0, "tokens": None, "model": model, "pieces": [piece_id], "saved": []})

    def test_the_next_session_start_in_the_project_grades_what_was_left(self):
        p = passed_candidate()
        self._ended_ungraded("t1", "old1", p.id)
        self._ended_ungraded("t2", "old2", p.id, project="elsewhere")
        self.cli.send("session-start", {"session_id": "n1", "cwd": self.work, "transcript_path": None,
                                        "model": "claude-opus-5-5"})
        [e] = reuses(p.id)
        self.assertEqual((e["task_id"], e["outcome"], e["stage"]), ("t1", "clean", "catch_up"))
        self.cli.send("session-start", {"session_id": "n2", "cwd": self.work, "transcript_path": None,
                                        "model": "claude-opus-5-5"})
        self.assertEqual(len(reuses(p.id)), 1)                                 # once

    def test_catch_up_keeps_the_rules(self):
        p = passed_candidate()
        self._ended_ungraded("t1", "s0", p.id)                                 # the session that wrote it
        ev.append({"type": "task_end", "task_id": "t0", "session_id": "s0", "at": ev._iso(ev.now()),
                   "model": "claude-opus-5-5", "pieces": [], "saved": [p.id]})
        self._ended_ungraded("t3", "old3", p.id, model="unknown")               # a model never seen
        self.assertEqual(grade.catch_up("demo"), [])


class WaitingForTheCapTest(TempHome):
    """A candidate the daily cap left unverified is verified later without anyone asking: the first hook of the next
    day that may start a run (a session start or a Stop) starts it."""

    def test_the_next_day_it_starts_on_its_own(self):
        import datetime as dt
        from athos import start, verify
        start.config_file().write_text(json.dumps({"autolearn": {"budget": {"runs_per_day": 1}}}))
        first = candidate(task="t1")
        verify.run(first.id, verify.build_bundle(first, "t1", None), StubRunner())          # today's one run
        waiting = store.create("Bump the version", "bumping the version", BODY, projects=["demo"],
                               status="candidate", learned_by="claude-opus-5-5", confidence="0.3")
        evidence.add("t2", dict(PASS))
        spawned = []
        self.assertFalse(verify.after_save(waiting, {"task_id": "t2"}, None, verify.Path("athos"),
                                           lambda argv, **kw: spawned.append(argv)))
        self.assertIn("daily cap", [e for e in ev.events() if e.get("type") == "grade"][-1]["basis"])
        self.assertEqual([pid for pid, _ in verify.pending()], [waiting.id])
        self.assertFalse(verify.maybe_spawn_pending(verify.Path("athos"), lambda argv, **kw: spawned.append(argv)))
        tomorrow = ev.now() + dt.timedelta(days=1)
        with mock.patch.object(ev, "now", return_value=tomorrow):
            self.assertTrue(verify.maybe_spawn_pending(verify.Path("athos"),
                                                       lambda argv, **kw: spawned.append(argv)))
            self.assertIn("--pending", spawned[-1])
            out = verify.run_pending(StubRunner())
        self.assertEqual([(o["piece"], o["outcome"]) for o in out], [(waiting.id, "pass")])

    def test_a_session_start_starts_it_too(self):
        import io
        from contextlib import redirect_stdout
        from athos import cli, verify
        calls = []
        event = {"session_id": "n1", "cwd": self.home, "transcript_path": None, "model": "claude-opus-5-5"}
        with mock.patch.object(verify, "maybe_spawn_pending", side_effect=lambda *a, **k: calls.append(a) or True), \
                mock.patch("sys.stdin", io.StringIO(json.dumps(event))), redirect_stdout(io.StringIO()):
            cli.hook("session-start")
        self.assertEqual(len(calls), 1)
        self.assertTrue(session.load("n1").get("verifying_since"))


class AskNobodyAnsweredTest(TempHome):
    """A frontier task that qualified to keep what it taught and saved nothing, in a session that never sent another
    request: the next session start in the project records it, as that request would have, once."""

    def test_recorded_at_a_later_session_start_and_only_once(self):
        import datetime as dt
        from athos import autolearn
        long_ago = ev.now() - dt.timedelta(minutes=30)
        for task, sid, at in (("t1", "s1", long_ago), ("t2", "s2", ev.now())):
            ev.append({"type": "learn", "task_id": task, "session_id": sid, "decision": "qualified",
                       "project": "demo", "model": "claude-opus-5-5", "ask": "guide", "at": ev._iso(at)})
            ev.append({"type": "task_end", "task_id": task, "session_id": sid, "at": ev._iso(at), "pieces": [],
                       "saved": []})
        self.assertEqual(autolearn.catch_up("demo"), ["t1"])              # t2 just ended: its session may answer
        self.assertEqual(autolearn.catch_up("demo"), [])
        self.assertEqual(autolearn.catch_up("elsewhere"), [])
        [e] = [e for e in ev.events() if e.get("reason") == "model_saved_nothing"]
        self.assertEqual((e["task_id"], e["caught_up"]), ("t1", True))
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5",
                            "auto_ask": {"task_id": "t1", "answered": False, "ask": "guide"}})
        autolearn.on_next_request("s1")                                    # a late request: not twice
        self.assertEqual(len([e for e in ev.events() if e.get("reason") == "model_saved_nothing"]), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
