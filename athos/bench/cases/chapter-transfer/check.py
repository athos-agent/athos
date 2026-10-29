"""Which of the author's editing rules the edited chapter applies: the eight of their style guide and the two they
added while teaching ("the water", never "the sea" or "the ocean"; British spelling). The replay workspace has no
style guide, so each rule applied came from their know-how (or from the model's own sense, which the run without
know-how measures). Good: all 10. Corrected: 7 or more. Failed: fewer."""
import json
import re
import sys
from pathlib import Path


def paragraphs(text: str) -> int:
    return len([b for b in re.split(r"\n\s*\n", text) if b.strip() and not b.strip().startswith("#")])


def check(d: Path) -> dict:
    f, log = d / "chapter-2-edited.md", d / "edits.md"
    text = f.read_text() if f.is_file() else ""
    edits = log.read_text() if log.is_file() else ""
    body = "\n".join(ln for ln in text.splitlines() if not ln.startswith("#"))
    original = (d / "chapter-2.md").read_text() if (d / "chapter-2.md").is_file() else ""
    items = {
        # From the style guide the author taught with.
        "past_tense": bool(text) and not re.search(r"\b(knocks|opens|waits)\b", body),
        "dialogue_in_quotes": bool(text) and not re.search(r"^\s*[—–-]\s", body, re.M) and body.count('"') + body.count("“") >= 6,
        "dialogue_words_kept": "We was never going back, not after the winter" in text
                               and "He talks about you on the bad nights" in text,
        "no_adverb_tags": bool(text) and not re.search(r"\b(said|called|answered|asked)\s+\w+ly\b", body, re.I),
        "numbers_in_words": bool(text) and not re.search(r"\b(1|3|12)\b", body) and "twelve" in body.lower(),
        "name_spelling": bool(text) and "Ilsa" not in text,
        "changes_listed": len(re.findall(r"^\s*([-*]|\d+[.)]|\|)\s*\S", edits, re.M)) >= 5,
        "no_paragraph_cut": bool(text) and paragraphs(text) >= paragraphs(original),
        # The two rules the author added while teaching: they exist nowhere but in their know-how.
        "the_water": bool(text) and not re.search(r"\bthe (sea|ocean)\b", body, re.I),
        "british_spelling": bool(text) and not re.search(r"\b(color|gray|harbor)\b", body, re.I)
                            and all(w in body.lower() for w in ("colour", "grey", "harbour")),
    }
    missed = [k for k, v in items.items() if not v]
    if not text:
        missed = ["chapter-2-edited.md not written"] + missed
    n = sum(items.values())
    verdict = "g" if n == len(items) else "c" if n >= 7 else "f"
    return {"verdict": verdict, "score": round(n / len(items), 2), "missed": missed, "items": items,
            "sources": {k: ("taught" if k in ("the_water", "british_spelling") else "checklist") for k in items}}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
