# The delegation take: the release Athos's piece describes, run live on Meta Model API (muse-spark-1.3) in Athos's own
# loop, then the report with Claude Code and a local model beside it on the same task.
#
#   sh demo/setup.sh && sh demo/prep.sh && sh demo/bench.sh && vhs demo/delegate.tape
#
# The Meta run is marked by what git and the tests say, as bench.sh marks the other two. The prompt shows only the folder.
Output "demo/delegate.gif"
Set Shell "zsh"
Set FontSize 15
Set Width 1600
Set Height 860
Set TypingSpeed 20ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type "cd ~/athos-demo/greet-meta && export ATHOS_HOME=~/athos-demo/home && . .venv/bin/activate && PROMPT='%1~ %# '" Enter
Type `AB=$(ls -d ~/.claude/plugins/cache/athos/athos/*/bin/athos | sort -V | tail -1); athos() { python3 "$AB" "$@"; }` Enter
Type `PIECE=$(basename "$(ls $ATHOS_HOME/know-how/*.md | head -1)" .md)` Enter
Type `BEFORE=$(cd ../greet && .venv/bin/python -m pytest -q 2>/dev/null | sed -n 's/^\([0-9]*\) passed.*/\1/p' | tail -1)` Enter
Type `verdict() { git tag -l v0.3.0 | grep -q . && python -m pytest -q > /dev/null 2>&1 || { echo f; return; }; now=$(python -m pytest -q 2>/dev/null | sed -n 's/^\([0-9]*\) passed.*/\1/p' | tail -1); [ "${now:-0}" -gt "$BEFORE" ] && echo g || echo c; }` Enter
Type "clear" Enter
Sleep 1s
Show

Type `athos delegate $PIECE "Release 0.3.0 with a new name_upper option for greet() that uppercases the name." --backend meta --yes`
Sleep 1s
Enter
Sleep 3s
Hide
Wait+Screen /meta \/ muse-spark-1\.3: /
Show
Sleep 5s

Hide
Type "athos mark $(verdict) > /dev/null; clear" Enter
Sleep 10s
Show
Type "athos report"
Sleep 1s
Enter
Wait+Screen@120s /Models on your tasks/
Sleep 8s
