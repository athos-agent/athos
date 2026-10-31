# Athos's memory, per project: each project's recent past (the journal), curating as the know-how grows, and each
# project loading only its own ways of working. Three fictional projects (an SRE team, a newsroom, a law firm) with
# pages taken from the gallery; a throwaway store, never the person's own.
#
#   DEMO_HOME=<a store prepared like the one in this take> vhs demo/memory-en.tape
Output "demo/memory-en.gif"
Set Shell "zsh"
Set FontSize 15
Set Width 1600
Set Height 900
Set TypingSpeed 35ms
Set Theme "Builtin Dark"

Hide
Type `export ATHOS_HOME=$DEMO_HOME PATH=$HOME/athos/athos/bin:$PATH GIT_CONFIG_GLOBAL=/dev/null PROMPT='%1~ %# ' && cd /Users/Shared/acme-ops && clear` Enter
Sleep 1s
Show

Type "athos journal"
Sleep 500ms
Enter
Sleep 5s
Type "athos curate"
Sleep 500ms
Enter
Sleep 9s
Type "athos curate apply 1 2 3 4 5"
Sleep 500ms
Enter
Sleep 4s
Type "clear && cd ../newsroom && athos list | grep -E '^[●○]'"
Sleep 500ms
Enter
Sleep 7s
