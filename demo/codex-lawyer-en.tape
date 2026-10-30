# Codex follows a lawyer's own contract checklist, and Athos shows the method beside it: on the left Codex reviews a
# lease from a one-line request; on the right `athos watch --trail` says which way of working it follows and ticks
# its steps as Codex reports them. Waits are hidden, not sped up.
#
#   sh demo/lawyer-setup.sh en && vhs demo/codex-lawyer-en.tape
#
# Runs in /Users/Shared/athos-demo-law/office (fictional lease, no user name on screen). Codex passes no ATHOS_HOME to
# its hooks, so this take uses the person's own store: it must hold the English law starters (athos start --lang en
# --profile law), and the take's events are removed from it afterwards.
Output "demo/codex-lawyer-en.gif"
Set Shell "zsh"
Set FontSize 13
Set Width 1900
Set Height 980
Set TypingSpeed 22ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type "cd /Users/Shared/athos-demo-law/office && export PATH=$HOME/athos/athos/bin:$PATH && clear" Enter
Sleep 1s
Type `tmux new-session -s law \; set -g status off \; split-window -h -l 64 "athos watch --trail" \; select-pane -L` Enter
Sleep 3s
Type "PROMPT='%1~ %# ' && clear && codex" Enter
Wait+Screen@60s /Ask Codex to do anything/
Sleep 2s
Show

Sleep 1s
Type "Review lease.md for my client, the tenant. The data is fictitious."
Sleep 1s
Enter
Sleep 28s
Hide
Wait+Screen@240s /Worked for/
Sleep 2s
Show
Sleep 8s
Hide
Type "/quit" Enter
Sleep 1s
