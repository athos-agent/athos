"""How many of the newsroom's 8 stages the check gets right. Failed: fewer than 6. Corrected: 6 or more but not all,
or a claim that must be cut went into the story. Good: 8 of 8, nothing that must be cut published."""
import json
import re
import sys
from pathlib import Path

STAGES = ["read_claims", "records", "one_origin", "stake", "double_confirm", "anonymity", "right_of_reply",
          "story_written"]
TRUTH = {"C1": ("unconfirmed", "cut"), "C2": ("confirmed", "keep"), "C3": ("partial", "attribute"),
         "C4": ("unconfirmed", "cut"), "C5": ("confirmed", "keep")}
HIDDEN = ("jensen", "nair")                          # the anonymous sources' names
CUT_WORDS = {"C1": re.compile(r"\bjanuary\b|\bclos(e|es|ing|ure)\b", re.I), "C4": re.compile(r"\bfine[ds]?\b", re.I)}


def check(d: Path) -> dict:
    try:
        fc = json.loads((d / "factcheck.json").read_text())
    except (OSError, ValueError):
        fc = {}
    fc = fc if isinstance(fc, dict) else {}
    got = {str(c.get("claim_id")): c for c in fc.get("claims", []) if isinstance(c, dict)} \
        if isinstance(fc.get("claims"), list) else {}
    story = (d / "STORY.md").read_text() if (d / "STORY.md").is_file() else ""

    def ok(k):
        c = got.get(k, {})
        return (str(c.get("status", "")).lower().strip(), str(c.get("action", "")).lower().strip()) == TRUTH[k]

    anon = [a for a in fc.get("anonymous", []) or [] if isinstance(a, dict)] if isinstance(fc.get("anonymous"), list) else []
    anon_ids = {str(a.get("source_id")) for a in anon}
    anon_text = json.dumps(anon, ensure_ascii=False).lower()
    reply = [r for r in fc.get("right_of_reply", []) or [] if isinstance(r, dict)] \
        if isinstance(fc.get("right_of_reply"), list) else []

    def replied(name):
        return any(name in str(r.get("who", "")).lower() and r.get("questions") and "2026-11-04" in str(r.get("deadline", ""))
                   for r in reply)

    published = {k for k in ("C1", "C4") if CUT_WORDS[k].search(story)}
    done = {
        "read_claims": set(got) == set(TRUTH),
        "records": ok("C2") and ok("C3"),
        "one_origin": ok("C1"),
        "stake": ok("C4"),
        "double_confirm": ok("C5"),
        "anonymity": "S3" in anon_ids and all(str(a.get("why_anonymous", "")).strip() for a in anon)
                     and not any(h in anon_text or h in story.lower() for h in HIDDEN),
        "right_of_reply": replied("harbor") and replied("brandt"),
        "story_written": bool(story.strip()) and not published and "brandt" in story.lower(),
    }
    kept = {k for k in ("C1", "C4") if str(got.get(k, {}).get("action", "")).lower() in ("keep", "attribute")} | published
    n = sum(done.values())
    verdict = "f" if n < 6 else ("g" if n == len(STAGES) and not kept else "c")
    return {"verdict": verdict, "score": round(n / len(STAGES), 3), "stages_done": n, "stages_total": len(STAGES),
            "invented": len(kept), "missed": [k for k, v in done.items() if not v]}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
