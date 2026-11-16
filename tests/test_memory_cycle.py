"""Long-term memory and the dream cycle: the live log keeps a recent window, older events are archived compressed and
folded into rollups the hooks read, nothing is lost, every derived file equals its rebuild, a crash at any step is
resumed, and the hot paths never read the archive. All data here is synthetic."""

import contextlib
import datetime as dt
import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

from athos import cli, consolidate, eval as ev, journal, memory, paths, store
from athos.memory import cycle
from tests.test_audit import HookCase, piece

DAY = dt.timedelta(days=1)


def stamp(days_ago: float, minute: int = 0) -> str:
    t = ev.now() - days_ago * DAY + dt.timedelta(minutes=minute)
    return t.isoformat(timespec="milliseconds")


def task(tid, days_ago, project="alpha", pieces=(), saved=(), result=None, platform="claude-code",
         model="claude-opus-5-5", request="please do the thing", opened=(), end=True):
    rows = [{"type": "task_start", "task_id": tid, "session_id": "s-" + project, "platform": platform,
             "model": model, "project": project, "at": stamp(days_ago), "request": request,
             "request_chars": len(request)}]
    rows += [{"type": "piece_opened", "task_id": tid, "piece": p, "at": stamp(days_ago, 1)} for p in opened]
    rows += [{"type": "trail", "kind": "step", "task_id": tid, "piece": p, "step": "one", "at": stamp(days_ago, 1)}
             for p in pieces]
    if end:
        rows.append({"type": "task_end", "task_id": tid, "session_id": "s-" + project, "at": stamp(days_ago, 2),
                     "duration_s": 30.0, "tokens": {"total": 1000}, "model": model, "pieces": list(pieces),
                     "saved": list(saved)})
    if result:
        rows.append({"type": "mark", "task_id": tid, "result": result, "at": stamp(days_ago, 3)})
    return rows


def write(rows):
    target = paths.events_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")


class MemoryCase(HookCase):
    def setUp(self):
        super().setUp()
        piece("ship", "Ship a release", "shipping a release", ["alpha"])
        piece("keys", "Rotate the keys", "rotating the keys", ["alpha"])
        piece("report", "Write the report", "writing the weekly report", ["beta"])
        rows = []
        for i in range(30):                                   # 30 old tasks, 60 to 31 days ago
            d = 60 - i
            rows += task(f"old{i:02d}", d, pieces=("ship", "keys") if i % 3 == 0 else ("ship",),
                         saved=("keys",) if i == 1 else (), result="ok" if i % 2 else "corrected",
                         opened=("keys",) if i % 3 == 0 else ())
        rows += task("old-beta", 45, project="beta", pieces=("report",), result="ok", platform="codex")
        rows += [{"type": "route", "request_kind": "person", "project": "alpha", "chosen": [], "delivery": None,
                  "request_sha": "aaaaaaaaaaaa", "at": stamp(50)}] * 3
        rows += [{"type": "reuse", "piece": "ship", "version": 1, "outcome": "corrected", "tier": "frontier",
                  "basis": ["check_failed"], "at": stamp(40 - k)} for k in range(2)]
        rows += [{"type": "verify", "piece": "keys", "version": 1, "outcome": "pass", "at": stamp(41)}]
        rows += [{"type": "shadow", "piece": "ship", "model": "m", "equivalent": True, "at": stamp(42)}]
        rows += [{"type": "rating", "id": "r1", "stars": 1, "piece": "ship", "step": "one", "version": 1,
                  "task_id": "old03", "request": "secret words", "did": "did it", "at": stamp(43)}]
        # A task begun in the archived window that ends in the live one, and recent tasks.
        rows += task("edge", 31, pieces=("ship",), end=False)
        for i in range(10):
            rows += task(f"new{i}", 10 - i, pieces=("ship",) if i % 2 else (), result="ok")
        rows += [{"type": "task_end", "task_id": "edge", "session_id": "s-alpha", "at": stamp(5),
                  "duration_s": 3.0, "tokens": None, "model": "claude-opus-5-5", "pieces": ["ship"], "saved": []}]
        write(rows)

    def snapshot(self):
        tasks = ev.tasks()
        return {"events": ev.events(), "tasks": tasks, "records": {p: ev.record(p, tasks) for p in
                                                                     ("ship", "keys", "report", "gone")},
                "report": {k: v for k, v in ev.report().items() if k != "generated"},
                "bars": {p: ev._bars_from(tasks, p) for p in ("alpha", "beta", None)}}

    def hot(self):
        v = memory.view()
        return {"records": {p: v.record(p) for p in ("ship", "keys", "report", "gone")},
                "bars": {p: v.bars(p) for p in ("alpha", "beta", None)}}


class WindowTest(MemoryCase):
    def test_the_cut_is_a_prefix_of_old_whole_lines(self):
        raw = memory.live_raw()
        n = cycle.cut(raw, ev.now())
        self.assertTrue(raw[:n].endswith(b"\n"))
        archived, kept = memory.decode(raw[:n]), memory.decode(raw[n:])
        self.assertTrue(all(cycle._days(ev.now(), e["at"]) > 30 for e in archived))
        self.assertTrue(cycle._days(ev.now(), kept[0]["at"]) <= 30)
        # By size: older lines leave while the log is over keep_bytes, never one of the last min_keep_days.
        s = {**memory.settings(), "keep_bytes": 100}
        n2 = cycle.cut(raw, ev.now(), s)
        self.assertTrue(all(cycle._days(ev.now(), e["at"]) > 8 for e in memory.decode(raw[:n2])))
        self.assertGreater(n2, n)

    def test_a_cycle_archives_and_every_statistic_stays_the_same(self):
        before = self.snapshot()
        hot_before = self.hot()
        live_before = paths.events_file().stat().st_size
        out = cycle.run()
        self.assertGreater(out["replay"]["archived_lines"], 50)
        self.assertLess(paths.events_file().stat().st_size, live_before)
        seg = memory.manifest()["segments"][0]
        self.assertEqual(seg["state"], "pruned")
        self.assertTrue(memory.segment_path(seg).name.endswith(".jsonl.gz"))
        after = self.snapshot()
        before_events = [e for e in before["events"]]
        self.assertEqual(after["events"][:len(before_events)], before_events)   # nothing lost, nothing doubled
        self.assertEqual(after["tasks"], before["tasks"])
        self.assertEqual(after["records"], before["records"])
        self.assertEqual(after["report"], before["report"])
        self.assertEqual(self.hot(), hot_before)
        self.assertEqual(self.hot()["records"], before["records"])
        self.assertEqual(self.hot()["bars"], before["bars"])
        # The task begun in the archive and ended in the live log is one task, folded across the boundary.
        self.assertIn("edge", (memory.load_rollups() or {})["boundary"])
        self.assertEqual(sum(1 for t in memory.view().tasks() if t["task_id"] == "edge"), 1)

    def test_the_rollups_and_the_ledger_equal_a_rebuild(self):
        cycle.run()
        write(task("later", 0.5, pieces=("keys",), result="ok"))
        with mock.patch.object(cycle, "_now", return_value=ev.now() + 25 * DAY):
            cycle.run()                                       # a second segment
        self.assertEqual(len(memory.manifest()["segments"]), 2)
        self.assertEqual(cycle.compare_rebuild(), {"ledger_equal": True, "rollups_equal": True,
                                                   "rollups_present": True})
        led, roll = memory.ledger_file().read_bytes(), memory.rollups_file().read_text()
        memory.ledger_file().unlink()
        memory.rollups_file().unlink()
        cycle.rebuild()
        self.assertEqual(memory.ledger_file().read_bytes(), led)
        drop = lambda t: {k: v for k, v in json.loads(t).items() if k != "live_mark"}   # noqa: E731
        self.assertEqual(drop(memory.rollups_file().read_text()), drop(roll))

    def test_no_request_words_in_the_derived_files(self):
        cycle.run()
        for f in (memory.ledger_file(), memory.rollups_file()):
            text = f.read_text()
            self.assertNotIn("please do the thing", text)
            self.assertNotIn("secret words", text)


class CrashTest(MemoryCase):
    """A cycle stopped at any step is finished by the next one, and the readers never count a line twice meanwhile."""

    def check_whole(self, before):
        self.assertEqual(self.snapshot()["tasks"], before["tasks"])
        self.assertEqual(self.snapshot()["records"], before["records"])
        self.assertEqual(self.hot()["records"], before["records"])

    def resume_and_check(self, before):
        cycle.run()
        self.assertTrue(all(s["state"] == "pruned" for s in memory.manifest()["segments"]))
        self.assertEqual(len(memory.manifest()["segments"]), 1)
        self.assertFalse([f for f in memory.archive_dir().iterdir() if f.name.endswith(".tmp")])
        self.check_whole(before)
        self.assertEqual(cycle.compare_rebuild()["ledger_equal"], True)
        self.assertFalse(cycle.running())

    def test_a_crash_while_the_segment_is_written(self):
        before = self.snapshot()
        real = os.replace

        def boom(src, dst):
            if str(dst).endswith(".jsonl.gz"):
                raise OSError("disk gone")
            return real(src, dst)
        with mock.patch.object(cycle.os, "replace", side_effect=boom), self.assertRaises(OSError):
            cycle.run()
        self.check_whole(before)
        self.resume_and_check(before)

    def test_a_crash_after_the_segment_before_it_is_folded(self):
        before = self.snapshot()
        with mock.patch.object(cycle, "fold_segment", side_effect=RuntimeError("killed")), \
                self.assertRaises(RuntimeError):
            cycle.run()
        self.assertEqual(memory.manifest()["segments"][0]["state"], "written")
        self.check_whole(before)                       # the full history reads the segment once; the hot view the log
        self.resume_and_check(before)

    def test_a_crash_after_folding_before_the_live_log_is_trimmed(self):
        before = self.snapshot()
        with mock.patch.object(cycle, "prune", side_effect=RuntimeError("killed")), self.assertRaises(RuntimeError):
            cycle.run()
        self.assertEqual(memory.manifest()["segments"][0]["state"], "folded")
        self.check_whole(before)                       # folded and still in the live log: counted once
        self.resume_and_check(before)

    def test_a_crash_after_trimming_before_the_manifest_says_so(self):
        before = self.snapshot()
        real = cycle._set_state

        def stop(seg_id, state):
            if state == "pruned":
                raise RuntimeError("killed")
            return real(seg_id, state)
        with mock.patch.object(cycle, "_set_state", side_effect=stop), self.assertRaises(RuntimeError):
            cycle.run()
        self.check_whole(before)
        live = paths.events_file().stat().st_size
        self.resume_and_check(before)
        self.assertEqual(paths.events_file().stat().st_size >= live, True)   # trimmed once, not twice

    def test_a_line_an_older_athos_appends_without_the_lock_while_trimming_is_kept(self):
        real = os.replace

        def old_writer_then_replace(src, dst):
            if str(dst).endswith("events.jsonl"):
                with open(dst, "a") as out:               # an older Athos: no lock, the old file, mid-trim
                    out.write(json.dumps({"type": "from_old_version", "at": stamp(0)}) + "\n")
            return real(src, dst)
        with mock.patch.object(cycle.os, "replace", side_effect=old_writer_then_replace):
            cycle.run()
        self.assertEqual(sum(1 for e in ev.live_events() if e.get("type") == "from_old_version"), 1)
        self.assertEqual(sum(1 for e in ev.events() if e.get("type") == "from_old_version"), 1)


class HotPathTest(MemoryCase):
    """The hooks and `athos status` read the rollups and the live log, never the archive."""

    def test_no_hook_reads_the_whole_history(self):
        cycle.run()
        reads = []

        def forbidden(*_a, **_k):
            reads.append(1)
            raise AssertionError("the hot path read the whole history")
        ev.append({"type": "mark", "task_id": "new3", "result": "ok", "at": stamp(0)})
        base = {"session_id": "hot1", "cwd": str(self.alpha)}
        with mock.patch.object(memory, "archived_events", forbidden), \
                mock.patch.object(memory, "read_segment", forbidden), \
                mock.patch.object(ev, "events", forbidden), mock.patch.object(ev, "tasks", forbidden):
            self.hook("session-start", {**base, "model": "claude-opus-5-5"})
            for prompt in ("please ship a release", "perfect, thanks. rotate the keys"):
                self.hook("prompt", {**base, "prompt": prompt})
                self.hook("tool-start", {**base, "tool_name": "Bash", "tool_input": {"command": "pytest"}})
                self.hook("tool", {**base, "tool_name": "Bash", "tool_input": {"command": "athos show ship"}})
                self.hook("stop", base)
            with contextlib.chdir(self.alpha):
                cli.status()
            journal.text("alpha")
            consolidate.run()
        self.assertEqual(reads, [])
        self.assertFalse([e for e in ev.events() if e.get("type") == "hook_error"])

    def test_the_journal_counts_archived_tasks(self):
        before = journal.text("alpha")
        cycle.run()
        after = journal.text("alpha")
        self.assertEqual(after, before)        # six recent tasks live: the archived ones were only counted anyway


class LateLinesTest(MemoryCase):
    def test_a_correction_after_archiving_takes_effect(self):
        cycle.run()
        uses = memory.view().record("ship")["uses"]
        ev.append({"type": "correction", "task_id": "old05", "target": "task_pieces", "piece": "ship",
                   "original_at": None, "reason": "another_project", "at": stamp(0)})
        self.assertTrue(memory.view().stale)               # named an archived task the rollups have not folded
        self.assertEqual(cycle.due(), "late")
        cli._absorb_late()                                 # what `athos repair --apply` does right after
        self.assertFalse(memory.view().stale)
        full = ev.record("ship", ev.tasks())
        self.assertEqual(full["uses"], uses - 1)
        self.assertEqual(memory.view().record("ship"), full)
        # And once that correction is itself archived, it still holds.
        with mock.patch.object(cycle, "_now", return_value=ev.now() + 40 * DAY):
            cycle.run()
        self.assertEqual(memory.view().record("ship"), ev.record("ship", ev.tasks()))
        self.assertEqual(memory.view().record("ship")["uses"], uses - 1)

    def test_a_late_mark_of_an_archived_task(self):
        cycle.run()
        ev.append({"type": "mark", "task_id": "old02", "result": "failed", "at": stamp(0)})
        cli._absorb_late()
        self.assertEqual(memory.view().record("ship"), ev.record("ship", ev.tasks()))


class RulesTest(MemoryCase):
    def test_the_cycle_never_writes_a_piece_file(self):
        files = {f: f.read_bytes() for f in paths.know_how().glob("*.md")}
        stamps = {f: f.stat().st_mtime_ns for f in files}
        cycle.run()
        self.assertEqual({f: f.read_bytes() for f in files}, files)
        self.assertEqual({f: f.stat().st_mtime_ns for f in files}, stamps)
        self.assertFalse((paths.know_how() / ".history").exists())

    def test_project_pages_name_only_what_may_be_named_there(self):
        piece("secretive", "Private thing", "the private thing", ["beta"])
        write(task("mix", 2, project="alpha", pieces=("report",), result="ok"))     # another project's piece here
        cycle.run()
        page = (memory.projects_dir() / "alpha.md").read_text()
        self.assertIn("`ship`", page)
        self.assertNotIn("report", page.replace("1 use(s) of pieces of other projects", ""))
        self.assertIn("1 use(s) of pieces of other projects", page)
        self.assertNotIn("please do the thing", page)
        # A public project's page: only what may load there.
        write([{"type": "route", "request_kind": "person", "project": "beta", "public": True, "chosen": [],
                "delivery": None, "at": stamp(0)}])
        control_profile = Path(self.home) / "profile.json"
        control_profile.write_text(json.dumps({"pieces": ["ship"]}))
        write(task("pub", 1, project="beta", pieces=("ship", "report"), result="ok"))
        cycle.run()
        beta = (memory.projects_dir() / "beta.md").read_text()
        self.assertIn("`report`", beta)
        self.assertNotIn("`ship`", beta)                  # a profile piece not allowed in public: counted only

    def test_a_project_page_of_the_persons_is_never_touched(self):
        memory.projects_dir().mkdir(parents=True, exist_ok=True)
        own = memory.projects_dir() / "alpha.md"
        own.write_text("# alpha\nMy own words about this project.\n")
        cycle.run()
        self.assertEqual(own.read_text(), "# alpha\nMy own words about this project.\n")
        self.assertTrue((memory.projects_dir() / "beta.md").exists())

    def test_an_earlier_page_athos_wrote_is_kept(self):
        cycle.run()
        write(task("more", 1, pieces=("keys",), result="ok"))
        write(task("more2", 1, pieces=("keys",), result="ok"))
        cycle.run()
        self.assertTrue(list((memory.projects_dir() / ".history").glob("alpha.v1.md")))

    def test_in_a_public_repository_another_projects_page_is_refused(self):
        cycle.run()
        (self.alpha / paths.MARKER).write_text('name = "alpha"\npublic = true\n')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.chdir(self.alpha), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["memory", "project", "beta"]), 1)
            self.assertEqual(cli.main(["memory", "project"]), 0)
        self.assertNotIn("beta", out.getvalue())
        self.assertIn("# Working in alpha", out.getvalue())

    def test_one_cycle_at_a_time(self):
        self.assertTrue(cycle.take_lock())
        self.assertEqual(cycle.run(), {"skipped": "another cycle is running"})
        cycle.release_lock()
        cycle.lock_file().write_text(json.dumps({"pid": 999999, "at": 0}))      # a cycle that died
        self.assertIn("replay", cycle.run())

    def test_the_hooks_start_it_detached_only_when_due(self):
        calls = []
        popen = lambda argv, **kw: calls.append(argv)          # noqa: E731
        self.assertTrue(cycle.maybe_spawn(Path("/x/athos"), popen))     # its oldest event is 60 days old
        self.assertEqual(calls[-1][-3:], ["memory", "cycle", "--quiet"])
        cycle.run()
        self.assertFalse(cycle.maybe_spawn(Path("/x/athos"), popen))
        self.assertEqual(len(calls), 1)
        with mock.patch.object(cycle, "due", return_value="size"):
            (Path(self.home) / "config.json").write_text(json.dumps({"memory": {"auto": False}}))
            self.assertFalse(cycle.maybe_spawn(Path("/x/athos"), popen))

    def test_every_phase_is_an_event(self):
        cycle.run()
        phases = [e["phase"] for e in ev.live_events() if e.get("type") == "memory_cycle"]
        self.assertEqual(phases, ["replay", "abstraction", "consolidation", "done"])
        replay = next(e for e in ev.live_events() if e.get("type") == "memory_cycle")
        self.assertGreater(replay["archived_bytes"], 0)
        self.assertIn("duration_ms", replay)


class FindingsTest(MemoryCase):
    def test_what_counting_finds(self):
        piece("ship-again", "Ship a release", "shipping a release of the app", ["alpha"])
        write([{"type": "learned_from_edit", "task_id": f"new{k}", "piece": "keys", "statement": "one",
                "basis": "changed_between_tool_calls", "at": stamp(1)} for k in range(2)])
        write([{"type": "learned_from_edit", "task_id": "new5", "piece": "keys", "statement": "one", "at": stamp(1)}])
        cycle.run()
        found = json.loads(memory.findings_file().read_text())
        self.assertIn({"pieces": ["keys", "ship"], "tasks": 10}, found["together"])
        self.assertEqual(found["no_piece"], [{"project": "alpha", "requests": 3, "nothing": 3, "repeated": 1}])
        self.assertIn({"pieces": ["ship", "ship-again"]}, found["overlaps"])
        self.assertEqual(found["corrected_steps"], [{"piece": "keys", "step": "one", "edits": 2}])
        self.assertEqual(found["checks_failing"], [{"piece": "ship", "check_failed": 2}])


class AssociationTest(MemoryCase):
    """The "often used with" index line: off by default (it did not help on one person's tasks), from the rollups and
    the live log when turned on."""

    def test_partner_and_the_line(self):
        from athos import load
        cycle.run()
        self.assertEqual(memory.partner("ship", {"keys", "ship"}, set()), ("keys", 10))
        self.assertIsNone(memory.partner("ship", {"keys", "ship"}, {"keys"}))
        ship, keys = store.get("ship"), store.get("keys")
        self.assertIsNone(load._often_with([ship], {"ship": ship, "keys": keys}, ["ship"]))       # off
        (Path(self.home) / "config.json").write_text(json.dumps({"memory": {"associations_line": True}}))
        pid, line = load._often_with([ship], {"ship": ship, "keys": keys}, ["ship"])
        self.assertEqual(pid, "keys")
        self.assertIn("often used with `ship` (10 tasks): `keys`", line)


class RecoverTest(MemoryCase):
    """Nothing the cycle keeps is ever deleted to tidy up, and derived files that are lost are made again."""

    def test_a_lost_manifest_never_costs_a_segment(self):
        before = self.snapshot()
        cycle.run()
        seg = memory.segment_path(memory.manifest()["segments"][0])
        memory.manifest_file().unlink()
        cycle.run()
        self.assertTrue(seg.exists())
        self.assertEqual(memory.manifest()["segments"][0]["state"], "pruned")
        self.assertEqual(self.snapshot()["tasks"], before["tasks"])
        self.assertEqual(self.hot()["records"], before["records"])

    def test_lost_rollups_and_ledger_are_made_again_and_the_hooks_ask_for_it(self):
        before = self.snapshot()
        cycle.run()
        memory.rollups_file().unlink()
        memory.ledger_file().write_text("{not json")
        self.assertEqual(cycle.due(), "rollups")
        cycle.run()
        self.assertEqual(self.hot()["records"], before["records"])
        self.assertEqual(cycle.compare_rebuild()["ledger_equal"], True)

    def test_an_unreadable_segment_is_set_aside_not_deleted(self):
        cycle.run()
        bad = memory.archive_dir() / "events-00009.jsonl.gz"
        bad.write_bytes(b"not gzip")
        cycle.run()
        self.assertTrue((memory.archive_dir() / "damaged" / "events-00009.jsonl.gz").exists())
