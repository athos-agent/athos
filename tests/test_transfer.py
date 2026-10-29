import json
import subprocess
import sys
import tempfile
from pathlib import Path

from athos import bench
from athos.bench import transfer
from tests.helpers import TempHome

KEYS = ["table_columns", "governing_law_row", "push_first_line"]
SOURCES = {"table_columns": "checklist", "governing_law_row": "taught", "push_first_line": "taught"}


def row(agent, arm, applied, teach="contract-transfer-1"):
    items = {k: k in applied for k in KEYS}
    return {"case": "contract-transfer", "agent": agent, "arm": arm, "teach": teach, "model": "m",
            "items": items, "sources": SOURCES, "verdict": "g" if all(items.values()) else "f",
            "duration_s": 10.0, "tokens": {"input": 100, "output": 10}, "cost_usd": 0.01}


class TransferReport(TempHome):
    def test_completeness_and_taught_rules_per_agent_and_arm(self):
        rows = [row("muse", "A", ["table_columns"]), row("muse", "A", []),
                row("muse", "B", KEYS), row("muse", "B", ["table_columns", "push_first_line"]),
                row("claude", "B", KEYS)]
        rep = transfer.report("contract-transfer", rows=rows)
        by = {(x["agent"], x["arm"]): x for x in rep["lines"]}
        self.assertEqual(by[("muse", "A")]["completeness"], round((1 / 3 + 0) / 2, 3))
        self.assertEqual(by[("muse", "A")]["taught_applied"], 0)
        self.assertEqual(by[("muse", "B")]["taught_applied"], 0.75)
        self.assertEqual(by[("muse", "B")]["all_points"], 1)
        self.assertEqual([x["agent"] for x in rep["lines"]], ["claude", "muse", "muse"])   # bench's agent order
        text = transfer.render(rep)
        self.assertIn("| Muse Code | m | B: .athos/ folder only | 2 | 83% | 75% | 1/2 |", text)
        self.assertIn("governing_law_row", text)

    def test_only_the_latest_teaching_unless_one_is_named(self):
        rows = [row("muse", "B", [], teach="old"), row("muse", "B", KEYS, teach="new")]
        self.assertEqual(transfer.report("contract-transfer", rows=rows)["lines"][0]["completeness"], 1.0)
        self.assertEqual(transfer.report("contract-transfer", "old", rows=rows)["lines"][0]["completeness"], 0.0)

    def test_a_transfer_case_has_teaching_turns_and_scores_each_point(self):
        case = bench.cases()["contract-transfer"]
        self.assertEqual(len(case["teach"]), 3)
        self.assertTrue((case["dir"] / "teach_setup.py").is_file())
        self.assertEqual(transfer.render(transfer.report("contract-transfer", rows=[])),
                         "No transfer runs for contract-transfer yet. Run `athos bench transfer contract-transfer`.")


class OpenCodeEvents(TempHome):
    def test_a_run_that_used_no_tool_is_told_apart(self):
        talk = "\n".join(json.dumps(e) for e in [
            {"type": "text", "part": {"text": "I'll locate the agreement."}},
            {"type": "step_finish", "part": {"tokens": {"input": 10, "output": 2, "reasoning": 1,
                                                       "cache": {"read": 5}}}}])
        tokens = {"input": 0, "output": 0}
        acted, last, note = bench._opencode_events(talk, tokens)
        self.assertEqual((acted, last, note, tokens),
                         (False, "I'll locate the agreement.", "", {"input": 15, "output": 3}))
        acted, _, _ = bench._opencode_events(json.dumps({"type": "tool_use", "part": {"tool": "read"}}), tokens)
        self.assertFalse(acted)                                    # reading and stopping is the stall
        acted, _, _ = bench._opencode_events(json.dumps({"type": "tool_use", "part": {"tool": "write"}}), tokens)
        self.assertTrue(acted)


class Rescore(TempHome):
    def test_kept_reviews_are_scored_again_with_the_current_check(self):
        teach = transfer.teach_root() / "contract-transfer-x" / "reviews"
        teach.mkdir(parents=True)
        case = bench.cases()["contract-transfer"]
        ws = Path(tempfile.mkdtemp())
        subprocess.run([sys.executable, str(case["dir"] / "solve.py"), str(ws)], check=True)
        (teach / "muse-B-abc.md").write_text((ws / "review.md").read_text())
        old = {**row("muse", "B", []), "id": "abc", "teach": "contract-transfer-x"}
        bench.save(old)
        self.assertEqual(transfer.rescore("contract-transfer", "contract-transfer-x"), 1)
        new = [json.loads(x) for x in bench.results_file().read_text().splitlines()][0]
        self.assertEqual((new["verdict"], new["score"]), ("g", 1.0))


class MuseEvents(TempHome):
    def test_last_words_tokens_and_a_failed_end(self):
        talk = "\n".join(json.dumps(e) for e in [
            {"payload_type": "run.usage", "payload": {"models": [{"input_tokens": 7, "output_tokens": 2,
                                                                  "reasoning_tokens": 1}]}},
            {"payload_type": "run.terminal.completed", "payload": {"terminal": "completed",
                                                                   "text": "How do you edit your chapters?"}}])
        tokens = {"input": 0, "output": 0}
        self.assertEqual(bench._muse_events(talk, tokens), ("How do you edit your chapters?", ""))
        self.assertEqual(tokens, {"input": 7, "output": 3})
        failed = json.dumps({"payload_type": "run.terminal.failed", "payload": {"terminal": "failed",
                                                                                "reason": "network"}})
        self.assertEqual(bench._muse_events(failed, tokens)[1], "failed: network")

    def test_the_snapshot_sees_a_written_file_but_not_an_agents_own_folder(self):
        ws = Path(tempfile.mkdtemp())
        (ws / "chapter-2.md").write_text("x")
        before = bench._snapshot(ws)
        (ws / ".muse").mkdir()
        (ws / ".muse" / "state").write_text("y")
        self.assertEqual(bench._snapshot(ws), before)
        (ws / "edits.md").write_text("z")
        self.assertNotEqual(bench._snapshot(ws), before)


class Leaks(TempHome):
    def test_a_run_that_read_outside_is_left_out_and_counted_apart(self):
        rows = [row("codex", "A", []), {**row("codex", "A", KEYS), "looked_outside": True}]
        rep = transfer.report("contract-transfer", rows=rows)
        line = rep["lines"][0]
        self.assertEqual((line["runs"], line["completeness"], line["looked_outside"]), (1, 0.0, 1))
        self.assertIn("Left out of the table", transfer.render(rep))
