"""The replay workspace: the second chapter (written for this case) and no style guide: what the author taught must
come from their know-how, or it is missing."""
import sys
from pathlib import Path

CHAPTER = """# Chapter 2

The island had 1 road and 12 houses, and every one of them faced the sea. Ilse carried her bag up from the pier,
past 3 boats turned over on the stones and the nets drying on their poles.

Her brother's house was the last one, with a red door the color of old rust. She knocks twice and waits. Nobody
answers, so she opens the door herself.

— Tomas? she called nervously.

— He's gone down to the boats, said a voice from the kitchen. We was never going back, not after the winter.

A woman in a gray apron stepped into the hall, drying her hands. She looked at Ilsa for a long time.

— You'll be the sister, the woman said slowly. He talks about you on the bad nights.

Suddenly the wind threw rain against the window, and the whole house seemed to lean toward the harbor. Ilse put her
bag down. Outside, the light over the ocean was already going.
"""

if __name__ == "__main__":
    d = Path(sys.argv[1])
    d.mkdir(parents=True, exist_ok=True)
    (d / "chapter-2.md").write_text(CHAPTER)
