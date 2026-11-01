"""A correct solution, used only by the tests."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import STAGES, truth  # noqa: E402


def main(d: Path) -> None:
    t = truth(d)
    claims = [{"claim_id": k, "decision": r["decision"], "reimburse_usd": float(r["reimburse"]),
               "fx_rate": float(r["fx"]) if r["fx"] is not None else None, "reason": r["why"]}
              for k, r in t["claims"].items()]
    rev = {"stages": STAGES, "claims": claims, "totals": {e: float(v) for e, v in t["totals"].items()},
           "total_usd": float(t["total"]), "open_decisions": [f"{k}: for the finance lead" for k in t["open"]]}
    (d / "review.json").write_text(json.dumps(rev, indent=2))
    (d / "REVIEW.md").write_text("# Expense review — October 2026\n\nSee review.json.\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
