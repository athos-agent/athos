"""The report against the numbers the rules give. Failed: no JSON or wrong numbers (refunds, QA orders or cents
counted wrong). Corrected: right numbers, but the markdown misses the house format. Good: both."""
import csv
import json
import re
import sys
from pathlib import Path


def expected(d: Path) -> dict:
    regions: dict = {}
    with open(d / "data" / "orders-2026-10.csv") as fh:
        for r in csv.DictReader(fh):
            if r["status"] != "paid" or r["order_id"].startswith("TEST-"):
                continue
            g = regions.setdefault(r["region"], {"orders": 0, "cents": 0})
            g["orders"] += 1
            g["cents"] += int(r["amount_cents"])
    return regions


def check(d: Path) -> dict:
    exp = expected(d)
    missed = []
    try:
        got = json.loads((d / "reports" / "2026-10.json").read_text())
        numbers_ok = all(
            got["regions"][k]["orders"] == v["orders"] and abs(float(got["regions"][k]["revenue"]) - v["cents"] / 100) < 0.006
            for k, v in exp.items()) and set(got["regions"]) == set(exp)
        total_ok = (got["total"]["orders"] == sum(v["orders"] for v in exp.values())
                    and abs(float(got["total"]["revenue"]) - sum(v["cents"] for v in exp.values()) / 100) < 0.006)
    except (OSError, ValueError, KeyError, TypeError):
        numbers_ok = total_ok = False
    if not numbers_ok:
        missed.append("JSON numbers per region")
    if not total_ok:
        missed.append("JSON total")
    md = (d / "reports" / "2026-10.md").read_text() if (d / "reports" / "2026-10.md").exists() else ""
    conv = {
        "markdown title": "# Sales report — October 2026" in md,
        "table header": re.search(r"\|\s*Region\s*\|\s*Orders\s*\|\s*Revenue \(USD\)\s*\|", md) is not None,
    }
    rows = re.findall(r"^\|\s*([A-Za-z]+)\s*\|\s*(\d+)\s*\|\s*\$?([\d,]+\.\d{2})\s*\|", md, re.M)
    names = [r[0] for r in rows if r[0] not in ("Region", "Total")]
    order = sorted(exp, key=lambda k: -exp[k]["cents"])
    conv["regions sorted by revenue"] = names == order
    conv["total row last"] = bool(rows) and rows[-1][0] == "Total"
    conv["two decimals"] = all(re.fullmatch(r"[\d,]+\.\d{2}", r[2]) for r in rows) and bool(rows)
    missed += [k for k, v in conv.items() if not v]
    core_ok = numbers_ok and total_ok
    verdict = "f" if not core_ok else ("g" if all(conv.values()) else "c")
    total_checks = 2 + len(conv)
    return {"verdict": verdict, "score": round((total_checks - len(missed)) / total_checks, 3), "missed": missed}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
