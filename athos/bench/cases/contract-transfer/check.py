"""Which of the lawyer's points the review applies: the eight of their checklist file and the two rules they added
while teaching. The replay workspace has no checklist, so each point applied came from their know-how (or from the
model's own sense, which the run without know-how measures). Good: all 10. Corrected: 7 or more. Failed: fewer."""
import json
import re
import sys
from pathlib import Path


def rows(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip().startswith("|")]


def headers(table: list[str]) -> list[str]:
    """Every table's header row: the line just above a |---| separator (a review may open with a status table)."""
    return [table[i - 1].lower() for i, ln in enumerate(table) if i and re.fullmatch(r"[|:\-\s]+", ln.strip())]


def has(text: str, *patterns: str) -> bool:
    return all(re.search(p, text, re.IGNORECASE | re.DOTALL) for p in patterns)


def check(d: Path) -> dict:
    f = d / "review.md"
    text = f.read_text() if f.is_file() else ""
    table = rows(text)
    body = "\n".join(table).lower()
    items = {
        # From the checklist file the lawyer taught with.
        "table_columns": any(all(w in h for w in ("clause", "issue", "propos", "priority")) for h in headers(table)),
        "priority_scale": sum(w in body for w in ("must", "should", "minor")) >= 2,
        "payment_days_and_interest": has(text, r"120", r"interest"),
        "liability_capped": has(text, r"unlimited|without limit|no (cap|limit)|uncapped",
                                r"\bcap|shall not exceed|not to exceed|limited to|aggregate liability|limit(ed)? (of|at)"),
        "security_return": has(text, r"security|deposit", r"\breturn|refund|releas"),
        "termination_one_sided": has(text, r"terminat", r"one[- ]sided|asymmetr|unilateral|mutual|both (sides|parties)"
                                                     r"|either party|reciprocal|only the (client|provider|landlord|tenant)"),
        "renewal_and_jurisdiction": has(text, r"renew", r"jurisdiction|courts?"),
        "client_decides": has(text, r"(client'?s?|your) (own )?(decision|call|choice)|for (the|your|my) client to decide"
                                    r"|decision (on [^.]{0,60})?(is|stays|remains|rests) (with )?(the |your |my )?client"
                                    r"|(the|your|my) client decides"),
        # The two rules the lawyer added while teaching: they exist nowhere but in the know-how.
        "governing_law_row": any("governing law" in r.lower() and "must" in r.lower() for r in table),
        "push_first_line": bool(re.search(r"^\W*push first\W*:", text, re.IGNORECASE | re.MULTILINE)),
    }
    applied = [k for k, v in items.items() if v]
    missed = [k for k, v in items.items() if not v]
    if not text:
        missed = ["review.md not written"] + missed
    n = len(applied)
    verdict = "g" if n == len(items) else "c" if n >= 7 else "f"
    return {"verdict": verdict, "score": round(n / len(items), 2), "missed": missed, "items": items,
            "sources": {k: ("taught" if k in ("governing_law_row", "push_first_line") else "checklist") for k in items}}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
