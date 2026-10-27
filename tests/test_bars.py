from athos import eval as ev, paths, store, watch
from tests.helpers import TempHome


def task(tid, platform, project, chars, pieces=(), saved=(), result=None):
    ev.append({"type": "task_start", "task_id": tid, "platform": platform, "model": "m", "project": project,
               "at": "2026-10-27T10:00:00Z", **ev.request_fields("x" * chars)})
    ev.append({"type": "task_end", "task_id": tid, "pieces": list(pieces), "saved": list(saved),
               "duration_s": 30, "tokens": {"input": 100, "output": 0, "total": 100},
               "at": "2026-10-27T10:01:00Z"})
    if result:
        ev.append({"type": "mark", "task_id": tid, "result": result, "at": "2026-10-27T10:02:00Z"})


class BarsTest(TempHome):
    def setUp(self):
        super().setUp()
        self.piece = store.create("Release the greet package", "release greet", "Bump both places.")

    def test_nothing_until_a_task_here_used_or_saved_a_piece(self):
        task("t0", "claude-code", "greet", 10)
        self.assertIsNone(ev.bars("greet"))

    def test_one_row_per_agent_against_the_run_that_taught_the_piece(self):
        p = self.piece.id
        task("t1", "claude-code", "greet", 500, saved=[p])                     # the first run: the baseline
        task("t2", "claude-code", "greet", 100, pieces=[p], result="ok")
        task("t3", "claude-code", "greet", 150, pieces=[p], result="corrected")
        task("t4", "codex", "greet", 75, pieces=[p], result="ok")
        b = ev.bars("greet")
        self.assertEqual((b["piece"], b["baseline_request_chars"]), (p, 500))
        cc, cx = b["agents"]
        self.assertEqual((cc["label"], cc["uses"], cc["ok"], cc["evaluated"], cc["success_rate"]),
                         ("Claude Code", 2, 1, 2, 0.5))
        self.assertAlmostEqual(cc["prompt_saved"], 0.75)
        self.assertEqual(ev.bar_line(cc), ("█" * 10 + "░" * 10, "1/2 good · 75% shorter prompt"))
        self.assertEqual(ev.bar_line(cx)[1], "1/1 good · 85% shorter prompt")
        self.assertEqual([a["platform"] for a in b["agents"]], ["claude-code", "codex"])   # Muse only once used

    def test_only_this_projects_tasks_count(self):
        p = self.piece.id
        task("t1", "claude-code", "greet", 500, saved=[p])
        task("t2", "codex", "old-rehearsal", 75, pieces=[p], result="ok")
        self.assertEqual(ev.bars("greet")["agents"][1]["uses"], 0)

    def test_an_agent_that_has_not_used_it_shows_an_empty_bar(self):
        task("t1", "claude-code", "greet", 500, saved=[self.piece.id])
        cx = ev.bars("greet")["agents"][1]
        self.assertEqual(ev.bar_line(cx), ("░" * 20, "not used yet"))

    def test_the_panel_prints_the_same_bars(self):
        p = self.piece.id
        task("t1", "claude-code", "greet", 500, saved=[p])
        task("t2", "codex", "greet", 75, pieces=[p], result="ok")
        text = watch.frame("greet", color=False)
        self.assertIn("Release the greet package", text)
        self.assertIn("(first request 500 chars)", text)
        self.assertIn("Codex       " + "█" * 20 + "  1/1 good · 85% shorter prompt", text)
        self.assertIn("last task: Codex / m · ok", text)


class FormatTest(TempHome):
    def test_large_token_counts_read_in_millions(self):
        self.assertEqual((ev._k(950), ev._k(12400), ev._k(1133500)), ("950", "12.4k", "1.1M"))


class RequestTest(TempHome):
    def test_the_whole_request_length_is_kept_beside_its_first_characters(self):
        f = ev.request_fields("  " + "y" * 300 + " ")
        self.assertEqual((len(f["request"]), f["request_chars"]), (120, 300))
