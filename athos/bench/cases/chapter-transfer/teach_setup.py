"""The teaching workspace: the first chapter of the author's novel (written for this case) and their style guide."""
import sys
from pathlib import Path

CHAPTER = """# Chapter 1

The ferry left Puerto Nieve at dawn, when the sea was still the color of slate. Ilse stood at the rail with her
coat buttoned to the chin and counted 4 fishing boats tied up in the harbor below the lighthouse.

Her brother had promised to meet her on the other side. She does not believe him, not really, but she has nowhere
else to go.

— You came back, said the old ferryman softly.

— I said I would, Ilse answered quietly.

— Nobody comes back in March. The water don't like it.

Ilsa watched the gray gulls follow the wake. Suddenly the engine coughed and the whole deck shook under her boots.
The ferryman laughed and lit his pipe as if nothing at all had happened.

By noon the coast was a thin line behind them, and the ocean ahead was empty in every direction.
"""

GUIDE = """# My style guide

- Narration in the past tense, always. Fix any slip into the present.
- Dialogue in double quotes, never dashes.
- Never change what a character says: their words stay exactly as written, grammar included.
- Dialogue tags without adverbs: "said", not "said softly".
- Numbers under one hundred in words ("four boats", not "4 boats").
- The heroine is Ilse. Never Ilsa.
- List every change in edits.md with its reason.
- Cutting is my decision: don't delete paragraphs; suggest cuts in edits.md instead.
"""

if __name__ == "__main__":
    d = Path(sys.argv[1])
    d.mkdir(parents=True, exist_ok=True)
    (d / "chapter-1.md").write_text(CHAPTER)
    (d / "style-guide.md").write_text(GUIDE)
