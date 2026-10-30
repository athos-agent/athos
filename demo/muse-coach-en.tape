# Muse Code, on Meta's Muse Spark, plans an athlete's week following a coach's own rules, and Athos shows the method
# beside it: on the left Muse Code works from a plain request; on the right `athos watch --trail` says which way of
# working it follows and ticks its steps as Muse reports them. Waits are hidden, not sped up.
#
#   sh demo/lawyer-setup.sh en && vhs demo/muse-coach-en.tape
#
# Runs in /Users/Shared/athos-demo-law/office (fictional athlete). Muse passes no ATHOS_HOME to its hooks, so this
# take uses the person's own store (it must hold the English sports starters: athos start --lang en --profile sports);
# the take's events are removed from it afterwards.
Output "demo/muse-coach-en.gif"
Set Shell "zsh"
Set FontSize 13
Set Width 1900
Set Height 980
Set TypingSpeed 18ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type "cd /Users/Shared/athos-demo-law/office && export PATH=$HOME/athos/athos/bin:$PATH && clear" Enter
Sleep 1s
Type `tmux new-session -s coach \; set -g status off \; split-window -h -l 64 "GIT_CONFIG_GLOBAL=/dev/null athos watch --trail" \; select-pane -L` Enter
Sleep 3s
Type "PROMPT='%1~ %# ' && clear && muse --model muse-spark-1.3 --trust-workspace --contributor-mode off --workspace /Users/Shared/athos-demo-law/office" Enter
Wait+Screen@90s /Auto-review/
Sleep 2s
Show

Sleep 1s
Type "Plan next week's training for Lucy. She runs 4 days a week, never on Wednesdays or Sundays. Last 4 weeks (minutes x effort 1-10): W1 Mon 40x5, Tue 30x7, Thu 45x4, Sat 70x6; W2 Mon 40x5, Tue 35x7, Thu 45x4, Sat 75x6; W3 Mon 45x5, Tue 35x8, Thu 50x4, Sat 80x6; W4 Mon 45x6, Tue 40x8, Thu 50x5, Sat 95x7. She wants to run a 10K in three weeks."
Sleep 1s
Enter
Sleep 30s
Hide
Wait+Screen@280s /steps applied/
Sleep 3s
Show
Sleep 8s
Hide
Ctrl+C
Sleep 1s
