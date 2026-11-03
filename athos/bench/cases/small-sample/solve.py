"""A correct solution, used only by the tests."""
import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import A, B, EXCLUDED, RB, STAGES, U_A, q  # noqa: E402


def main(d: Path) -> None:
    sha = hashlib.sha256((d / "data.csv").read_bytes()).hexdigest()
    an = {"stages": STAGES, "raw": {"file": "data.csv", "sha256": sha},
          "exclusions": {"rule": "failed attention check", "excluded": sorted(EXCLUDED)},
          "n": {"A": len(A), "B": len(B)}, "test": "Mann-Whitney U", "statistic": U_A,
          "effect_size": {"name": "rank-biserial", "value": round(RB, 4)},
          "medians": {"A": statistics.median(A), "B": statistics.median(B)}, "iqr": {"A": q(A), "B": q(B)}, "seed": 0}
    (d / "analysis.json").write_text(json.dumps(an, indent=2))
    (d / "RESULTS.md").write_text(f"Mann-Whitney U because n per group ({len(A)}, {len(B)}) is under 30.\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
