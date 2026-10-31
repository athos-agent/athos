# Codex analyses an investment with an advisor's own committee rules, and Athos shows the method beside it: one step
# hands over to another way of working only when the case needs it (**If:** the investor, the asset and the vehicle are
# in different countries → the cross-border tax check), and the trail shows those steps nested under it (↳).
# On the right `athos watch --trail` ticks the steps as Codex reports them. Waits are hidden, not sped up.
#
#   vhs demo/codex-finance-en.tape
#
# Runs in /Users/Shared/athos-demo-finance/desk (a fictional prospectus). Codex's hooks use the person's own store: it
# must hold the English finance starters (athos start --lang en --profile finance); the take's events are removed
# afterwards.
Output "demo/codex-finance-en.gif"
Set Shell "zsh"
Set FontSize 13
Set Width 1900
Set Height 980
Set TypingSpeed 22ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type "cd /Users/Shared/athos-demo-finance/desk && export PATH=$HOME/athos/athos/bin:$PATH && clear" Enter
Sleep 1s
Type `tmux new-session -s fin \; set -g status off \; split-window -h -l 64 "GIT_CONFIG_GLOBAL=/dev/null athos watch --trail" \; select-pane -L` Enter
Sleep 3s
Type "PROMPT='%1~ %# ' && clear && codex" Enter
Wait+Screen@60s /Trust this folder|Ask Codex to do anything/
Sleep 2s
Enter
Wait+Screen@60s /Ask Codex to do anything/
Sleep 2s
Show

Sleep 1s
Type "Analyse this investment for my client. The prospectus is in prospectus.md; it's fictional, no client details."
Sleep 1s
Enter
Sleep 30s
Hide
Wait+Screen@280s /Worked for/
Sleep 2s
Show
Sleep 10s
Hide
Type "/quit" Enter
Sleep 1s
Type "tmux kill-session -t fin" Enter
Sleep 1s
