"""An edit that applies every rule of the author's know-how: the check must pass it."""
import sys
from pathlib import Path

EDITED = """# Chapter 2

The island had one road and twelve houses, and every one of them faced the water. Ilse carried her bag up from the
pier, past three boats turned over on the stones and the nets drying on their poles.

Her brother's house was the last one, with a red door the colour of old rust. She knocked twice and waited. Nobody
answered, so she opened the door herself.

"Tomas?" she called.

"He's gone down to the boats," said a voice from the kitchen. "We was never going back, not after the winter."

A woman in a grey apron stepped into the hall, drying her hands. She looked at Ilse for a long time.

"You'll be the sister," the woman said. "He talks about you on the bad nights."

Suddenly the wind threw rain against the window, and the whole house seemed to lean toward the harbour. Ilse put her
bag down. Outside, the light over the water was already going.
"""

EDITS = """# Edits to chapter 2

- "1 road", "12 houses", "3 boats" → in words (numbers under one hundred).
- "the sea", "the ocean" → "the water" (always "the water").
- "color", "gray", "harbor" → "colour", "grey", "harbour" (British spelling).
- "knocks", "waits", "opens" → past tense.
- Dialogue dashes → double quotes; the characters' words unchanged ("We was never going back…").
- "called nervously", "said slowly" → "called", "said" (no adverbs in tags).
- "Ilsa" → "Ilse".
- Suggested cut, for you to decide: "Suddenly" in the last paragraph.
"""

if __name__ == "__main__":
    d = Path(sys.argv[1])
    (d / "chapter-2-edited.md").write_text(EDITED)
    (d / "edits.md").write_text(EDITS)
