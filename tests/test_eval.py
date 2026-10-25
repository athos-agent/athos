import datetime as dt
import json
import os
import tempfile
from unittest import mock

from athos import capture, eval as ev, load, session, store
from tests.helpers import TempHome

PIECE = "---\ntitle: Cut a release\nwhen: release a new version: bump, changelog, tag\n---\nBump both places."


def transcript(path, start, replies):
    """A transcript like Claude Code's: each reply repeated on several lines with the same id and usage."""
    with open(path, "w") as fh:
        for i, (secs, out) in enumerate(replies):
            ts = (start + dt.timedelta(seconds=secs)).isoformat().replace("+00:00", "Z")
            for _ in range(2):
                fh.write(json.dumps({"type": "assistant", "timestamp": ts,
                                     "message": {"id": f"m{i}", "model": "claude-opus-5-5",
                                                 "usage": {"input_tokens": 10, "output_tokens": out,
                                                           "cache_read_input_tokens": 100}}}) + "\n")


class EvalTest(TempHome):
    def run_task(self, sid, prompt, save=None, mark=None, seconds=60):
        t0 = ev.now()
        with mock.patch.object(ev, "now", return_value=t0):
            ev.task_start({"session_id": sid, "prompt": prompt, "cwd": self.home})
        load.on_prompt({"session_id": sid, "prompt": prompt})
        if save:
            capture.save_text(save, sid)
        with mock.patch.object(ev, "now", return_value=t0 + dt.timedelta(seconds=seconds)):
            rec = ev.task_end({"session_id": sid})
        if mark:
            ev.mark(mark, session_id=sid)
        return rec

    def test_a_task_is_recorded_with_duration_and_unevaluated_by_default(self):
        session.update("s1", model="claude-opus-5-5")
        rec = self.run_task("s1", "do something", seconds=42)
        self.assertEqual(rec["duration_s"], 42)
        t = ev.tasks()[0]
        self.assertEqual((t["result"], t["model"], t["platform"]), ("unevaluated", "claude-opus-5-5", "claude-code"))

    def test_tokens_come_from_the_transcript_once_per_reply_and_only_inside_the_task(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            t0 = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
            transcript(p, t0, [(-30, 999), (5, 50), (20, 70)])            # the first reply is before the task
            tok = ev.tokens_between(p, t0.isoformat(), (t0 + dt.timedelta(seconds=60)).isoformat())
        self.assertEqual(tok["output"], 120)
        self.assertEqual(tok["cache_read"], 200)
        self.assertEqual(tok["total"], 120 + 20 + 200)

    def test_tokens_are_none_when_unreadable(self):
        self.assertIsNone(ev.tokens_between(None, "", ""))
        self.assertIsNone(ev.tokens_between("/nonexistent", "", ""))

    def test_marks_and_success_rates(self):
        session.update("s1", model="claude-opus-5-5")
        self.run_task("s1", "first release", save=PIECE, mark="g", seconds=300)
        self.run_task("s1", "release 0.3.0 now", mark="g", seconds=100)
        self.run_task("s1", "another release please", mark="c", seconds=140)
        self.run_task("s1", "release again", seconds=90)                                     # never marked
        r = ev.report()
        p = r["pieces"][0]
        self.assertEqual((p["uses"], p["evaluated"]), (3, 2))
        self.assertEqual(p["success_rate"], 0.5)
        self.assertEqual(p["baseline"]["duration_s"], 300)
        self.assertAlmostEqual(p["time_saved_s"], 300 - (100 + 140 + 90) / 3)
        m = r["models"][0]
        self.assertEqual((m["model"], m["tasks"], m["evaluated"]), ("claude-opus-5-5", 4, 3))
        self.assertAlmostEqual(m["success_rate"], 2 / 3)

    def test_a_task_that_uses_and_improves_a_piece_counts_as_a_use(self):
        # Found in a real run: the second session loaded the piece and saved v2 of it; it was not counted as a use.
        session.update("s1", model="m")
        self.run_task("s1", "first release", save=PIECE, seconds=200)
        pid = store.all_pieces()[0].id
        self.run_task("s1", "release 0.3.0", save=f"---\nid: {pid}\nnote: more\n---\nBump both places. Tag too.",
                      seconds=80)
        p = ev.report()["pieces"][0]
        self.assertEqual(p["uses"], 1)
        self.assertEqual(p["baseline"]["duration_s"], 200)
        self.assertAlmostEqual(p["time_saved_s"], 120)

    def test_the_capture_after_the_first_stop_does_not_inflate_the_baseline(self):
        t0 = ev.now()
        with mock.patch.object(ev, "now", return_value=t0):
            ev.task_start({"session_id": "s1", "prompt": "first release"})
        with mock.patch.object(ev, "now", return_value=t0 + dt.timedelta(seconds=50)):
            ev.task_end({"session_id": "s1"})                         # the work is done; Athos asks for a capture
        capture.save_text(PIECE, "s1")
        with mock.patch.object(ev, "now", return_value=t0 + dt.timedelta(seconds=90)):
            ev.task_end({"session_id": "s1"})                         # after the capture
        t = ev.tasks()[0]
        self.assertEqual(t["duration_s"], 50)
        self.assertEqual(t["saved"], [store.all_pieces()[0].id])

    def test_mark_rejects_unknown_results_and_missing_tasks(self):
        with self.assertRaises(LookupError):
            ev.mark("g")
        self.run_task("s1", "x")
        with self.assertRaises(ValueError):
            ev.mark("maybe")

    def test_the_last_mark_wins(self):
        self.run_task("s1", "x")
        ev.mark("f", session_id="s1")
        ev.mark("g", session_id="s1")
        self.assertEqual(ev.tasks()[0]["result"], "ok")

    def test_pieces_to_review(self):
        store.create("Old", "legacy archive cleanup", "x")
        p = store.create("Bad", "bad thing to do", "x")
        session.update("s1", model="m")
        for _ in range(3):
            self.run_task("s1", "bad thing to do", mark="f")
        later = dt.date.today() + dt.timedelta(days=30)
        old = store.get("old")
        old.last_used = (dt.date.today() - dt.timedelta(days=20)).isoformat()
        store._write(old)
        r = ev.report(dt.date.today())
        flags = {x["piece"]: x["review"] for x in r["pieces"]}
        self.assertIn("low success", flags[p.id])
        self.assertIn("not used in 14 days", flags["old"])
        self.assertIn("not used in 14 days", {x["piece"]: x["review"] for x in ev.report(later)["pieces"]}[p.id])

    def test_external_platforms_are_recorded_too(self):
        store.create("A", "aaa", "b")
        ev.record_external("local", "gemma4:12b", ["a"], 3.5, None, "g")
        m = ev.report()["models"][0]
        self.assertEqual((m["platform"], m["model"], m["success_rate"]), ("local", "gemma4:12b", 1.0))

    def test_render_has_no_invented_numbers(self):
        text = ev.render(ev.report())
        self.assertIn("0 task(s)", text)
        self.assertIn("(none yet)", text)
