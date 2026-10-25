---
description: Export your whole Athos know-how store to a folder
argument-hint: <folder>
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" export $ARGUMENTS`

Tell the user in one line where the store was exported.
