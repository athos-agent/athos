---
description: Choose which know-how may load — auto (this project's, the default), all, project [name], pieces <id>..., or none
argument-hint: auto | all | project [name] | pieces <id>... | none
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" load $ARGUMENTS`

Tell the user in one line what will load from now on.
