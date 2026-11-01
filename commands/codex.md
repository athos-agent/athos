---
description: Bring your know-how to Codex: your pieces as Codex skills, and hooks so Codex's tasks show up in your report
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" export --codex && python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" codex install`

In a few lines, tell the user what the commands above set up. Mention that Codex asks once before it trusts new hooks
(they can review them with `/hooks` in Codex), and that Codex's tasks are counted in `/athos:report` in any case.
