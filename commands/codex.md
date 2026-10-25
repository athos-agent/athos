---
description: Take your know-how to Codex — its skills, plus hooks that record Codex tasks in your report
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" export --codex && python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" codex install`

Tell the user, in a few lines, what was set up above, and that Codex asks once to trust new hooks (`/hooks` inside
Codex). Codex's tasks reach `/athos:report` either way.
