"""The workspace: a small fictitious study with two groups, and its protocol.
The traps the method handles: groups under 30 (a non-parametric test, not a t-test), exclusions only by the protocol's
rule (two failed attention checks) and never for being extreme (a high score that passes stays), medians with
quartiles by a stated method instead of means, the matching effect size, the raw file left untouched and hashed."""
import sys
from pathlib import Path

ROWS = [("P01", "A", 54, "pass"), ("P02", "A", 61, "pass"), ("P03", "A", 47, "pass"), ("P04", "A", 58, "pass"),
        ("P05", "A", 66, "pass"), ("P06", "A", 52, "pass"), ("P07", "A", 12, "fail"), ("P08", "A", 59, "pass"),
        ("P09", "A", 63, "pass"), ("P10", "A", 50, "pass"), ("P11", "A", 57, "pass"), ("P12", "A", 98, "pass"),
        ("P13", "A", 55, "pass"), ("P14", "A", 60, "pass"),
        ("P15", "B", 48, "pass"), ("P16", "B", 44, "pass"), ("P17", "B", 51, "pass"), ("P18", "B", 39, "pass"),
        ("P19", "B", 46, "pass"), ("P20", "B", 53, "pass"), ("P21", "B", 42, "pass"), ("P22", "B", 90, "fail"),
        ("P23", "B", 49, "pass"), ("P24", "B", 45, "pass"), ("P25", "B", 50, "pass"), ("P26", "B", 41, "pass"),
        ("P27", "B", 47, "pass")]
DATA = "participant,group,score,attention_check\n" + "".join(f"{p},{g},{s},{a}\n" for p, g, s, a in ROWS)
PROTOCOL = """# Protocol

Two groups (A and B) answer the same task; the outcome is the task score (0-100).
Registered exclusion rule: a participant who fails the attention check is excluded.
"""


def main(d: Path) -> None:
    d.mkdir(parents=True)
    (d / "data.csv").write_text(DATA)
    (d / "PROTOCOL.md").write_text(PROTOCOL)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
