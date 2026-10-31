# OpenCode on Muse Spark analyses an investment with an advisor's own committee rules, with Athos's trail in OpenCode's
# sidebar. One step hands over to another way of working only when the case needs it (**If:** the investor, the asset
# and the vehicle are in different countries → the cross-border tax check): its steps appear nested under it (↳) and
# tick in order, then the walk comes back to the numbers. Waits are hidden, not sped up.
#
#   DEMO_HOME=<store with the English finance starters> DEMO_XDG=<an OpenCode config folder with Athos installed> \
#   MODEL_API_KEY=<Meta Model API key> vhs demo/opencode-finance-en.tape
#
# Runs in /Users/Shared/athos-demo-finance/oc, whose opencode.json has a `meta` provider (model muse-spark-1.3). The
# prospectus is fictional.
Output "demo/opencode-finance-en.gif"
Set Shell "zsh"
Set FontSize 13
Set Width 1900
Set Height 1000
Set TypingSpeed 18ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type `export OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1 ATHOS_HOME=$DEMO_HOME XDG_CONFIG_HOME=$DEMO_XDG XDG_DATA_HOME=$DEMO_XDG/data PROMPT='%1~ %# ' && cd /Users/Shared/athos-demo-finance/oc && clear && opencode` Enter
Wait+Screen@60s /Ask anything/
Sleep 2s
Show

Sleep 1s
Type "Analyse this investment for my client. The prospectus is in prospectus.md; it's fictional, no client details."
Sleep 1s
Enter
Sleep 40s
Hide
Wait+Screen@280s /Muse Spark 1.3 · [0-9]/
Sleep 3s
Show
Sleep 10s
Hide
Ctrl+C
Sleep 1s
