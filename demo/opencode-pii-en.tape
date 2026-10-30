# OpenCode on Muse Spark reviews a lease through pii-guard, with Athos's trail in OpenCode's own sidebar: it says which
# way of working it follows, that the personal data goes through pii-guard, and ticks the checklist's steps. Then the
# person changes a step from the command palette (ctrl+p → "Athos: change this step"), with no command to type.
# Waits are hidden, not sped up.
#
#   pii-guard running on 127.0.0.1:8787 (its README; `athos connector add pii-guard`), then
#   DEMO_HOME=<store with the English law starters and the pii-guard connector> \
#   DEMO_XDG=<an OpenCode config folder with Athos installed> vhs demo/opencode-pii-en.tape
#
# OPENCODE_DISABLE_CLAUDE_CODE_SKILLS keeps the skills Claude Desktop synced to ~/.claude/skills out of the take.
# Runs in /Users/Shared/athos-demo-law/clients, whose opencode.json has a `pii-guard` provider (baseURL
# http://127.0.0.1:8787/v1, model muse-spark-1.3). The lease and its people are fictional.
Output "demo/opencode-pii-en.gif"
Set Shell "zsh"
Set FontSize 13
Set Width 1900
Set Height 1000
Set TypingSpeed 4ms
Set Theme "Builtin Dark"
Set WaitTimeout 300s

Hide
Type `export OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1 ATHOS_HOME=$DEMO_HOME XDG_CONFIG_HOME=$DEMO_XDG ATHOS_BIN=$HOME/athos/athos/bin/athos PROMPT='%1~ %# ' && cd /Users/Shared/athos-demo-law/clients && clear && opencode` Enter
Wait+Screen@60s /Ask anything/
Sleep 2s
Show

Sleep 1s
Type "Review this lease before my client signs it. We act for the tenant. (Fictional data.)  LEASE AGREEMENT 1. Parties: Example Realty Inc., represented by Jane Placeholder (jane.placeholder@example.net, +1 555 0142), landlord; and John Sample, born 12 March 1988, of 45 Fictional Avenue, Springfield, tenant (john.sample@example.org). 2. Premises: apartment 4B at 123 Made-Up Street, Springfield, for residential use. 3. Term: 3 years from December 1, 2026. 4. Rent: $2,500 per month, paid to account GB33BUKB20201555555555, adjusted every 3 months by an index the landlord chooses. 5. Deposit: two months' rent, returned "
Type `"at the landlord's discretion". 6. Termination: the tenant may not terminate before 2 years; if they do, they pay 6 months' rent. 7. Repairs: all repairs, structural ones included, are the tenant's responsibility. 8. Renewal: the lease renews automatically for 3 years unless notice is given 6 months in advance. 9. Disputes: go to the courts the landlord chooses.`
Sleep 1s
Enter
Sleep 15s
Hide
Wait+Screen@240s /through pii-guard\) · [0-9.]+s/
Sleep 2s
Show
Sleep 8s

Ctrl+P
Sleep 1s
Type "athos"
Sleep 2s
Type ": change"
Sleep 1s
Enter
Wait+Screen@10s /How should this step change/
Sleep 1s
Type "add a column with the legal basis for each issue"
Sleep 1s
Enter
Sleep 12s
Hide
# The change is saved and the table comes back in about 40 s; its last line may have scrolled out of reach of a Wait.
Sleep 75s
Show
Sleep 8s
Hide
Ctrl+C
Sleep 1s
