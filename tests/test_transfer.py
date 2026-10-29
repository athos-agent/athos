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
