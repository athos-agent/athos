import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from athos import bench
from tests.helpers import TempHome

CASES = {k: v for k, v in bench.cases().items() if v["dir"].parent == bench.CASES}   # the shipped ones


def solve(case: dict, ws: Path) -> None:
    subprocess.run([sys.executable, str(case["dir"] / "solve.py"), str(ws)], check=True, capture_output=True)


class Workspace(unittest.TestCase):
    def ws(self, name: str, solved: bool = True) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = Path(tmp.name) / "work"
        bench.setup(CASES[name], ws)
        if solved:
            solve(CASES[name], ws)
        return ws

    def verdict(self, name: str, ws: Path) -> dict:
        return bench.check(CASES[name], ws)


class Checks(Workspace):
    """Each case's check fails an untouched workspace, passes the reference solution and catches a broken one."""

    def test_every_case_is_complete(self):
        self.assertEqual(set(CASES), {"release", "monthly-report", "device-setup", "tile-plan", "training-week",
                                          "contract-transfer", "chapter-transfer"})
        for name, c in CASES.items():
            for f in ("case.json", "piece.md", "setup.py", "check.py", "solve.py"):
                self.assertTrue((c["dir"] / f).exists(), f"{name}/{f}")
            self.assertTrue(c["request"] and c["when"] and c["domain"])

    def test_untouched_fails_and_solution_is_good(self):
        for name in CASES:
            with self.subTest(name):
                self.assertEqual(self.verdict(name, self.ws(name, solved=False))["verdict"], "f")
                r = self.verdict(name, self.ws(name))
                self.assertEqual((r["verdict"], r["missed"]), ("g", []))

    def test_release_without_a_new_test_is_corrected(self):
        ws = self.ws("release", solved=False)
        solve(CASES["release"], ws)
        t = ws / "tests" / "test_greet.py"
        t.write_text(t.read_text().split("\n    def test_name_upper")[0] + "\n")
        subprocess.run(["git", "-c", "user.name=b", "-c", "user.email=b@e", "commit", "-qam", "drop test"], cwd=ws,
                       check=True)
        r = self.verdict("release", ws)
        self.assertNotEqual(r["verdict"], "g")

    def test_report_counting_test_orders_is_not_good(self):
        ws = self.ws("monthly-report")
        p = ws / "reports" / "2026-10.json"
        d = json.loads(p.read_text())
        d["total"]["orders"] += 7
        p.write_text(json.dumps(d))
        self.assertNotEqual(self.verdict("monthly-report", ws)["verdict"], "g")

    def test_device_without_save_is_not_good(self):
        ws = self.ws("device-setup", solved=False)
        for cmd in (["set", "hostname", "mvd-gw-03"], ["set", "vlan", "30"], ["set", "ntp", "ntp.internal.example"],
                    ["set", "interval", "60"], ["firewall", "on"], ["network", "up"]):
            subprocess.run([sys.executable, "devctl.py", *cmd], cwd=ws, check=True, capture_output=True)
        self.assertNotEqual(self.verdict("device-setup", ws)["verdict"], "g")

    def test_device_network_before_firewall_is_not_good(self):
        ws = self.ws("device-setup", solved=False)
        for cmd in (["set", "hostname", "mvd-gw-03"], ["set", "vlan", "30"], ["set", "ntp", "ntp.internal.example"],
                    ["set", "interval", "60"], ["network", "up"], ["firewall", "on"], ["save"]):
            subprocess.run([sys.executable, "devctl.py", *cmd], cwd=ws, check=True, capture_output=True)
        self.assertNotEqual(self.verdict("device-setup", ws)["verdict"], "g")

    def test_tile_plan_subtracting_the_vent_or_choosing_a_tile(self):
        ws = self.ws("tile-plan")
        plan = json.loads((ws / "plan.json").read_text())
        vent = dict(plan, walls_net_m2=round(plan["walls_net_m2"] - 0.04, 2))
        (ws / "plan.json").write_text(json.dumps(vent))
        r = self.verdict("tile-plan", ws)
        self.assertEqual(r["verdict"], "c")
        self.assertIn("subtract_openings", r["missed"])
        chosen = dict(plan, chosen_tile="A30", open_decisions=["Budget"])
        (ws / "plan.json").write_text(json.dumps(chosen))
        r = self.verdict("tile-plan", ws)
        self.assertEqual((r["verdict"], r["invented"]), ("c", 3))

    def test_tile_plan_numbers(self):
        ws = self.ws("tile-plan")
        plan = json.loads((ws / "plan.json").read_text())
        self.assertEqual((plan["floor_m2"], plan["walls_net_m2"], plan["total_with_waste_m2"]), (4.32, 15.74, 22.07))
        self.assertEqual({o["sku"]: (o["boxes"], o["cost_usd"]) for o in plan["options"]},
                         {"A30": (16, 448.0), "B60": (16, 736.0), "C2060": (19, 665.0)})


class Runner(TempHome):
    """The bench with a fake agent: the reference solution when it has the know-how, nothing without it."""

    @staticmethod
    def fake(case, ws, home, with_piece, model=None):
        if with_piece:
            solve(case, ws)
        return {"tokens": {"input": 100, "output": 10}, "cost_usd": 0.01 if model == "cheap" else 0.2,
                "model": model or "big", "note": ""}

    def test_runs_check_save_and_report(self):
        rows = bench.run(["tile-plan", "device-setup"], ["claude"], runs=2, without_piece=True, out=lambda *_: None,
                         runner=self.fake)
        self.assertEqual(len(rows), 8)
        self.assertEqual({(r["know_how"], r["verdict"]) for r in rows}, {(True, "g"), (False, "f")})
        self.assertEqual(len(bench.load_results()), 8)
        self.assertTrue(str(bench.results_file()).startswith(self.home))
        rep = bench.report()
        lines = rep["tile-plan"]["lines"]
        self.assertEqual([(x["know_how"], x["success"]) for x in lines], [(True, 1.0), (False, 0.0)])
        self.assertEqual(lines[1]["median_invented"], 3)
        self.assertIn("tile-plan", bench.render(rep))

    def test_recommends_the_cheapest_at_the_best_success(self):
        rows = []
        for model in ("big", "cheap"):
            rows += bench.run(["tile-plan"], ["meta"], runs=1, models={"meta": model}, out=lambda *_: None,
                              runner=self.fake)
        rec = bench.report(rows)["tile-plan"]["recommend"]
        self.assertEqual((rec["model"], rec["median_cost_usd"]), ("cheap", 0.01))

    def test_spend_cap_stops_the_bench(self):
        said = []
        rows = bench.run(["tile-plan"], ["claude"], runs=5, max_usd=0.3, out=said.append, runner=self.fake)
        self.assertEqual(len(rows), 2)
        self.assertIn("cap", said[-1])

    def test_report_survives_runs_without_a_score(self):
        rows = [{"case": "x", "agent": "claude", "model": "m", "know_how": True, "verdict": "f", "score": 0.0,
                 "duration_s": 1.0, "tokens": {}, "cost_usd": None, "stages_done": None, "invented": None}]
        self.assertIn("stages ?", bench.render(bench.report(rows)))

    def test_a_crashing_agent_is_a_failed_run(self):
        def boom(*_a, **_k):
            raise RuntimeError("no network")
        row = bench.run_once("tile-plan", CASES["tile-plan"], "meta", runner=boom)
        self.assertEqual(row["verdict"], "f")
        self.assertIn("no network", row["note"])
        self.assertEqual(row["model"], "muse-spark-1.3")

    def test_workspace_hides_agent_folders_from_git(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ws = Path(tmp.name) / "w"
        bench.setup(CASES["release"], ws)
        (ws / ".agents" / "skills").mkdir(parents=True)
        (ws / ".agents" / "skills" / "x.md").write_text("x")
        out = subprocess.run(["git", "status", "--porcelain"], cwd=ws, capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "")

    def test_own_cases_folder_and_env(self):
        own = Path(self.home) / "bench" / "cases" / "mine"
        own.mkdir(parents=True)
        (own / "case.json").write_text(json.dumps({"title": "Mine", "domain": "x", "when": "w", "request": "r",
                                                   "timeout_s": 5400}))
        (own / "piece.md").write_text("p")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        other = Path(tmp.name) / "theirs"
        other.mkdir()
        (other / "case.json").write_text(json.dumps({"title": "T", "domain": "x", "when": "w", "request": "r"}))
        (other / "piece.md").write_text("p")
        old = os.environ.get("ATHOS_BENCH_CASES")
        os.environ["ATHOS_BENCH_CASES"] = tmp.name
        try:
            found = bench.cases()
        finally:
            os.environ.pop("ATHOS_BENCH_CASES") if old is None else os.environ.__setitem__("ATHOS_BENCH_CASES", old)
        self.assertIn("release", found)
        self.assertEqual(bench._timeout(found["mine"]), 5400)
        self.assertEqual(bench._timeout(found["theirs"]), bench.TIMEOUT)

    def test_cli_list_and_empty_report(self):
        from athos import cli
        self.assertEqual(cli.main(["bench", "--list"]), 0)
        self.assertEqual(cli.main(["bench", "report"]), 0)
        self.assertEqual(cli.main(["bench", "nope", "--agents", "claude"]), 1)


if __name__ == "__main__":
    unittest.main()
