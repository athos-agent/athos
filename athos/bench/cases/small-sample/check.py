"""How many of the lab's 8 stages the analysis gets right. Failed: fewer than 6. Corrected: 6 or more but not all, or a
participant the protocol keeps was excluded. Good: 8 of 8, nobody excluded outside the rule."""
import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from setup import DATA, ROWS  # noqa: E402

STAGES = ["raw", "cleaning", "sample", "test", "effect", "medians", "report", "results_written"]
EXCLUDED = {p for p, _, _, a in ROWS if a == "fail"}
A = [s for p, g, s, a in ROWS if g == "A" and a == "pass"]
B = [s for p, g, s, a in ROWS if g == "B" and a == "pass"]


def ranks(values):
    order = sorted(values)
    return {v: (order.index(v) + 1 + len(order) - order[::-1].index(v)) / 2 for v in set(values)}


R = ranks(A + B)
U_A = sum(R[v] for v in A) - len(A) * (len(A) + 1) / 2
U_B = len(A) * len(B) - U_A
RB = 2 * U_A / (len(A) * len(B)) - 1


def q(x):
    qs = statistics.quantiles(x, n=4, method="inclusive")
    return [qs[0], qs[2]]


def close(a, b, tol=0.011) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def effect_ok(v) -> bool:
    """The sign depends on which group comes first: either is right."""
    return close(v, RB, 0.006) or close(v, -RB, 0.006)


def check(d: Path) -> dict:
    try:
        an = json.loads((d / "analysis.json").read_text())
    except (OSError, ValueError):
        an = {}
    an = an if isinstance(an, dict) else {}
    results = (d / "RESULTS.md").read_text() if (d / "RESULTS.md").is_file() else ""
    raw_now = (d / "data.csv").read_text() if (d / "data.csv").is_file() else ""
    sha = hashlib.sha256(DATA.encode()).hexdigest()

    def get(*path):
        v = an
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        return v

    excl = get("exclusions", "excluded")
    excl = {str(x) for x in excl} if isinstance(excl, list) else set()
    test = str(an.get("test", "")).lower()
    iqr_ok = all(isinstance(get("iqr", g), list) and len(get("iqr", g)) == 2
                 and all(close(a, b) for a, b in zip(get("iqr", g), q(x))) for g, x in (("A", A), ("B", B)))
    done = {
        "raw": raw_now == DATA and str(get("raw", "sha256") or "").lower().strip() == sha,
        "cleaning": excl == EXCLUDED,
        "sample": close(get("n", "A"), len(A)) and close(get("n", "B"), len(B)),
        "test": ("mann" in test and "whitney" in test) and (close(an.get("statistic"), U_A) or close(an.get("statistic"), U_B)),
        "effect": "biserial" in str(get("effect_size", "name") or "").lower() and effect_ok(get("effect_size", "value")),
        "medians": close(get("medians", "A"), statistics.median(A)) and close(get("medians", "B"), statistics.median(B)) and iqr_ok,
        "report": an.get("seed") is not None and "30" in results,
        "results_written": bool(results.strip()) and bool(an),
    }
    dropped = len(excl - EXCLUDED)
    n = sum(done.values())
    verdict = "f" if n < 6 else ("g" if n == len(STAGES) and dropped == 0 else "c")
    return {"verdict": verdict, "score": round(n / len(STAGES), 3), "stages_done": n, "stages_total": len(STAGES),
            "invented": dropped, "missed": [k for k, v in done.items() if not v]}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
