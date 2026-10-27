#!/bin/sh
# Before the take, off camera: Claude Code releases 0.2.0 once with the conventions spelled out, and Athos captures
# them as a piece. That run is the baseline every later run is measured against. Real run, about a minute.
set -eu
DEMO="${ATHOS_DEMO:-$HOME/athos-demo}"
export ATHOS_HOME="$DEMO/home"
cd "$DEMO/greet"
. .venv/bin/activate
ATHOS_BIN=$(ls -d "$HOME"/.claude/plugins/cache/athos/athos/*/bin/athos 2>/dev/null | sort -V | tail -1)

claude -p "Release version 0.2.0 and add an \`excited\` option to greet() that ends with '!!!'. Our conventions: the version lives in TWO places (pyproject.toml and greet/__init__.py __version__); the CHANGELOG entry goes on top as '## [X.Y.Z] - YYYY-MM-DD' with '### Added' / '### Fixed', keeping the older entries; run the tests (python -m pytest -q) before tagging; commit 'release X.Y.Z' and an annotated tag 'vX.Y.Z' whose message is 'greet X.Y.Z'." \
  --permission-mode acceptEdits --allowedTools "Bash Read Edit Write" --max-budget-usd 3 > /dev/null

python3 "$ATHOS_BIN" mark g
python3 "$ATHOS_BIN" export --codex .agents/skills > /dev/null
echo "Baseline done:"; git log --oneline -1; git tag -n1; python3 "$ATHOS_BIN" list
