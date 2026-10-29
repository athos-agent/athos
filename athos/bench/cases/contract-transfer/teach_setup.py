"""The teaching workspace: a fictitious lease and the lawyer's own checklist."""
import sys
from pathlib import Path

LEASE = """# RESIDENTIAL LEASE (FICTITIOUS)

Between EXAMPLE PROPERTIES LLC ("the Landlord") and ANN SAMPLE ("the Tenant").

1. PREMISES. The Landlord leases 123 Fictional Street, apt. 4, as a residence.
2. TERM. Two years from December 1, 2026, renewing automatically unless the Tenant gives 180 days' notice.
3. RENT. 3,000 units per month, adjusted every three months by an index the Landlord chooses.
4. DEPOSIT. Six months' rent, which the Landlord may keep at the end without giving a reason.
5. TERMINATION. The Landlord may terminate on 15 days' notice. The Tenant may not terminate before the end of the term.
6. REPAIRS. All repairs, structural ones included, are the Tenant's.
7. ASSIGNMENT. The Landlord may assign this lease without the Tenant's consent.
8. JURISDICTION. The courts the Landlord chooses.
"""

CHECKLIST = """# My checklist for reviewing contracts

- Parties, scope, term, price and payment, governing law and jurisdiction: say if any is missing.
- Deposit or security: amount and conditions for its return.
- Early termination and notice, for both sides: flag it if it is one-sided.
- Payment: days to pay and late interest.
- Liability: always capped; never unlimited.
- Automatic renewal, assignment and jurisdiction.
- Return a table: clause, issue, proposed wording, priority (must / should / minor).
- What to negotiate is the client's decision: propose, don't decide.
"""

if __name__ == "__main__":
    d = Path(sys.argv[1])
    d.mkdir(parents=True, exist_ok=True)
    (d / "lease.md").write_text(LEASE)
    (d / "my-checklist.md").write_text(CHECKLIST)
