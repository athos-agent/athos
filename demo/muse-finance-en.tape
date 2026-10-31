# Muse Code, on Meta's Muse Spark, analyses an investment with an advisor's own committee rules, and Athos shows the
# method beside it. One step hands over to another way of working only when the case needs it (**If:** the investor,
# the asset and the vehicle are in different countries → the cross-border tax check): its steps appear nested under it
# (↳) in `athos watch --trail` and tick in order. Waits are hidden, not sped up.
#
#   vhs demo/muse-finance-en.tape
#
# Runs in /Users/Shared/athos-demo-finance/desk (a fictional prospectus). Muse passes no ATHOS_HOME to its hooks, so
# this take uses the person's own store: it must hold the English finance starters (athos start --lang en --profile
# finance); the take's events are removed afterwards.
Output "demo/muse-finance-en.gif"
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
Type `tmux new-session -s musefin \; set -g status off \; split-window -h -l 64 "GIT_CONFIG_GLOBAL=/dev/null athos watch --trail" \; select-pane -L` Enter
Sleep 3s
Type "PROMPT='%1~ %# ' && clear && muse --model muse-spark-1.3 --trust-workspace --contributor-mode off --workspace /Users/Shared/athos-demo-finance/desk" Enter
Wait+Screen@90s /Auto-review/
Sleep 2s
Show

Sleep 1s
Type "Analyse this investment for my client. The prospectus is in prospectus.md; it's fictional, no client details."
Sleep 1s
Enter
Sleep 35s
Hide
Wait+Screen@290s /steps applied/
Sleep 3s
Show
Sleep 10s
Hide
Ctrl+C
Sleep 1s
Type "tmux kill-session -t musefin" Enter
Sleep 1s
