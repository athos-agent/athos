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
