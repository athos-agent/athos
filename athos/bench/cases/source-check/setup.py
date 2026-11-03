"""The workspace: a fictitious business story's claims, its sources and the documents the newsroom holds.
The traps the method handles: two sources where the second heard it from the first (one source, so the claim is cut),
a figure a record only partly backs (attributed), a claim from a source with a stake and no record (cut), an anonymous
claim confirmed by a second independent source (kept, the source described but never named), and the right of reply
with a deadline counted from the publication time."""
import sys
from pathlib import Path

CLAIMS = """claim_id,claim,source_ids
C1,Harbor Logistics will close its Riverside warehouse in January,S1;S2
C2,Harbor Logistics' revenue fell 30% last year,S4
C3,The Riverside warehouse employs 120 people,S2
C4,Harbor Logistics was fined in 2024 for breaking safety rules,S4
C5,"Harbor Logistics' chief executive, Lena Brandt, sold half of her shares in September",S3;S5
"""
SOURCES = """source_id,name,role,how_known,stake,anonymous,heard_from
S1,Mark Jensen,shift supervisor at the Riverside warehouse,saw an internal memo,none,yes,
S2,Dana Ortiz,union representative,was told,none,no,S1
S3,Priya Nair,employee of the bank that handled the share sale,saw the transfer documents,none,yes,
S4,Tom Keller,chief executive of a competing logistics company,was told,competitor,no,
S5,Ravi Shah,former board member of Harbor Logistics,was told by Lena Brandt,none,no,
"""
RECORDS = """record_id,kind,says
R1,company registry (annual accounts 2025),"Harbor Logistics: revenue 2025 down 30% on 2024"
R2,state employer registry,"Harbor Logistics, Riverside site: between 100 and 130 employees"
R3,court file search,"No proceedings found against Harbor Logistics"
"""


def main(d: Path) -> None:
    d.mkdir(parents=True)
    (d / "claims.csv").write_text(CLAIMS)
    (d / "sources.csv").write_text(SOURCES)
    (d / "records.csv").write_text(RECORDS)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
