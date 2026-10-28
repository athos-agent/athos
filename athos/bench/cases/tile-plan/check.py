"""How many of the method's 8 stages are done right, and how many of the client's decisions were invented.
Failed: fewer than 5 stages right. Corrected: 5 or more, but not all, or a decision invented. Good: 8 of 8, none
invented."""
import csv
import json
import math
import sys
from pathlib import Path

STAGES = ["measure_floor", "measure_walls", "subtract_openings", "add_waste", "options_per_supplier",
          "cost_per_option", "open_decisions", "plan_written"]
DECISIONS = {"tile": ("tile", "sku", "product"), "color": ("color", "colour"), "budget": ("budget",)}


def truth(d: Path) -> dict:
    room = json.loads((d / "room.json").read_text())
    floor = room["floor"]["length_m"] * room["floor"]["width_m"]
    walls = sum(w["length_m"] * w["height_m"] for w in room["walls_to_tile"])
    net = walls - sum(o["width_m"] * o["height_m"] for o in room["openings"] if o["width_m"] * o["height_m"] >= 0.1)
    total = (floor + net) * 1.10
    opts = {}
    with open(d / "suppliers.csv") as fh:
        for r in csv.DictReader(fh):
            boxes = math.ceil(total / float(r["m2_per_box"]) - 1e-9)
            opts[r["sku"]] = (boxes, round(boxes * float(r["price_per_box_usd"]), 2))
    return {"floor": floor, "walls": walls, "net": net, "total": total, "options": opts}


def close(a, b, tol=0.011) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def check(d: Path) -> dict:
    t = truth(d)
    try:
        plan = json.loads((d / "plan.json").read_text())
    except (OSError, ValueError):
        plan = {}
    got_opts = {o.get("sku"): o for o in plan.get("options", []) if isinstance(o, dict)}
    open_text = " ".join(str(x).lower() for x in plan.get("open_decisions", []))
    done = {
        "measure_floor": close(plan.get("floor_m2"), t["floor"]),
        "measure_walls": close(plan.get("walls_m2"), t["walls"]) or close(plan.get("walls_net_m2"), t["net"]),
        "subtract_openings": close(plan.get("walls_net_m2"), t["net"]),
        "add_waste": close(plan.get("total_with_waste_m2"), t["total"]),
        "options_per_supplier": set(got_opts) == set(t["options"]) and all(
            got_opts[k].get("boxes") == v[0] for k, v in t["options"].items()),
        "cost_per_option": set(got_opts) == set(t["options"]) and all(
            close(got_opts[k].get("cost_usd"), v[1], 0.51) for k, v in t["options"].items()),
        "open_decisions": all(any(w in open_text for w in words) for words in DECISIONS.values()),
        "plan_written": (d / "PLAN.md").exists() and bool(plan),
    }
    invented = sum(1 for k in plan if str(k).lower().startswith("chosen")) + sum(
        1 for words in DECISIONS.values() if not any(w in open_text for w in words))
    n = sum(done.values())
    verdict = "f" if n < 5 else ("g" if n == len(STAGES) and invented == 0 else "c")
    return {"verdict": verdict, "score": round(n / len(STAGES), 3), "stages_done": n, "invented": invented,
            "missed": [k for k, v in done.items() if not v]}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
