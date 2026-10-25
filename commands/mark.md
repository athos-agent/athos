---
description: Mark how the last task went — g (good), c (needed corrections) or f (failed)
argument-hint: g | c | f
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" mark $ARGUMENTS`

Confirm the mark to the user in one line. Do nothing else.
