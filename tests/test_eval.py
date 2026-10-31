"""The local task log in athos/eval: recording tasks, judging them, and the report built from them."""

import datetime as dt
import json
import os
import tempfile
from contextlib import contextmanager
from unittest import mock

from athos import capture, eval as ev, load, session, store
from tests.helpers import TempHome

RELEASE_PIECE = "---\ntitle: Cut a release\nwhen: release a new version: bump, changelog, tag\n---\nBump both places."


@contextmanager
def frozen_at(moment):
    """Make the log believe it is `moment`."""
    with mock.patch.object(ev, "now", return_value=moment):
        yield


def write_transcript(path, origin, replies):
    """Write a Claude Code style transcript. `replies` holds (seconds after origin, output tokens); like the real
    thing, each reply shows up on two lines that share an id and its usage."""
    rows = []
    for n, (offset, produced) in enumerate(replies):
        stamp = (origin + dt.timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")
        usage = {"input_tokens": 10, "output_tokens": produced, "cache_read_input_tokens": 100}
        line = json.dumps({"type": "assistant", "timestamp": stamp,
                           "message": {"id": f"reply-{n}", "model": "claude-opus-5-5", "usage": usage}})
        rows += [line, line]
    with open(path, "w") as out:
        out.write("\n".join(rows) + "\n")


class LogTestCase(TempHome):
    def work(self, sid, prompt, *, seconds=60, saving=None, verdict=None):
        """One request through the hooks: start, load, maybe save a piece, stop after `seconds`, maybe judge."""
        began = ev.now()
        with frozen_at(began):
            ev.task_start({"session_id": sid, "prompt": prompt, "cwd": self.home})
        load.on_prompt({"session_id": sid, "prompt": prompt})
        if saving:
            capture.save_text(saving, sid)
        with frozen_at(began + dt.timedelta(seconds=seconds)):
            ended = ev.task_end({"session_id": sid})
        if verdict:
            ev.mark(verdict, session_id=sid)
        return ended


class Recording(LogTestCase):
    def test_a_finished_task_has_its_duration_and_no_verdict_yet(self):
        session.update("alpha", model="claude-opus-5-5")
        self.assertEqual(self.work("alpha", "do something", seconds=42)["duration_s"], 42)
        only = ev.tasks()[0]
        self.assertEqual(only["result"], "unevaluated")
        self.assertEqual(only["model"], "claude-opus-5-5")
        self.assertEqual(only["platform"], "claude-code")

    def test_transcript_tokens_count_each_reply_once_and_only_within_the_task(self):
        origin = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "session.jsonl")
            write_transcript(path, origin, [(-30, 999), (5, 50), (20, 70)])     # the first reply predates the task
            counted = ev.tokens_between(path, origin.isoformat(), (origin + dt.timedelta(minutes=1)).isoformat())
        self.assertEqual((counted["output"], counted["cache_read"]), (50 + 70, 2 * 100))
        self.assertEqual(counted["total"], 120 + 2 * 10 + 200)

    def test_no_tokens_without_a_readable_transcript(self):
        for missing in (None, "/nonexistent"):
            self.assertIsNone(ev.tokens_between(missing, "", ""))

    def test_a_second_stop_for_the_capture_leaves_the_baseline_alone(self):
        began = ev.now()
        with frozen_at(began):
            ev.task_start({"session_id": "alpha", "prompt": "first release"})
        with frozen_at(began + dt.timedelta(seconds=50)):
            ev.task_end({"session_id": "alpha"})                  # work done; Athos now asks for a capture
        capture.save_text(RELEASE_PIECE, "alpha")
        with frozen_at(began + dt.timedelta(seconds=90)):
            ev.task_end({"session_id": "alpha"})                  # the stop after capturing
        only = ev.tasks()[0]
        self.assertEqual(only["duration_s"], 50)
        self.assertEqual(only["saved"], [store.all_pieces()[0].id])

    def test_tasks_run_elsewhere_are_logged_and_judged(self):
        store.create("A", "aaa", "b")
        ev.record_external("local", "gemma4:12b", ["a"], 3.5, None, "g")
        model = ev.report()["models"][0]
        self.assertEqual((model["platform"], model["model"], model["success_rate"]), ("local", "gemma4:12b", 1.0))


class Verdicts(LogTestCase):
    def test_bad_verdicts_and_an_empty_log_are_refused(self):
        with self.assertRaises(LookupError):
            ev.mark("g")
        self.work("alpha", "x")
        with self.assertRaises(ValueError):
            ev.mark("maybe")

    def test_a_later_verdict_replaces_an_earlier_one(self):
        self.work("alpha", "x")
        for verdict in ("f", "g"):
            ev.mark(verdict, session_id="alpha")
        self.assertEqual(ev.tasks()[0]["result"], "ok")

    def test_a_bare_mark_judges_the_latest_task_of_this_project(self):
        # Seen while rehearsing the demo: a mark right after a Codex task landed on the earlier Claude Code task.
        with frozen_at(ev.now()):
            ev.task_start({"session_id": "claude", "prompt": "a", "cwd": "/nonexistent/greet-claude"})
            ev.task_end({"session_id": "claude"})
        codex_task = ev.record_external("codex", "gpt", [], 30, None, project="greet-codex")
        # In the Codex folder there is no Claude Code session, so the project points at the Codex task...
        self.assertEqual(ev.mark("g", session_id=None, project="greet-codex")[0], codex_task)
        # ...while inside the Claude Code session, in its own folder, the session's task is the one judged.
        self.assertNotEqual(ev.mark("g", session_id="claude", project="greet-claude")[0], codex_task)


class Reporting(LogTestCase):
    def test_success_rates_baseline_and_time_saved(self):
        session.update("alpha", model="claude-opus-5-5")
        self.work("alpha", "first release", saving=RELEASE_PIECE, verdict="g", seconds=300)
        later = [("release 0.3.0 now", "g", 100), ("another release please", "c", 140), ("release again", None, 90)]
        for prompt, verdict, seconds in later:
            self.work("alpha", prompt, verdict=verdict, seconds=seconds)
        result = ev.report()
        piece, model = result["pieces"][0], result["models"][0]
        self.assertEqual((piece["uses"], piece["evaluated"], piece["success_rate"]), (3, 2, 0.5))
        self.assertEqual(piece["baseline"]["duration_s"], 300)
        self.assertAlmostEqual(piece["time_saved_s"], 300 - (100 + 140 + 90) / 3)
        self.assertEqual((model["model"], model["tasks"], model["evaluated"]), ("claude-opus-5-5", 4, 3))
        self.assertAlmostEqual(model["success_rate"], 2 / 3)

    def test_loading_a_piece_and_saving_its_next_version_is_still_a_use(self):
        # From a real session: the second run loaded the piece, saved its v2, and was not counted as using it.
        session.update("alpha", model="m")
        self.work("alpha", "first release", saving=RELEASE_PIECE, seconds=200)
        pid = store.all_pieces()[0].id
        self.work("alpha", "release 0.3.0", saving=f"---\nid: {pid}\nnote: more\n---\nBump both places. Tag too.",
                  seconds=80)
        piece = ev.report()["pieces"][0]
        self.assertEqual((piece["uses"], piece["baseline"]["duration_s"]), (1, 200))
        self.assertAlmostEqual(piece["time_saved_s"], 120)

    def test_idle_and_failing_pieces_are_put_up_for_review(self):
        store.create("Old", "legacy archive cleanup", "x")
        failing = store.create("Bad", "bad thing to do", "x")
        session.update("alpha", model="m")
        for _ in range(3):
            self.work("alpha", "bad thing to do", verdict="f")
        idle = store.get("old")
        idle.last_used = (dt.date.today() - dt.timedelta(days=20)).isoformat()
        store._write(idle)

        def flags(day):
            return {row["piece"]: row["review"] for row in ev.report(day)["pieces"]}

        today = flags(dt.date.today())
        self.assertIn("low success", today[failing.id])
        self.assertIn("not used in 14 days", today["old"])
        self.assertIn("not used in 14 days", flags(dt.date.today() + dt.timedelta(days=30))[failing.id])

    def test_an_empty_log_prints_no_made_up_figures(self):
        text = ev.render(ev.report())
        for expected in ("0 task(s)", "(none yet)"):
            self.assertIn(expected, text)


class PlainWords(TempHome):
    def test_the_next_words_mark_the_previous_task_when_they_plainly_judge_it(self):
        from athos import eval as ev, session
        tid = ev.task_start({"session_id": "s1", "prompt": "release it", "cwd": self.home})
        self.assertIsNone(ev.infer_mark("s1", "mergea 50"))                  # no judgement: no mark
        self.assertEqual(ev.infer_mark("s1", "ok excelente, ahora el changelog"), "ok")
        self.assertIsNone(ev.infer_mark("s1", "excelente"))                  # already marked: once
        ev.task_start({"session_id": "s1", "prompt": "now the docs", "cwd": self.home})
        self.assertEqual(ev.infer_mark("s1", "el título está mal, cambialo"), "corrected")
        marks = [e for e in ev.events() if e["type"] == "mark"]
        self.assertEqual([(m["task_id"] == tid, m["by"]) for m in marks][:1], [(True, "inferred")])
        self.assertTrue(session.load("s1")["task_id"])

    def test_a_pieces_record_counts_uses_marks_and_agents(self):
        from athos import eval as ev
        tasks = [{"pieces": ["p"], "result": "ok", "platform": "claude-code"},
                 {"pieces": ["p"], "result": "unevaluated", "platform": "opencode"},
                 {"pieces": ["q"], "result": "ok", "platform": "codex"}]
        self.assertEqual(ev.record("p", tasks), {"uses": 2, "ok": 1, "marked": 1, "agents": ["Claude Code", "OpenCode"]})

    def test_only_recent_tasks_wait_for_a_mark(self):
        from athos import eval as ev
        self.assertTrue(ev.recent({"started": ev._iso(ev.now())}))
        self.assertFalse(ev.recent({"started": "2026-01-01T00:00:00+00:00"}))


class Language(TempHome):
    def test_the_language_the_person_writes_in_when_none_was_chosen(self):
        from athos import start
        self.assertEqual(start.lang(), "en")
        start.note_language("mergea 50")                                     # too little to tell
        self.assertEqual(start.lang(), "en")
        start.note_language("dime como viene la corrida y que falta para el PR")
        self.assertEqual(start.lang(), "es")
        start.save_choice("en", "other")                                     # a choice always wins
        start.note_language("dime como viene la corrida y que falta para el PR")
        self.assertEqual(start.lang(), "en")
