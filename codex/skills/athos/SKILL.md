---
name: athos
description: "Athos, the user's own know-how store. Use when the user asks about their know-how or Athos: what pieces they have, show one, mark how the last task went (good, corrected, failed), see the report or the bars per agent, or take a piece they built in Claude Code into this task."
---

The user's know-how lives in `~/.athos/know-how/`, one markdown file per piece, shared by Claude Code and Codex.
Run the `athos` command from the plugin (`python3 <plugin root>/bin/athos`, or `athos` if it is on the PATH):

- `athos list` lists the pieces; `athos show <id>` prints one. When a piece's "when" matches the task, follow it.
- `athos mark g|c|f` marks the last task in this project as good, corrected or failed. Only the user decides the
  mark: ask them, never mark on your own.
- `athos report` shows each piece's uses and success, and each agent and model on the user's own tasks.
- `athos watch` is a live panel (in a terminal beside Codex) with one bar per agent for this project's know-how.
- `athos export --codex .agents/skills` writes every piece as a Codex skill in this project.

Nothing leaves the machine: Athos keeps everything local.
