"""A correct solution, used only by the tests."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import STAGES, truth  # noqa: E402


def main(d: Path) -> None:
    t = truth(d)
    fixed = [("Wed", "intervals", 50, 8), ("Fri", "tempo", 45, 7), ("Sat", "long", 100, 5)]
    rest = t["target"] - sum(m * r for _, _, m, r in fixed)
    easy = [(day, "easy", round(rest / 3 / 3), 3) for day in ("Mon", "Thu", "Sun")]
    sessions = [{"day": a, "type": b, "minutes": c, "rpe": e} for a, b, c, e in sorted(
        fixed + easy, key=lambda s: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].index(s[0]))]
    plan = {"stages": STAGES, "weekly_loads": t["weeks"], "acwr": round(t["acwr"], 2),
            "target_load": round(t["target"]), "sessions": sessions,
            "open_decisions": ["Whether to run the tune-up 5k on Saturday", "Goal pace for the 10k"]}
    (d / "plan.json").write_text(json.dumps(plan, indent=2))
    (d / "PLAN.md").write_text("# Training week from 2026-11-02\n\nSee plan.json.\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
