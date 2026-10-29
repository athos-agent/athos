"""The replay workspace: another fictitious contract, and no checklist: what the lawyer taught must come from their
know-how, or it is missing."""
import sys
from pathlib import Path

SERVICES = """# SERVICES AGREEMENT (FICTITIOUS)

Between EXAMPLE CLIENT INC. ("the Client") and SAMPLE DESIGN STUDIO ("the Provider").

1. SCOPE. The Provider will design the Client's visual identity as set out in schedule A.
2. TERM. Twelve months, renewing automatically for equal periods unless the Provider gives 90 days' notice.
3. FEES. 5,000 units per month; the Client pays 120 days after receiving each invoice.
4. SECURITY. The Provider deposits 10,000 units, which the Client may keep if it finds the work unsatisfactory.
5. TERMINATION. The Client may terminate on 7 days' notice. If the Provider terminates, it pays three months' fees.
6. INTELLECTUAL PROPERTY. Everything created belongs to the Client from creation, paid for or not.
7. LIABILITY. The Provider is liable for any damage, direct or indirect, without limit.
8. JURISDICTION. The courts of the Client's domicile.
"""

if __name__ == "__main__":
    d = Path(sys.argv[1])
    d.mkdir(parents=True, exist_ok=True)
    (d / "services-agreement.md").write_text(SERVICES)
