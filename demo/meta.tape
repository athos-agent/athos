# Every take is checked before it is kept: the marks the tape presses must match `git log` and `git tag -n1`.
# The Muse Code take: Claude Code learns a release once, Muse Code does the next one in the same folder with a
# one-line request, and athos watch fills both bars. Waits are hidden, not sped up: every number is the real one.
#
#   sh demo/setup.sh && sh demo/prep.sh && vhs demo/meta.tape
#
# Muse Code runs with its API key (`muse auth set --api-key-stdin`) on muse-spark-1.3, never the -contributor model.
# The recording shell shows only the folder in its prompt, turns off Athos's capture (done in prep.sh) and Claude Code's IDE link, and tmux hides its status
# bar, so no local user, host or editor selection shows up.
Output "demo/meta.gif"
Set Shell "zsh"
Set FontSize 14
Set Width 1900
Set Height 860
Set TypingSpeed 20ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type "cd ~/athos-demo/greet && export ATHOS_HOME=~/athos-demo/home && . .venv/bin/activate && export ATHOS_CAPTURE=off CLAUDE_CODE_AUTO_CONNECT_IDE=false && clear" Enter
Sleep 1s
Type `tmux new-session -s meta \; set -g status off \; split-window -h -l 74 "python3 ~/.athos/bin/athos watch" \; select-pane -L` Enter
Sleep 3s
Type "PROMPT='%1~ %# ' && clear" Enter
Sleep 1s
Type "claude --permission-mode acceptEdits --allowedTools 'Bash Read Edit Write'" Enter
Wait+Screen@60s /Yes, I trust this folder|accept edits on/
Sleep 1s
Down
Sleep 1s
Enter
Wait+Screen@60s /accept edits on/
Sleep 3s
Show

Type "Release 0.3.0 with a new name_upper option for greet() that uppercases the name."
Sleep 1s
Enter
Sleep 2s
Hide
Wait+Screen /v0\.3\.0/
Sleep 40s
Ctrl+B
Type "o"
Sleep 1s
Type "g"
Sleep 3s
Ctrl+B
Type "o"
Sleep 4s
Show
Sleep 5s

Hide
Type "/exit" Enter
Sleep 4s
Type "clear" Enter
Sleep 1s
Type `alias muse="muse --model muse-spark-1.3 --trust-workspace --disable-approval" && clear` Enter
Sleep 1s
Show
Type "muse"
Enter
Hide
Wait+Screen@60s /muse-spark-1\.3 ·/
Sleep 2s
Show
Type "Release 0.4.0 with a new name_lower option for greet() that lowercases the name."
Sleep 1s
Enter
Sleep 2s
Hide
Wait+Screen /annotated tag v0\.4\.0|tagged locally|Released 0\.4\.0/
Sleep 6s
Show
Sleep 4s
Hide
Type "/exit"
Enter
Sleep 6s
Ctrl+B
Type "o"
Sleep 8s
Type "g"
Sleep 3s
Show
Sleep 6s
Hide
Ctrl+B
Type "o"
Sleep 1s
Type "tmux kill-session -t meta" Enter
Sleep 1s
