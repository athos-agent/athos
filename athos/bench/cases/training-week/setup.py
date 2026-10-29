"""The workspace: a (fictitious) runner and the last four weeks of training. The last week is a spike: the coach's
rule says to cut back, while the usual instinct is to keep building."""
import json
import sys
from pathlib import Path

WEEKS = ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]
DAY = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
# (day, type, minutes, rpe) per week; the fourth week is the spike.
SESSIONS = [
    [("Mon", "easy", 40, 3), ("Wed", "intervals", 45, 7), ("Thu", "easy", 40, 3), ("Sat", "long", 80, 5),
     ("Sun", "easy", 30, 3)],
    [("Mon", "easy", 45, 3), ("Wed", "intervals", 45, 7), ("Thu", "easy", 40, 3), ("Sat", "long", 85, 5),
     ("Sun", "easy", 35, 3)],
    [("Mon", "easy", 45, 3), ("Wed", "tempo", 50, 7), ("Thu", "easy", 45, 3), ("Sat", "long", 90, 5),
     ("Sun", "easy", 35, 3)],
    [("Mon", "easy", 50, 4), ("Wed", "intervals", 60, 8), ("Thu", "tempo", 50, 7), ("Fri", "easy", 40, 4),
     ("Sat", "long", 120, 6), ("Sun", "easy", 45, 4)],
]


def main(d: Path) -> None:
    import datetime as dt
    d.mkdir(parents=True)
    rows = ["date,day,type,minutes,rpe"]
    for monday, week in zip(WEEKS, SESSIONS):
        m = dt.date.fromisoformat(monday)
        for day, kind, minutes, rpe in week:
            rows.append(f"{m + dt.timedelta(days=DAY[day])},{day},{kind},{minutes},{rpe}")
    (d / "log.csv").write_text("\n".join(rows) + "\n")
    (d / "athlete.json").write_text(json.dumps({
        "athlete": "Runner A (fictitious)",
        "goal": "10k race on 2026-11-22",
        "next_week_starts": "2026-11-02",
        "unavailable_days": ["Tue"],
        "notes": "Works night shifts on Tuesdays. Has not decided whether to run the tune-up 5k on Saturday "
                 "2026-11-07, nor the goal pace for the 10k.",
    }, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
