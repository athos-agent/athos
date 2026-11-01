import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A plain YAML scalar can't hold ": " (YAML reads a second mapping). Claude Code tolerates it; Muse Code refuses the
# whole plugin ("Claude command frontmatter is invalid YAML", 2026-11-01, commands/codex.md and commands/mark.md).
PLAIN_WITH_COLON = re.compile(r"^[\w-]+: (?![\"'|>\[{]).*: ", re.MULTILINE)


class FrontmatterTest(unittest.TestCase):
    def test_every_command_skill_and_agent_frontmatter_is_valid_yaml_for_muse_code(self):
        files = [*ROOT.glob("commands/*.md"), *ROOT.glob("skills/**/*.md"), *ROOT.glob("agents/*.md")]
        self.assertTrue(files)
        for f in files:
            m = re.match(r"---\n(.*?)\n---", f.read_text(), re.S)
            if m:
                self.assertIsNone(PLAIN_WITH_COLON.search(m.group(1)), f"{f.relative_to(ROOT)}: quote the value")
