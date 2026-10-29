"""A review that applies every point of the lawyer's know-how: the check must pass it."""
import sys
from pathlib import Path

REVIEW = """# Review of services-agreement.md (for the Provider)

| Clause | Issue | Proposed wording | Priority |
|---|---|---|---|
| 3. Fees | 120 days to pay, and no late interest | "The Client pays within 30 days of each invoice; late amounts accrue interest at [x]% per month." | must |
| 7. Liability | Unlimited, direct and indirect | "Each party's liability is limited to direct damage, capped at the fees paid in the last 12 months." | must |
| (missing) Governing law | The agreement names no governing law | "This agreement is governed by the laws of [jurisdiction]." | must |
| 4. Security | The Client may keep it at will; no return conditions | "The security is returned within 15 days of acceptance of the work." | should |
| 5. Termination | One-sided: 7 days for the Client, a penalty for the Provider | "Either party may terminate on 30 days' notice, without penalty." | should |
| 6. Intellectual property | Rights pass before payment | "Rights pass to the Client on full payment." | should |
| 2. Term | Automatic renewal that only the Provider can stop | "Renewal requires written agreement of both parties." | minor |
| 8. Jurisdiction | Courts of the Client's domicile | "The courts of [neutral seat]." | minor |

Push first: 7 (liability), 3 (fees), the missing governing law. These are proposals: what to negotiate is your client's decision.
"""

if __name__ == "__main__":
    (Path(sys.argv[1]) / "review.md").write_text(REVIEW)
