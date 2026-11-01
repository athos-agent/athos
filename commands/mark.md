---
description: Give the last task its verdict: g if it went well, c if you had to correct it, f if it failed
argument-hint: g (good) | c (corrected) | f (failed)
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" mark $ARGUMENTS`

Confirm the verdict to the user in a single line, and take no other action.
