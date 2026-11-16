"""Edges of the dream cycle found by a second review: a filesystem without hard links, backups from long ago, lines
repeated across the cut, kills inside the sweep, torn lines, the lock without `flock`, a clock set back. Every line
written must end up in the history exactly once. All data here is synthetic."""

import json
import os
import threading
from unittest import mock

from athos import eval as ev, memory, paths
from athos.memory import cycle
from tests.test_memory_cycle import DAY, MemoryCase, stamp, task, write


def count(kind):
    ev._EVENTS_CACHE.clear()
    return sum(1 for e in ev.events() if e.get("type") == kind)


def later(days):
    return mock.patch.object(cycle, "_now", return_value=ev.now() + days * DAY)


class NoHardLinksTest(MemoryCase):
    def no_links(self):
        return mock.patch.object(cycle.os, "link", side_effect=OSError(45, "Operation not supported"))

    def test_a_line_written_into_the_old_file_a_moment_after_the_trim_is_kept(self):
        old = open(paths.events_file(), "a")
        real = os.replace
        timers = []

        def write_later():
            old.write(json.dumps({"type": "late_unlocked", "at": stamp(0)}) + "\n")
            old.flush()

        def replace(src, dst):
            done = real(src, dst)
            if str(dst).endswith("events.jsonl") and not timers:
                timers.append(threading.Timer(0.3, write_later))    # an older Athos, opened before, writes after
                timers[0].start()
            return done
        try:
            with self.no_links(), mock.patch.object(cycle.os, "replace", side_effect=replace):
                out = cycle.run()
        finally:
            for t in timers:
                t.join()
            old.close()
        self.assertEqual(count("late_unlocked"), 1)
        self.assertIn("hard links", out["replay"].get("no_links") or "")
        cycle.run()
        self.assertEqual(count("late_unlocked"), 1)
        replay = [e for e in ev.live_events() if e.get("type") == "memory_cycle" and e.get("phase") == "replay"]
        self.assertTrue(any("hard links" in (e.get("no_links") or "") for e in replay))

    def test_the_same_log_put_back_twice_never_reuses_a_trim_name(self):
        copy = paths.events_file().read_bytes()
        cycle.run()
        outcomes = []
        real = os.link

        def spy(a, b):
            try:
                done = real(a, b)
            except OSError as problem:
                outcomes.append(type(problem).__name__)
                raise
            outcomes.append("ok")
            return done
        with mock.patch.object(cycle.os, "link", side_effect=spy):
            for _ in range(3):
                paths.events_file().write_bytes(copy)
                cycle.replay_and_prune()
        self.assertEqual(outcomes, ["ok"] * 3)
        self.assertEqual(len({f.name for f in cycle.sidecars()}), len(cycle.sidecars()))


class OldBackupTest(MemoryCase):
    def archived(self):
        raw = b"".join(memory.read_segment(s) for s in memory.manifest()["segments"])
        return [line for line in raw.splitlines() if line.strip()]

    def archived_ends(self):
        return sum(1 for line in self.archived() if json.loads(line).get("type") == "task_end")

    def test_a_backup_ending_inside_a_segment_that_is_not_the_newest(self):
        full = paths.events_file().read_bytes()
        cycle.run()
        with later(22):
            cycle.run()
        with later(25):
            cycle.run()
        segs = memory.manifest()["segments"]
        self.assertGreaterEqual(len(segs), 3)
        lines_before, ends = len(self.archived()), self.archived_ends()
        second = memory.read_segment(segs[1]).splitlines(keepends=True)
        backup = full[:segs[0]["bytes"]] + b"".join(second[:len(second) // 2])
        self.assertTrue(full.startswith(backup))
        paths.events_file().write_bytes(backup)            # the log as a backup from before the second cut kept it
        self.assertEqual(count("task_end"), ends)            # read once, before any cycle
        with later(25):
            out = cycle.run()
        self.assertNotIn("refused", out["replay"])
        self.assertEqual(len(self.archived()), lines_before)     # nothing archived twice
        self.assertEqual(count("task_end"), ends)
        self.assertEqual(cycle.compare_rebuild()["ledger_equal"], True)

    def test_a_backup_ending_inside_the_newest_segment(self):
        cycle.run()
        first = memory.read_segment(memory.manifest()["segments"][0]).splitlines(keepends=True)
        lines_before, ends = len(self.archived()), self.archived_ends()
        paths.events_file().write_bytes(b"".join(first[:len(first) // 2]))
        self.assertEqual(count("task_end"), ends)
        outs = [cycle.run(auto=True) for _ in range(2)]
        self.assertFalse(any(o.get("stuck") or o["replay"].get("refused") for o in outs), outs)
        self.assertEqual(len(self.archived()), lines_before)
        self.assertEqual(count("task_end"), ends)
        self.assertNotIn(first[0], paths.events_file().read_bytes())

    def test_lines_of_an_older_segment_put_back_out_of_place_are_not_archived_again(self):
        cycle.run()
        with later(22):
            cycle.run()
        segs = memory.manifest()["segments"]
        self.assertEqual(len(segs), 2)
        before = self.archived()
        twins = len(before) - len(set(before))              # the fixture's own identical lines, archived together
        old = memory.read_segment(segs[0]).splitlines(keepends=True)
        paths.events_file().write_bytes(b"".join(old[5:9]) + paths.events_file().read_bytes())
        with later(25):
            cycle.run()
        archived = self.archived()
        self.assertEqual(len(archived) - len(set(archived)), twins)


class BareMarkTest(MemoryCase):
    def mark_in(self, folder, key="g"):
        import contextlib
        import io
        from athos import cli
        out = io.StringIO()
        with contextlib.chdir(folder), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = cli.main(["mark", key])
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue()

    def marks(self):
        return [(e["task_id"], e["result"]) for e in ev.live_events() if e.get("type") == "mark"
                and e.get("at", "") >= stamp(0.01)]

    def test_a_bare_mark_where_every_task_of_the_project_is_archived(self):
        cycle.run()
        code, out = self.mark_in(self.beta)                 # beta's only task is archived; alpha has recent ones
        self.assertEqual(self.marks()[-1:], [("old-beta", "ok")], out)

    def test_never_another_projects_task_when_all_are_archived(self):
        with later(40):
            cycle.run()
        self.mark_in(self.beta)
        self.mark_in(self.alpha, "c")
        got = dict(self.marks())
        self.assertEqual(got.get("old-beta"), "ok")
        self.assertEqual(got.get("new9"), "corrected")
        self.assertNotEqual(got.get("old-beta"), "corrected")

    def test_a_project_with_no_task_says_so(self):
        import tempfile
        empty = tempfile.mkdtemp(dir=self.home)
        with mock.patch.object(paths, "project_of", return_value="gamma"):
            code, out = self.mark_in(empty)
        self.assertEqual(self.marks(), [])
        self.assertIn("nothing to mark", out)

    def test_watch_g_marks_this_projects_task(self):
        from athos import watch
        cycle.run()
        tid, _res = ev.mark(watch.KEYS["g"], None, None, "beta")
        self.assertEqual(tid, "old-beta")
