---
description: Copy your whole Athos know-how store into a folder of your choice
argument-hint: <destination folder>
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" export $ARGUMENTS`

In one line, tell the user which folder now holds the copy of their store.
