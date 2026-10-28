"""A correct solution, used only by the tests."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import expected  # noqa: E402


def main(d: Path) -> None:
    exp = expected(d)
    order = sorted(exp, key=lambda k: -exp[k]["cents"])
    (d / "reports").mkdir(exist_ok=True)
    lines = ["# Sales report — October 2026", "", "| Region | Orders | Revenue (USD) |", "|---|---|---|"]
    lines += [f"| {k} | {exp[k]['orders']} | {exp[k]['cents'] / 100:.2f} |" for k in order]
    to, tc = sum(v["orders"] for v in exp.values()), sum(v["cents"] for v in exp.values())
    lines.append(f"| Total | {to} | {tc / 100:.2f} |")
    (d / "reports" / "2026-10.md").write_text("\n".join(lines) + "\n")
    (d / "reports" / "2026-10.json").write_text(json.dumps({
        "regions": {k: {"orders": v["orders"], "revenue": round(v["cents"] / 100, 2)} for k, v in exp.items()},
        "total": {"orders": to, "revenue": round(tc / 100, 2)}}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
