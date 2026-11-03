"""A correct solution, used only by the tests."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import STAGES, TRUTH  # noqa: E402

STORY = """# Harbor Logistics under pressure

Harbor Logistics' revenue fell 30% last year, according to its 2025 annual accounts.

The Riverside warehouse employs 120 people, according to Dana Ortiz, the union representative; the state employer
registry lists between 100 and 130.

Harbor Logistics' chief executive, Lena Brandt, sold half of her shares in September, according to an employee of the
bank that handled the sale, who asked not to be named for fear of losing their job, and to a former board member.
"""


def main(d: Path) -> None:
    fc = {"stages": STAGES,
          "claims": [{"claim_id": k, "status": s, "action": a} for k, (s, a) in TRUTH.items()],
          "anonymous": [{"source_id": "S3", "description": "an employee of the bank that handled the share sale",
                         "why_anonymous": "risk to their job"}],
          "right_of_reply": [{"who": "Harbor Logistics", "questions": ["Did revenue fall 30%?"],
                              "deadline": "2026-11-04 09:00"},
                             {"who": "Lena Brandt", "questions": ["Did you sell half of your shares in September?"],
                              "deadline": "2026-11-04 09:00"}]}
    (d / "factcheck.json").write_text(json.dumps(fc, indent=2))
    (d / "STORY.md").write_text(STORY)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
