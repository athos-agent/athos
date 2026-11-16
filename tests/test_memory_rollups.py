"""The rollups the hooks read: equal to the whole history's numbers across the cut (a task that straddles it, a late
line about a task nobody started), bounded by the window and the number of pieces and projects, never by the length
of history, and free of request words. All data here is synthetic."""

import json
from unittest import mock

from athos import eval as ev, memory, paths, tiers
from athos.memory import cycle
from tests.test_audit import HookCase, piece
from tests.test_memory_cycle import MemoryCase, stamp, task


def reset(rows):
    rows = sorted(rows, key=lambda r: r["at"])
    paths.events_file().parent.mkdir(parents=True, exist_ok=True)
    paths.events_file().write_text("".join(json.dumps(r) + "\n" for r in rows))


def end(tid, days, pieces=(), saved=()):
    return {"type": "task_end", "task_id": tid, "session_id": "s-alpha", "at": stamp(days), "duration_s": 3.0,
            "tokens": None, "model": "claude-opus-5-5", "pieces": list(pieces), "saved": list(saved)}


class BoundaryBarsTest(HookCase):
    def bars_agree(self):
        full = ev._bars_from(ev.tasks(), "alpha")
        self.assertEqual(memory.view().bars("alpha"), full)
        return full

    def test_the_task_that_taught_a_piece_straddles_the_cut(self):
        piece("fresh", "Fresh way", "a fresh way", ["alpha"])
        rows = task("teach", 32, end=False)                       # begun before the cut, ends in the live log
        rows += [end("teach", 5, saved=("fresh",))]
        rows += task("use1", 31.5, pieces=("fresh",), result="ok") + task("use2", 31, pieces=("fresh",), result="ok")
        for i, d in enumerate((3, 2, 1)):
            rows += task(f"live{i}", d, pieces=("fresh",), result="ok")
        reset(rows)
        before = self.bars_agree()
        self.assertEqual(sum(r["uses"] for r in before["agents"]), 5)
        cycle.run()
        self.assertIn("teach", memory.load_rollups()["boundary"])
        self.assertEqual(self.bars_agree(), before)

    def test_a_use_that_straddles_the_cut_began_before_the_teaching_run(self):
        piece("fresh", "Fresh way", "a fresh way", ["alpha"])
        rows = task("early", 33, end=False) + [end("early", 4, pieces=("fresh",))]
        rows += task("teach", 31, saved=("fresh",), result="ok")
        rows += task("use1", 30.5, pieces=("fresh",), result="ok")
        rows += task("live0", 2, pieces=("fresh",), result="ok")
        reset(rows)
        before = self.bars_agree()
        cycle.run()
        self.assertEqual(self.bars_agree(), before)


class LateUnknownTaskTest(MemoryCase):
    def test_a_late_line_about_a_task_nobody_started_counts_at_once(self):
        (paths.home() / "config.json").write_text(json.dumps({"memory": {"auto": False}}))
        cycle.run()
        ev.append(end("ghost", 0, pieces=("ship",)))              # no task_start anywhere
        self.assertEqual(memory.view().record("ship"), ev.record("ship", ev.tasks()))
        self.assertNotEqual(cycle.due(), "late")


class BoundedRollupsTest(HookCase):
    def history(self, n):
        piece("ship", "Ship a release", "shipping a release", ["alpha"])
        piece("keys", "Rotate the keys", "rotating the keys", ["alpha"], )
        rows = []
        for i in range(n):
            d = 300 - 260 * i / n                                 # all archived: 300 to 40 days ago
            rows += task(f"t{i}", d, pieces=("ship", "keys") if i % 2 else ("ship",), result="ok")
            rows += [{"type": "reuse", "piece": "ship", "version": 1, "outcome": "clean", "tier": "frontier",
                      "basis": [], "task_id": f"t{i}", "at": stamp(d, 2)},
                     {"type": "route", "request_kind": "person", "project": "alpha", "chosen": [], "delivery": None,
                      "request_sha": f"{i:012x}", "at": stamp(d, 1)},
                     {"type": "learned_from_edit", "task_id": f"t{i}", "piece": "keys", "statement": "one",
                      "basis": "changed_between_tool_calls", "at": stamp(d, 2)},
                     {"type": "shadow", "piece": "ship", "model": "small", "equivalent": True, "case": f"c{i % 10}",
                      "version": 1, "at": stamp(d, 3)}]
        rows += task("now", 1, pieces=("ship",), result="ok")
        reset(rows)
        cycle.run()
        return memory.rollups_file().stat().st_size

    def test_the_rollups_do_not_grow_with_history(self):
        small = self.history(200)
        large = self.history(2000)
        roll = memory.load_rollups()
        # The archived task ids are a filter of a fixed size at most (it compresses less as it fills).
        self.assertLess(large - len(roll["ids"]), small * 1.2, (small, large))
        self.assertLess(len(roll["ids"]), memory.BLOOM_BITS // 8 * 4 // 3 + 100)
        for key in ("route", "step_edits", "misfires"):           # read by the cycle only: kept in the ledger
            self.assertNotIn(key, roll)
        self.assertLessEqual(len(roll["grade"]["ship"]), 20)
        # And what the grading rules see is the same as from the whole history.
        from athos import grade, store
        full = [e for e in ev.events() if e.get("piece") == "ship" and e.get("type") in memory.GRADE_TYPES]
        def decides(st):                     # what the rules compare: counts against thresholds of 1 to 3
            cap = memory.GRADE_PER_CLASS
            return (st["verifier"], st["checks"], st["risk"], min(st["frontier_clean"], cap),
                    min(st["apply_pass"], cap), min(st["apply_clean"], cap), st["outcomes"][-grade.RETIRE_WINDOW:],
                    min(st["strong_negatives"], cap))
        with mock.patch.object(grade, "_events", return_value=full):
            whole = grade.standing(store.get("ship"))
        self.assertEqual(decides(grade.standing(store.get("ship"))), decides(whole))
        self.assertGreater(whole["frontier_clean"], memory.GRADE_PER_CLASS)


class FreeTextTest(MemoryCase):
    def test_free_text_in_the_derived_files_holds_no_request_words(self):
        paths.events_file().write_text("".join(json.dumps(r) + "\n" for r in [
            {"type": "rating", "id": "r2", "stars": 2, "piece": "ship", "step": "one", "version": 1, "task_id": "old04",
             "request": "migrate the purple elephant database", "label": "Ship it",
             "did": "ran migrate the purple elephant database step", "at": stamp(41)},
            {"type": "learn", "piece": "keys", "decision": "saved", "task_id": "old05",
             "reason": "the person asked to migrate the purple elephant database", "at": stamp(41)}])
            + paths.events_file().read_text())
        cycle.run()
        for f in (memory.ledger_file(), memory.rollups_file()):
            self.assertNotIn("purple elephant", f.read_text())


class TierLookupTest(MemoryCase):
    def test_the_tier_is_looked_up_once_per_model(self):
        calls = []
        real = tiers.tier_of
        with mock.patch.object(tiers, "tier_of", side_effect=lambda m: calls.append(m) or real(m)):
            memory.sums(ev.tasks())
        self.assertLessEqual(len(calls), len({t.get("model") for t in ev.tasks()}))
