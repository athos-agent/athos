# Your know-how as a wiki

Athos keeps your know-how in `~/.athos/know-how/`: one markdown page per piece, plus an `Index.md` it rebuilds on
every save. Open the folder in any editor; in [Obsidian](https://obsidian.md) it is a wiki with a graph and backlinks,
because the links are plain `[[page]]` and `[[page#statement]]`.

## A page

A page is a list of **statements**, the smallest unit you can check:

```markdown
## #run_guard
**When:** about to commit or push to the public repo.
**Do:** run `python3 tools/guard.py .` and stop on any finding.
**Because:** a private name reached a public PR once.
**Links:** [[land-a-change#open_pr]] · [[bump-the-plugin-version#bump]]
```

- **When** is the moment the step applies, as you would recognise it in the middle of a task, not a topic.
- **Do** is the action, concrete enough to check: a command, a file, a question to ask you, a refusal.
- **Because** is the reason or the evidence (an incident, a measurement, your decision), so a statement can be checked
  and, one day, retired.
- **Links** name what applies **next or alongside**.

## Links are trajectories

The one rule for links: a statement links to the statement that was applied **right after it, or together with it,
in a real task**. Two pages about the same subject are not linked for that reason alone. So following links is the
same as doing the task: a walk starts at the page the Index points to for the situation, takes its first statement,
and follows links while their **When** applies.

Links are written when a piece is saved, from the task that just ran: the pieces loaded in that session are the ones
whose statements were applied, so the new statements link to them in the order they were used. A link nobody follows
again is a candidate to drop when the page is next improved.

## The wiki improves with use

- Every save is a new version of a page (the old one is kept in `.history/`), written from the task that just ran.
- Every save rebuilds `Index.md` and checks the links. A link that leads nowhere is reported back in the same turn,
  so the agent fixes it right away.
- Pages written before this format (numbered steps) still load and walk as one block. `athos wiki` lists them, and
  each one is rewritten as statements the next time a task improves it.

```
athos wiki                  rebuild Index.md; pages, statements, links; what to fix
athos wiki --json           the same, as JSON
```

## Trajectory agents

A walk that crosses pages (a release that runs the guard, then bumps the version, then opens the PR) is a
**trajectory**. Athos writes each trajectory as a subagent in markdown, `athos-<page>.md`, in `~/.athos/agents/`:
the statements of every page on the walk, in order, with instructions to follow them while they apply, cite each one
it follows and leave your decisions to you.

The agents are not written by hand and never drift: whenever a page on a trajectory improves, its agent is rebuilt
from the new version (its header says which versions it came from); when a trajectory disappears, so does its agent.

```
athos wiki agents                  list them
athos wiki agents --install        put them in ~/.claude/agents for Claude Code, and keep them in step on every save
athos wiki agents --uninstall      remove them from there
```
