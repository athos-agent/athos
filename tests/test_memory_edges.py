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
        segs = memory.manifest()["segments"]
        counted = [line for e in segs for n, line in enumerate(memory.read_segment(e).split(b"\n"))
                   if line.strip() and n not in set(e.get("repeats") or [])]
        self.assertEqual(len(counted) - len(set(counted)), twins)      # kept, but never counted twice
        self.assertEqual(sum(len(e.get("repeats") or []) for e in segs), 4)


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


class RepeatedLineTest(MemoryCase):
    def reimport(self):
        """Two archived lines written again into the live log, byte for byte: an older Athos importing the same
        turns again."""
        cycle.run()
        seg = memory.read_segment(memory.manifest()["segments"][0]).splitlines(keepends=True)
        twice = [line for line in seg if json.loads(line).get("task_id") == "old-beta"][:2]
        self.assertEqual(len(twice), 2)
        with open(paths.events_file(), "ab") as out:
            out.write(b"".join(twice))
        return twice

    def test_a_repeated_line_never_stops_the_archive(self):
        ends = count("task_end")
        self.reimport()
        outs = []
        for days in (45, 46, 47):                            # everything, the repeated lines too, is outside the window
            with later(days):
                outs.append(cycle.run(auto=True))
        self.assertFalse(any(o.get("stuck") or o["replay"].get("refused") for o in outs), outs)
        self.assertEqual(outs[0]["replay"].get("repeats_skipped"), 2)
        ev._EVENTS_CACHE.clear()
        replay = [e for e in ev.events() if e.get("type") == "memory_cycle" and e.get("phase") == "replay"]
        self.assertTrue(any(e.get("repeats_skipped") == 2 for e in replay))
        self.assertEqual(count("task_end"), ends)
        self.assertEqual(sum(1 for t in ev.tasks() if t["task_id"] == "old-beta"), 1)
        self.assertEqual(cycle.compare_rebuild()["ledger_equal"], True)

    def test_a_manifest_rebuilt_skips_the_same_lines(self):
        self.reimport()
        with later(45):
            cycle.run()
        uses = memory.view().record("report")
        whole = ev.record("report", ev.tasks())
        memory.manifest_file().unlink()
        cycle.recover()
        self.assertEqual(cycle.compare_rebuild()["ledger_equal"], True)
        cycle.rebuild()
        memory._VIEW.clear()
        ev._EVENTS_CACHE.clear()
        memory._ARCHIVE_CACHE.clear()
        self.assertEqual(memory.view().record("report"), uses)
        self.assertEqual(ev.record("report", ev.tasks()), whole)
        self.assertEqual(whole["uses"], 1)


class SweepTest(MemoryCase):
    def test_a_kill_between_the_sweeps_append_and_its_rename_then_one_more_line(self):
        old = open(paths.events_file(), "a")
        cycle.run()
        old.write(json.dumps({"type": "late_x", "at": stamp(0)}) + "\n")
        old.flush()
        size = paths.events_file().stat().st_size
        real = os.replace

        def die_after_the_append(src, dst):
            if ".trim-" in str(dst) and paths.events_file().stat().st_size > size:
                raise KeyboardInterrupt("killed between the append and the rename")
            return real(src, dst)
        with mock.patch.object(cycle.os, "replace", side_effect=die_after_the_append), \
                self.assertRaises(KeyboardInterrupt):
            cycle.sweep()
        self.assertEqual(count("late_x"), 1)
        self.assertEqual(cycle.due(), "sweep")
        old.write(json.dumps({"type": "late_y", "at": stamp(0)}) + "\n")
        old.flush()
        old.close()
        cycle.run()
        self.assertEqual((count("late_x"), count("late_y")), (1, 1))
        cycle.run()
        self.assertEqual((count("late_x"), count("late_y")), (1, 1))

    def test_a_kill_before_the_append_loses_nothing(self):
        old = open(paths.events_file(), "a")
        cycle.run()
        old.write(json.dumps({"type": "late_x", "at": stamp(0)}) + "\n")
        old.flush()
        old.close()
        real = os.replace
        calls = []

        def die_first(src, dst):
            if ".trim-" in str(dst) and not calls:
                calls.append(dst)
                raise KeyboardInterrupt("killed before the append")
            return real(src, dst)
        with mock.patch.object(cycle.os, "replace", side_effect=die_first), self.assertRaises(KeyboardInterrupt):
            cycle.sweep()
        cycle.run()
        self.assertEqual(count("late_x"), 1)

    def test_an_unfinished_line_carried_at_let_go_never_swallows_the_next_event(self):
        old = open(paths.events_file(), "a")
        cycle.run()
        old.write('{"type": "torn", "at": "')               # a writer killed in the middle of its line
        old.flush()
        old.close()
        with mock.patch.object(cycle, "SIDE_QUIET_S", -1):
            cycle.run()
        self.assertEqual(cycle.sidecars(), [])
        ev.append({"type": "next_one", "at": stamp(0)})
        self.assertEqual(count("next_one"), 1)
        torn = [line for line in paths.events_file().read_bytes().split(b"\n") if line.startswith(b'{"type": "torn"')]
        self.assertEqual(torn, [b'{"type": "torn", "at": "'])            # a line of its own, joined to nothing


class OlderAthosTest(MemoryCase):
    def test_tasks_an_older_athos_imports_again_are_counted_once_and_ask_for_a_cycle(self):
        cycle.run()
        hot = memory.view().sums()["projects"]["beta"]["tasks"]
        whole = sum(1 for t in ev.tasks() if t.get("project") == "beta")
        self.assertEqual(cycle.due(), "")
        seg = memory.read_segment(memory.manifest()["segments"][0]).splitlines(keepends=True)
        again = [line for line in seg if json.loads(line).get("task_id") == "old-beta"
                 and json.loads(line).get("type") in ("task_start", "task_end")]
        with open(paths.events_file(), "ab") as out:      # an older importer writes the archived turns again
            out.write(b"".join(again))
        memory._VIEW.clear()
        self.assertEqual(memory.view().sums()["projects"]["beta"]["tasks"], hot)
        self.assertEqual(cycle.due(), "late")
        cycle.run(auto=True)
        memory._VIEW.clear()
        self.assertEqual(memory.view().sums()["projects"]["beta"]["tasks"], hot)
        self.assertEqual(sum(1 for t in ev.tasks() if t.get("project") == "beta"), whole)
        self.assertEqual(cycle.due(), "")

    def test_the_audit_says_what_an_older_athos_costs_and_sees_its_imports(self):
        from athos import audit
        for cost in ("verifier", "grading", "import"):
            self.assertIn(cost, audit.OLDER_READS_WINDOW)
        cycle.run()
        seg = memory.read_segment(memory.manifest()["segments"][0]).splitlines(keepends=True)
        again = [line for line in seg if json.loads(line).get("task_id") == "old-beta"]
        with open(paths.events_file(), "ab") as out:
            out.write(b"".join(again))
        r = audit._version_mismatch(audit._Ctx("s", [], [], False), None)
        self.assertEqual(r["status"], "flagged")
        self.assertTrue(any("imported again" in f["what"] for f in r["found"]))


class ManifestTest(MemoryCase):
    def check(self, *more):
        import contextlib
        import io
        from athos import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["memory", "check", *more])
        return code, out.getvalue()

    def test_an_unreadable_manifest_is_reported_and_rebuilt_by_check(self):
        total = count("task_end")
        cycle.run()
        memory.manifest_file().write_text("{half a manif")
        self.assertEqual(cycle.due(), "resume")
        code, text = self.check()
        self.assertEqual(code, 1)
        self.assertIn("cannot be read", text)
        self.assertIn("rebuilt", text)
        self.assertEqual(len(memory.manifest()["segments"]), 1)
        self.assertEqual(count("task_end"), total)
        self.assertEqual(self.check()[0], 0)

    def test_an_empty_or_missing_manifest_is_never_read_as_no_archive(self):
        total = count("task_end")
        cycle.run()
        for broken in ("empty", "missing"):
            if broken == "empty":
                memory.manifest_file().write_text("")
            else:
                memory.manifest_file().unlink()
            self.assertTrue(memory.has_archive(), broken)
            self.assertEqual(cycle.due(), "resume", broken)
            code, text = self.check("--json")
            self.assertEqual(code, 1, broken)
            self.assertTrue(json.loads(text)["manifest_rebuilt"], broken)
            self.assertEqual(count("task_end"), total, broken)


class BoundaryLastTest(MemoryCase):
    def setUp(self):
        super().setUp()
        # In delta, an old task whose late mark keeps it at the boundary, and a newer task, archived whole.
        rows = task("d1", 50, project="delta", pieces=("keys",)) + task("d2", 40, project="delta", pieces=("ship",))
        log = paths.events_file()
        log.write_text("".join(json.dumps(r) + "\n" for r in rows) + log.read_text())
        write([{"type": "mark", "task_id": "d1", "result": "ok", "at": stamp(2)}])

    def test_the_bars_and_the_last_task_prefer_the_newer_archived_task(self):
        whole = ev._bars_from(ev.tasks(), "delta")["piece"]
        cycle.run()
        v = memory.view()
        self.assertIn("d1", v.rollups["boundary"])
        self.assertEqual(whole, "ship")
        self.assertEqual(v.bars("delta")["piece"], whole)
        self.assertEqual(v.last_task("delta")["task_id"], "d2")


NOFLOCK_LOCKER = r"""
import os, sys, time
sys.path.insert(0, sys.argv[1])
from athos.memory import cycle
cycle._flock = lambda: None                              # a filesystem without flock
if sys.argv[4] == "nolinks":
    real = os.link
    def no_link(*a, **k):
        raise OSError(45, "Operation not supported")
    os.link = no_link
marker = sys.argv[2]
bad = got = 0
until = time.time() + float(sys.argv[3])
while time.time() < until:
    if cycle.take_lock():
        got += 1
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            bad += 1
        else:
            time.sleep(0.002)
            os.close(fd)
            os.unlink(marker)
        cycle.release_lock()
    time.sleep(0.0005)
print(bad, got)
"""


class LockFallbackTest(MemoryCase):
    def race(self, mode):
        import subprocess
        import sys
        from pathlib import Path
        repo = str(Path(__file__).resolve().parents[1])
        marker = str(Path(self.home) / "holder")
        procs = [subprocess.Popen([sys.executable, "-c", NOFLOCK_LOCKER, repo, marker, "3", mode],
                                  stdout=subprocess.PIPE, text=True, env={**os.environ, "ATHOS_HOME": self.home})
                 for _ in range(4)]
        outs = [p.communicate(timeout=120)[0].split() for p in procs]
        return sum(int(o[0]) for o in outs), sum(int(o[1]) for o in outs)

    def test_without_flock_two_holders_never_overlap(self):
        bad, got = self.race("links")
        self.assertGreater(got, 50)
        self.assertEqual(bad, 0)

    def test_without_flock_nor_hard_links_a_cycle_still_runs_alone(self):
        bad, got = self.race("nolinks")
        self.assertGreater(got, 50)
        self.assertEqual(bad, 0)
        with mock.patch.object(cycle, "_flock", return_value=None), \
                mock.patch.object(cycle.os, "link", side_effect=OSError(45, "Operation not supported")):
            out = cycle.run()
        self.assertIn("replay", out)

    def test_looking_never_turns_a_starting_cycle_away(self):
        import fcntl
        real = fcntl.flock
        self.assertTrue(cycle.take_lock())
        calls = []
        with mock.patch.object(fcntl, "flock", side_effect=lambda *a: calls.append(a) or real(*a)):
            self.assertTrue(cycle.running())                 # read from the holder's pid, the lock untouched
        self.assertEqual(calls, [])
        cycle.release_lock()
        self.assertFalse(cycle.running())
        tries = []

        def busy_once(fd, op):
            tries.append(op)
            if len(tries) == 1:
                raise BlockingIOError("someone only looked")
            return real(fd, op)
        with mock.patch.object(fcntl, "flock", side_effect=busy_once):
            self.assertTrue(cycle.take_lock())
        cycle.release_lock()

    def test_a_lock_that_cannot_be_taken_by_nobody_backs_the_hooks_off(self):
        with mock.patch.object(cycle, "take_lock", return_value=False), \
                mock.patch.object(cycle, "running", return_value=False), later(45):
            self.assertEqual(cycle.run(auto=True), {"skipped": "another cycle is running"})
            why = cycle.due()
            self.assertTrue(why)
            self.assertTrue(cycle.backing_off(why))


class ClockAndQuietTest(MemoryCase):
    def test_a_back_off_recorded_while_the_clock_was_ahead_does_not_wedge(self):
        import time
        paths.write_atomic(cycle.state_file(), json.dumps({"at": time.time() + 400 * 86400, "reason": "age",
                                                            "outcome": "stuck", "streak": 3}))
        self.assertFalse(cycle.backing_off("age"))
        paths.write_atomic(cycle.state_file(), json.dumps({"at": time.time() - 60, "reason": "age",
                                                            "outcome": "stuck", "streak": 3}))
        self.assertTrue(cycle.backing_off("age"))

    def test_the_old_log_is_let_go_once_quiet_without_waiting_for_the_next_trim(self):
        import time
        cycle.run()
        sides = cycle.sidecars()
        self.assertTrue(sides)
        self.assertNotEqual(cycle.due(), "sweep")
        old = time.time() - cycle.SIDE_QUIET_S - 5
        for f in sides:
            os.utime(f, (old, old))
        with mock.patch.object(cycle, "_quiet", side_effect=lambda f, now=None: True):
            self.assertEqual(cycle.due(), "sweep")              # the next Stop asks for the cycle that lets it go
            cycle.run(auto=True)
        self.assertEqual(cycle.sidecars(), [])


class StreamTest(MemoryCase):
    def test_the_rollups_never_hold_every_live_event_at_once(self):
        cycle.run()
        before = memory.rollups_file().read_bytes()
        with mock.patch.object(memory, "decode", side_effect=AssertionError("the whole live log decoded at once")):
            cycle.write_rollups()
        self.assertEqual(cycle.compare_rebuild()["rollups_equal"], True)
        self.assertEqual(json.loads(memory.rollups_file().read_bytes())["boundary"], json.loads(before)["boundary"])
