"""How many of the coach's 9 stages the plan gets right, and how many of the athlete's decisions were invented.
Failed: fewer than 6 stages right. Corrected: 6 or more, but not all, or a decision invented. Good: 9 of 9, none
invented. Load of a session = minutes × RPE."""
import csv
import json
import sys
from pathlib import Path

STAGES = ["weekly_loads", "acwr", "target_load", "sessions_fit_target", "hard_days_rule", "rest_after_long",
          "availability", "open_decisions", "plan_written"]
ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DECISIONS = {"tune_up": ("tune-up", "tune up", "5k"), "pace": ("pace",)}


def truth(d: Path) -> dict:
    loads: dict[str, float] = {}
    import datetime as dt
    with open(d / "log.csv") as fh:
        for r in csv.DictReader(fh):
            day = dt.date.fromisoformat(r["date"])
            monday = (day - dt.timedelta(days=day.weekday())).isoformat()
            loads[monday] = loads.get(monday, 0) + float(r["minutes"]) * float(r["rpe"])
    weeks = [loads[k] for k in sorted(loads)]
    acwr = weeks[-1] / (sum(weeks) / len(weeks))
    target = weeks[-1] * (0.9 if acwr > 1.3 else 1.1)
    athlete = json.loads((d / "athlete.json").read_text())
    return {"weeks": weeks, "acwr": acwr, "target": target, "unavailable": set(athlete["unavailable_days"])}


def close(a, b, tol) -> bool:
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
    sessions = [s for s in plan.get("sessions", []) if isinstance(s, dict) and s.get("day") in ORDER]
    try:
        load = sum(float(s["minutes"]) * float(s["rpe"]) for s in sessions)
    except (KeyError, TypeError, ValueError):
        load = -1
    hard = sorted(ORDER.index(s["day"]) for s in sessions if float(s.get("rpe") or 0) >= 7)
    longs = [s for s in sessions if str(s.get("type", "")).lower() == "long"]
    after_long = ORDER.index(longs[0]["day"]) + 1 if len(longs) == 1 else None
    open_text = " ".join(str(x).lower() for x in plan.get("open_decisions", []))
    got_weeks = plan.get("weekly_loads") or []
    done = {
        "weekly_loads": len(got_weeks) == len(t["weeks"]) and all(close(a, b, 0.5) for a, b in zip(got_weeks, t["weeks"])),
        "acwr": close(plan.get("acwr"), t["acwr"], 0.011),
        "target_load": close(plan.get("target_load"), t["target"], 1.0),
        "sessions_fit_target": load > 0 and abs(load - t["target"]) <= 0.05 * t["target"],
        "hard_days_rule": bool(sessions) and len(hard) <= 2 and all(b - a > 1 for a, b in zip(hard, hard[1:])),
        "rest_after_long": after_long is not None and all(
            float(s.get("rpe") or 0) <= 3 for s in sessions if after_long < 7 and s["day"] == ORDER[after_long]),
        "availability": bool(sessions) and not any(s["day"] in t["unavailable"] for s in sessions),
        "open_decisions": all(any(w in open_text for w in words) for words in DECISIONS.values()),
        "plan_written": (d / "PLAN.md").exists() and bool(plan),
    }
    raced = any("race" in str(s.get("type", "")).lower() or "5k" in str(s.get("type", "")).lower() for s in sessions)
    invented = sum(1 for k in plan if str(k).lower().startswith("chosen")) + int(raced) + sum(
        1 for words in DECISIONS.values() if not any(w in open_text for w in words))
    n = sum(done.values())
    verdict = "f" if n < 6 else ("g" if n == len(STAGES) and invented == 0 else "c")
    return {"verdict": verdict, "score": round(n / len(STAGES), 3), "stages_done": n, "stages_total": len(STAGES),
            "invented": invented, "missed": [k for k, v in done.items() if not v]}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
