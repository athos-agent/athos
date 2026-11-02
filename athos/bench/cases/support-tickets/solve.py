"""A correct solution, used only by the tests."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check import LANG, STAGES, TRUTH  # noqa: E402

TEXT = {"T08": "We will write again within 24 business hours with the carrier's update.",
        "T09": "Por seguridad, nunca nos envíes números de tarjeta. Pasanos solo los últimos 4 dígitos y la fecha del cobro.",
        "T06": "The support lead will answer you within one business day."}


def main(d: Path) -> None:
    sign = {"en": "— Support team", "es": "— Equipo de soporte"}
    tickets = [{"ticket_id": k, "decision": dec, "refund_amount": amt, "tag": "",
                "reply": f"{TEXT.get(k, 'Thanks for writing.')}\n\n{sign[LANG.get(k, 'en')]}"}
               for k, (dec, amt) in TRUTH.items()]
    (d / "replies.json").write_text(json.dumps({"stages": STAGES, "tickets": tickets, "escalations": ["T06"]},
                                               ensure_ascii=False, indent=2))
    (d / "REPLIES.md").write_text("# Replies — 2026-10-31\n\nOne escalation: T06.\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
