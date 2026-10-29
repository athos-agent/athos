# The lawyer take: a lawyer reviews a lease in Claude Code from their own checklist file, and Athos keeps it as a way
# of working; then OpenCode, on Meta's Muse Spark, reviews a services agreement from a one-line request and says which
# of the lawyer's ways of working it follows. athos watch fills one bar per agent. Waits are hidden, not sped up.
#
#   sh demo/lawyer-setup.sh en && vhs demo/lawyer-en.tape
#
# Everything runs in /Users/Shared/athos-demo-law (no user name on screen) with its own Athos home. The Meta key is read
# from ~/.athos/.env into the hidden shell and never printed. Every take is checked before it is kept: the store must
# show the improved piece and two tasks, one per agent.
Output "demo/lawyer-en.gif"
Set Shell "zsh"
Set FontSize 14
Set Width 1900
Set Height 900
Set TypingSpeed 18ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type "cd /Users/Shared/athos-demo-law/office && export ATHOS_HOME=/Users/Shared/athos-demo-law/home ATHOS_BIN=$HOME/athos/athos/bin/athos CLAUDE_CODE_AUTO_CONNECT_IDE=false && export PATH=$HOME/athos/athos/bin:$PATH && clear" Enter
Sleep 1s
Type `export MODEL_API_KEY="$(sed -n 's/^MODEL_API_KEY=//p' ~/.athos/.env)" && clear` Enter
Sleep 1s
Type `tmux new-session -s law \; set -g status off \; split-window -h -l 74 "athos watch" \; select-pane -L` Enter
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

Type "Review lease.md against my checklist (my-checklist.md). I act for the tenant; the data is fictitious."
Sleep 1s
Enter
Sleep 3s
Hide
Wait+Screen@240s /(improved|saved) «/
Sleep 3s
Show
Sleep 6s
Hide
Ctrl+B
Type "o"
Sleep 1s
Type "g"
Sleep 2s
Ctrl+B
Type "o"
Sleep 1s
Type "/exit" Enter
Sleep 4s
Type "clear" Enter
Sleep 1s
Show
Type "opencode"
Enter
Hide
Wait+Screen@60s /Ask anything/
Sleep 8s
Show
Type "Review services-agreement.md, I act for the provider."
Sleep 1s
Enter
Sleep 3s
Hide
Wait+Screen@240s /▣ +Build · Muse Spark/
Sleep 3s
Show
Sleep 8s
Hide
Ctrl+B
Type "o"
Sleep 1s
Type "g"
Sleep 3s
Show
Sleep 6s
Hide
Ctrl+B
Type "o"
Sleep 1s
Ctrl+C
Sleep 1s
Type "tmux kill-session -t law" Enter
Sleep 1s
