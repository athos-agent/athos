"""The workspace: one month of orders with refunds, pending orders and QA orders mixed in."""
import random
import sys
from pathlib import Path

REGIONS = ["North", "South", "East", "West", "Online"]


def main(d: Path) -> None:
    rng = random.Random(2610)
    (d / "data").mkdir(parents=True)
    rows = ["order_id,date,region,amount_cents,status"]
    for i in range(1, 181):
        status = rng.choices(["paid", "refunded", "pending"], [0.8, 0.12, 0.08])[0]
        oid = f"TEST-{i:04d}" if i % 23 == 0 else f"ORD-{10000 + i}"
        rows.append(f"{oid},2026-10-{rng.randint(1, 31):02d},{rng.choice(REGIONS)},{rng.randint(500, 250000)},{status}")
    (d / "data" / "orders-2026-10.csv").write_text("\n".join(rows) + "\n")
    (d / "README.md").write_text("# Sales\n\nMonthly orders exports live in data/. Reports go in reports/.\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
