"""The workspace: one month of fictitious expense claims in four currencies, and two months of exchange rates.
The traps the method handles: a duplicate, a claim from last month (last month's rate), a foreign taxi that is
under the receipt limit in its own currency but over it in dollars, a meal over the cap with an exception request."""
import sys
from pathlib import Path

CLAIMS = """claim_id,employee,date,category,amount,currency,receipt,note
C01,ana,2026-10-03,meals,42.50,USD,yes,team lunch
C02,ana,2026-10-03,taxi,18.00,USD,no,airport
C03,ana,2026-10-03,taxi,18.00,USD,no,airport
C04,ana,2026-10-07,meals,95.00,USD,yes,"client dinner, asking for an exception to the meal cap"
C05,ben,2026-09-28,hotel,120.00,EUR,yes,Lisbon fair
C06,ben,2026-10-12,meals,85000,ARS,yes,dinner in Buenos Aires
C07,ben,2026-10-12,alcohol,30.00,USD,yes,wine with the dinner
C08,ben,2026-10-14,software,89.00,USD,no,design tool licence
C09,cara,2026-10-02,train,64.00,GBP,yes,London to Leeds
C10,cara,2026-10-02,meals,58.00,USD,yes,dinner
C11,cara,2026-10-09,taxi,70.00,EUR,no,Madrid
C12,cara,2026-10-20,personal,25.00,USD,yes,gym day pass
C13,ana,2026-10-21,hotel,210.00,USD,yes,two nights
C14,cara,2026-10-02,train,64.00,GBP,yes,London to Leeds
"""
RATES = """month,currency,usd_per_unit
2026-09,EUR,1.10
2026-09,GBP,1.25
2026-09,ARS,0.0011
2026-10,EUR,1.08
2026-10,GBP,1.27
2026-10,ARS,0.0010
"""


def main(d: Path) -> None:
    d.mkdir(parents=True)
    (d / "claims.csv").write_text(CLAIMS)
    (d / "rates.csv").write_text(RATES)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
