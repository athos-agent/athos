"""The log's history is never lost or counted twice by the dream cycle, whoever else writes it: writers that do not
take the lock (an older Athos, another tool), a log put back from a backup or a sync tool, readers that run while a
cycle trims, a crash or a power cut at any step, two cycles started at once. All data here is synthetic."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest import mock

from athos import eval as ev, memory, paths
from athos.memory import cycle
from tests.test_memory_cycle import DAY, MemoryCase, stamp, task, write


def count(kind):
    return sum(1 for e in ev.events() if e.get("type") == kind)


class UnlockedWriterTest(MemoryCase):
    def test_a_line_written_into_the_old_file_after_the_trim_is_kept(self):
        # An older Athos opened the log to append before the trim and writes after it: into the file just replaced.
        old = open(paths.events_file(), "a")
        try:
            cycle.run()
            old.write(json.dumps({"type": "late_unlocked", "at": stamp(0)}) + "\n")
            old.flush()
        finally:
            old.close()
        cycle.run()                                        # the next cycle sweeps what reached the old file
        self.assertEqual(sum(1 for e in ev.live_events() if e.get("type") == "late_unlocked"), 1)
        self.assertEqual(count("late_unlocked"), 1)
        cycle.run()
        self.assertEqual(count("late_unlocked"), 1)        # once, not again at every cycle

    def test_a_crash_right_after_the_trim_loses_nothing(self):
        real = os.replace
        old = open(paths.events_file(), "a")

        def replace_then_die(src, dst):
            done = real(src, dst)
            if str(dst).endswith("events.jsonl"):
                old.write(json.dumps({"type": "late_unlocked", "at": stamp(0)}) + "\n")
                old.flush()
                raise OSError("killed right after the trim")
            return done
        try:
            with mock.patch.object(cycle.os, "replace", side_effect=replace_then_die), self.assertRaises(OSError):
                cycle.run()
        finally:
            old.close()
        cycle.run()
        self.assertEqual(count("late_unlocked"), 1)
        self.assertEqual(cycle.compare_rebuild()["ledger_equal"], True)


class RestoredLogTest(MemoryCase):
    def test_a_log_put_back_after_the_trim_is_not_archived_twice(self):
        before = self.snapshot()
        hot_before = self.hot()
        copy = paths.events_file().read_bytes()
        cycle.run()
        paths.events_file().write_bytes(copy)              # a backup restore, a sync tool, a second machine
        self.assertEqual(len(ev.events()), len(before["events"]))
        self.assertEqual(self.hot()["records"], hot_before["records"])
        cycle.run()
        shas = [s["sha256"] for s in memory.manifest()["segments"]]
        self.assertEqual(len(shas), len(set(shas)))
        self.assertEqual(self.snapshot()["records"], before["records"])
        self.assertEqual(self.hot()["records"], hot_before["records"])
        self.assertEqual(cycle.compare_rebuild(), {"ledger_equal": True, "rollups_equal": True,
                                                   "rollups_present": True})

    def test_a_log_from_before_two_cycles(self):
        before = self.snapshot()
        copy = paths.events_file().read_bytes()
        cycle.run()
        with mock.patch.object(cycle, "_now", return_value=ev.now() + 25 * DAY):
            cycle.run()
        self.assertEqual(len(memory.manifest()["segments"]), 2)
        paths.events_file().write_bytes(copy)
        self.assertEqual(self.snapshot()["records"], before["records"])
        with mock.patch.object(cycle, "_now", return_value=ev.now() + 25 * DAY):
            cycle.run()
        self.assertEqual(len(memory.manifest()["segments"]), 2)
        self.assertEqual(self.snapshot()["records"], before["records"])

    def test_archived_lines_put_back_out_of_place_are_never_archived_again(self):
        cycle.run()
        archived = memory.read_segment(memory.manifest()["segments"][0]).splitlines(keepends=True)
        live = paths.events_file().read_bytes()
        paths.events_file().write_bytes(b"".join(archived[5:9]) + live)     # a merge that kept some old lines
        segs = len(memory.manifest()["segments"])
        size = paths.events_file().stat().st_size
        events = len(memory.archived_events())
        with mock.patch.object(cycle, "_now", return_value=ev.now() + 25 * DAY):
            out = cycle.run()
        # Archived and trimmed, but the four repeated lines are never counted again (kept in the segment's bytes).
        self.assertNotIn("refused", out["replay"])
        self.assertEqual(out["replay"]["repeats_skipped"], 4)
        new = memory.manifest()["segments"][segs:]
        self.assertEqual(len(new), 1)
        self.assertEqual(len(memory.archived_events()) - events, new[0]["lines"] - 4)
        self.assertLess(paths.events_file().stat().st_size, size)

    def test_a_log_replaced_before_the_trim_is_left_alone_and_said(self):
        real = cycle.prune

        def replace_then_prune(entry, *a, **k):
            paths.events_file().write_text(json.dumps({"type": "someone_else", "at": stamp(0)}) + "\n")
            return real(entry, *a, **k)
        with mock.patch.object(cycle, "prune", side_effect=replace_then_prune):
            cycle.run()
        seg = memory.manifest()["segments"][0]
        self.assertEqual(seg["state"], "kept")              # not "pruned": nothing was trimmed
        self.assertEqual(cycle.due(), "")                   # and no cycle is asked for again and again
        replay = [e for e in ev.live_events() if e.get("type") == "memory_cycle" and e.get("phase") == "replay"][-1]
        self.assertIn("no longer starts", replay.get("refused") or "")
        self.assertEqual(count("someone_else"), 1)


class ConcurrentReaderTest(MemoryCase):
    def cut_and_trim(self):
        raw = memory.live_raw()
        entry = cycle.write_segment(raw[:cycle.cut(raw, ev.now() + self.ahead * DAY)])
        led = cycle.fold_segment(entry)
        cycle.write_rollups(led)
        cycle._set_state(entry["id"], "folded")
        cycle.prune(entry)

    def in_thread(self):
        t = threading.Thread(target=self.cut_and_trim)
        t.start()
        t.join(timeout=2)
        self.threads.append(t)

    def setUp(self):
        super().setUp()
        self.threads = []
        self.ahead = 0

    def tearDown(self):
        for t in self.threads:
            t.join(timeout=10)
        super().tearDown()

    def test_a_full_history_read_during_a_cycle_sees_every_event(self):
        cycle.run()                                       # an archive exists; the next cut is 25 days later
        self.ahead = 25
        total = len(ev.events())
        ev._EVENTS_CACHE.clear()
        real = memory.archived_events

        def archive_then_cycle(*a, **k):
            rows = real(*a, **k)
            self.in_thread()                              # the cycle archives and trims between two reads
            return rows
        with mock.patch.object(memory, "archived_events", side_effect=archive_then_cycle):
            got = ev.events()
        self.assertEqual(len(got), total)

    def test_the_hot_view_during_a_cycle_sees_every_task(self):
        records = self.hot()["records"]
        memory._VIEW.clear()
        real = memory.load_rollups

        def rollups_then_cycle(*a, **k):
            data = real(*a, **k)
            self.in_thread()
            return data
        with mock.patch.object(memory, "load_rollups", side_effect=rollups_then_cycle):
            v = memory.View()
        self.assertEqual({p: v.record(p) for p in records}, records)


class DurabilityTest(MemoryCase):
    def test_a_segment_left_as_a_temporary_file_is_kept(self):
        before = self.snapshot()
        real = os.replace

        def die_before_rename(src, dst):
            if str(dst).endswith(".jsonl.gz"):
                raise OSError("power cut")
            return real(src, dst)
        with mock.patch.object(cycle.os, "replace", side_effect=die_before_rename), self.assertRaises(OSError):
            cycle.run()
        tmp = [f for f in memory.archive_dir().iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(len(tmp), 1)
        raw = __import__("gzip").decompress(tmp[0].read_bytes())
        out = cycle.recover()
        self.assertEqual(out["promoted"], 1)
        segs = memory.manifest()["segments"]
        self.assertEqual(memory.read_segment(segs[0]), raw)  # promoted, never deleted
        cycle.run()
        self.assertEqual(self.snapshot()["records"], before["records"])

    def test_an_unreadable_manifest_is_rebuilt_from_the_segments(self):
        before = self.snapshot()
        cycle.run()
        memory.manifest_file().write_text("{half a manif")
        out = cycle.run()
        self.assertIn("replay", out)
        self.assertEqual(len(memory.manifest()["segments"]), 1)
        self.assertTrue(list((memory.archive_dir() / "damaged").glob("manifest*")))
        self.assertEqual(self.snapshot()["records"], before["records"])
        self.assertEqual(cycle.compare_rebuild()["ledger_equal"], True)

    def test_what_must_survive_a_power_cut_is_synced(self):
        synced = set()
        real = os.fsync

        def record(fd):
            synced.add(os.fstat(fd).st_ino)
            return real(fd)
        with mock.patch.object(os, "fsync", side_effect=record):
            cycle.run()
        seg = memory.segment_path(memory.manifest()["segments"][0])
        for f in (seg, memory.archive_dir(), memory.manifest_file(), memory.ledger_file(), memory.root()):
            self.assertIn(f.stat().st_ino, synced, f.name)

    def test_a_trim_left_half_done_is_cleaned(self):
        stray = paths.events_file().with_name(".events.jsonl.deadbeef.tmp")
        stray.write_text("half a copy\n")
        cycle.run()
        self.assertFalse(stray.exists())


LOCKER = r"""
import os, sys, time
sys.path.insert(0, sys.argv[1])
from athos.memory import cycle
marker = sys.argv[2]
bad = 0
for _ in range(int(sys.argv[3])):
    if cycle.take_lock():
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
print(bad)
"""


class CycleLockTest(MemoryCase):
    def test_racing_processes_never_hold_it_together(self):
        repo = str(Path(__file__).resolve().parents[1])
        marker = str(Path(self.home) / "holder")
        procs = [subprocess.Popen([sys.executable, "-c", LOCKER, repo, marker, "60"], stdout=subprocess.PIPE,
                                  text=True, env={**os.environ, "ATHOS_HOME": self.home}) for _ in range(4)]
        bad = sum(int(p.communicate(timeout=120)[0].strip() or 0) for p in procs)
        self.assertEqual(bad, 0)

    def test_a_live_holder_is_never_robbed(self):
        self.assertTrue(cycle.take_lock())
        cycle.lock_file().write_text("")                   # emptied, or old: the holder is alive, so it holds
        os.utime(cycle.lock_file(), (time.time() - 3600, time.time() - 3600))
        self.assertTrue(cycle.running())
        self.assertEqual(cycle.run(), {"skipped": "another cycle is running"})
        cycle.release_lock()
        self.assertFalse(cycle.running())


class StressTest(MemoryCase):
    """A short version of tests/memory_stress.py: real writers with and without the lock, cycles in a loop, one
    killed at random points. The long run's numbers are in the change that added it."""

    def test_locked_and_unlocked_writers_against_a_looping_cycle(self):
        from tests import memory_stress
        out = memory_stress.stress(4, locked=1, unlocked=2, kill_every=1.0, home=str(Path(self.home) / "stress"))
        self.assertGreater(out["written"], 100)
        self.assertGreater(out["cycles_done"], 2)
        self.assertEqual((out["missing"], out["duplicated"], out["unexpected"]), (0, 0, 0), out)
        self.assertEqual(out["archive_failures"], [])
        self.assertEqual(out["rebuild"], {"ledger_equal": True, "rollups_equal": True, "rollups_present": True})
        self.assertEqual(out["errors"], [])


class OlderVersionTest(MemoryCase):
    def test_an_older_athos_writing_after_the_archive_is_reported_with_what_it_costs(self):
        from athos import audit
        cycle.run()
        self.assertTrue(memory.manifest().get("oldest_reader"))
        evs = [{"type": "route", "session_id": "s", "task_id": "t1", "project": "alpha", "at": stamp(0),
                "v": "0.1.109"}]
        r = audit._version_mismatch(audit._Ctx("s", evs, [], False), None)
        self.assertEqual(r["status"], "flagged")
        self.assertIn("live window", r["found"][0]["risk"])
        r = audit._version_mismatch(audit._Ctx("s", evs, [], False), {"agents": {"claude-code": "0.1.109"}})
        self.assertTrue(any("live window" in f["risk"] for f in r["found"]))
        same = [{**evs[0], "v": memory.OLDEST_READER}]
        self.assertEqual(audit._version_mismatch(audit._Ctx("s", same, [], False), None)["status"], "clean")
        # A main-line Athos from before both lines met (0.1.172 never read the archive) is flagged, even against a
        # manifest written by the memory line's 0.1.166.
        old_main = [{**evs[0], "v": "0.1.172"}]
        memory.write_json(memory.manifest_file(), {**memory.manifest(), "oldest_reader": "0.1.166"})
        r = audit._version_mismatch(audit._Ctx("s", old_main, [], False), None)
        self.assertEqual(r["status"], "flagged")
