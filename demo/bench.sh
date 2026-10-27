#!/bin/sh
# Off camera, after setup.sh and prep.sh, before demo/delegate.tape: the same release in Claude Code and on a local model,
# each in its own copy of the package, so the report can put them beside the Meta run the tape shows. Real runs: about
# a minute and a half. Each one is marked by what git and the tests say, never by hand.
set -eu
DEMO="${ATHOS_DEMO:-$HOME/athos-demo}"
export ATHOS_HOME="$DEMO/home" ATHOS_CAPTURE=off CLAUDE_CODE_AUTO_CONNECT_IDE=false
AB=$(ls -d "$HOME"/.claude/plugins/cache/athos/athos/*/bin/athos 2>/dev/null | sort -V | tail -1)
PIECE=$(basename "$(ls "$ATHOS_HOME"/know-how/*.md | head -1)" .md)
REQUEST="Release 0.3.0 with a new name_upper option for greet() that uppercases the name."

for v in claude meta local; do
  rm -rf "$DEMO/greet-$v"
  cp -R "$DEMO/greet" "$DEMO/greet-$v"
done

# What git and the tests say: failed without the tag or with failing tests; corrected when the piece's own rule "add a
# test for any new option" was skipped (no more tests than before); good otherwise.
verdict() {
  git tag -l v0.3.0 | grep -q . && .venv/bin/python -m pytest -q > /dev/null 2>&1 || { echo f; return; }
  now=$(.venv/bin/python -m pytest -q 2>/dev/null | sed -n 's/^\([0-9]*\) passed.*/\1/p' | tail -1)
  [ "${now:-0}" -gt "$BEFORE" ] && echo g || echo c
}
BEFORE=$(cd "$DEMO/greet" && .venv/bin/python -m pytest -q 2>/dev/null | sed -n 's/^\([0-9]*\) passed.*/\1/p' | tail -1)

cd "$DEMO/greet-claude"
claude -p "$REQUEST" --permission-mode acceptEdits --allowedTools "Bash Read Edit Write" > /dev/null
python3 "$AB" mark "$(verdict)"

cd "$DEMO/greet-local"
PATH="$DEMO/greet-local/.venv/bin:$PATH" python3 "$AB" delegate "$PIECE" "$REQUEST" --model "${LOCAL_MODEL:-gemma4:12b-mlx}" \
  --yes > /dev/null
python3 "$AB" mark "$(verdict)"

echo "Bench ready. Piece: $PIECE"
