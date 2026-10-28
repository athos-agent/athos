"""A correct solution, used only by the tests."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import STAGES, truth  # noqa: E402


def main(d: Path) -> None:
    t = truth(d)
    plan = {"stages": STAGES, "floor_m2": round(t["floor"], 2), "walls_net_m2": round(t["net"], 2),
            "total_with_waste_m2": round(t["total"], 2),
            "options": [{"sku": k, "boxes": b, "cost_usd": c} for k, (b, c) in t["options"].items()],
            "open_decisions": ["Which tile (A30, B60 or C2060)", "Tile color", "Budget"]}
    (d / "plan.json").write_text(json.dumps(plan, indent=2))
    (d / "PLAN.md").write_text("# Tiling plan — guest bathroom\n\nSee plan.json.\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
