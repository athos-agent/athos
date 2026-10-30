# Athos

Your AI know-how. Free to move, fast to run.

**Ask as you always do. Claude follows *your* way of working, and you watch it, step by step.**

![Claude Desktop (not the Code tab). A coach asked for next week's training plan for an athlete, without mentioning Athos. Athos's panel says how Claude is going about it in plain sentences, then shows the coach's own way of working as a page, with its steps ticked as they are done.](demo/athos-desktop-en.png)

*Claude Desktop, not the Code tab (fictional data; [en español](demo/athos-desktop-es.png)). A coach pastes an
athlete's last four weeks and asks for next week's plan, with no word about Athos. Claude picks up the coach's own way of working, "Plan the training week
with my rules". Athos's panel says how it is going about it, in plain sentences, then shows that way of working as a
page: what it is for, and its steps as a task list, ticked as Claude does them, each opening to when, what and why.
The answer is just the plan, with the coach's rules, and the decisions left to the coach.*

- **Your way, not a generic one.** Ask a lawyer's "review this lease" and the answer comes back with *their*
  five-line summary and *their* table: clause, problem, proposed wording, priority. Without it, the same request got
  a good, generic review.
- **You see the method, like a model's thinking.** Not tool calls: sentences, a page and a task list. **Change this
  step** improves your way of working on the spot; a task that needed new steps offers **Save as a way of working**.
- **It stays yours.** Plain markdown files in `~/.athos`, on your computer, that you can read and edit. The same know-how
  runs in Claude Code, Codex, Meta's Muse Code and OpenCode.

**In Claude Desktop:** `athos desktop` builds two files: double-click `athos.mcpb`, and upload `athos-skill.zip` in
Customize → Skills. [Step by step](docs/guides/claude-desktop-en.md) ([en español](docs/guides/claude-desktop.md)).

Every day you teach AI agents how you do things: your checklist, your steps, your format, the mistakes to avoid. Not
only in code: coding agents now do everyday work in any field, and a lawyer reviewing a contract or a coach planning a
week teaches them just as much. That know-how gets stuck in one chat of one tool. Athos keeps it as plain files on your
machine and carries it to every agent you use, **Claude Code, Codex, Meta's Muse Code and OpenCode**, so you never
explain it twice. On your own tasks, it shows what each agent and model does with it.

**Guides:** [Claude Desktop](docs/guides/claude-desktop-en.md) ([en español](docs/guides/claude-desktop.md)) · [for lawyers](docs/guides/lawyer.md) ([en español](docs/guides/abogado.md)) ·
[for coaches](docs/guides/coach.md) ([en español](docs/guides/entrenador.md)) ·
[your checklist is know-how](docs/guides/checklist-en.md) ([en español](docs/guides/checklist.md)) · why this should
exist and what isn't solved: [WHY.md](WHY.md).

## Your know-how moves, and it works where it lands

Teach a task once, in any of these tools, and the others follow it:

| Agent | How Athos plugs in | What we checked |
|---|---|---|
| **Claude Code** (and Claude Desktop's Code tab) | plugin | 21 of 21 bench runs good with the know-how |
| **Codex** | plugin | 20 of 20 bench runs good with the know-how |
| **Muse Code** (Meta) | the same plugin as Claude Code | a lawyer's contract review followed step by step; tokens from Muse's own log |
| **OpenCode** (any model) | plugin | the same review with Meta's Muse Spark; Athos asked, and Muse improved the piece |

In all four, the pieces that match a request are loaded and the agent opens by saying which of your ways of working it
follows and how it applies; every task is recorded with the model that answered; and after real work, or a task that
followed a checklist, Athos offers to save or improve a piece. A piece written in OpenCode loads in Claude Code the
next day.

In Claude Code, the band above the prompt says it in one place: which of your ways of working the task used, how it
has done so far and which words loaded it, with **Didn't apply** when it didn't fit (those words won't load it again);
**Save** when the task is worth keeping, so the AI is not asked after every task; and **Good / Corrected / Failed**.
Plain words count too: "ok excelente, …" marks the last task good. Only the last week's tasks wait for a mark.

**It starts to pay off on a cheaper model.** On five public bench tasks in five domains (code, data, devices, a
planning method, sports coaching), Meta's Muse Spark did 22 of 23 runs right with the know-how and 2 of 23 without it,
at 8 to 24 times less per run than Claude Code where we compared. Small cases written for the bench, 3 to 5 runs each;
reproduce with `athos bench all --without`.

## For professionals, not only programmers

`athos start` asks your language (English or Spanish) and your profession, and adds example ways of working to start
from: **law** (build the argument of a brief, review a contract against your checklist) and **sports coaching** (plan
the training week, write the post-match report). They leave every professional decision to you and ask before
touching client or athlete data. No terminal needed: Claude Desktop's Code tab runs the plugin. Start with the
[overview for professionals](docs/PROFESSIONALS.md) ([en español](docs/PROFESIONALES.md)) or the guides above.

**Checklists are know-how.** When a task follows a checklist (you name it, paste it as a list, or the agent opens a
checklist file), Athos treats it as know-how worth keeping, even if the task only read and answered, and asks to save
it, or to improve the piece it used with your own items. [How it works](docs/guides/checklist-en.md).

## What else it does

- **Captures and improves your know-how.** Each piece is a plain markdown page you can read and edit, with a version
  history. Only the pieces that match a request are loaded, and each reuse can improve them.
- **Yours, and free to move.** Plain files in `~/.athos` that you can read, edit, version and copy. Nothing leaves
  your machine unless you move it.
- **Your own benchmark.** Benchmarks measure someone else's tests; Athos measures yours. Mark each task with one key,
  and `/athos:report` shows what every piece of know-how and every model brings to your own work.
- **Hands mastered tasks to cheaper models.** Once a piece has proven itself, `athos delegate` runs the task on a
  smaller model, local or hosted, and `athos bench` shows whether it keeps up.

## Install

In **Claude Code** (or Claude Desktop's Code tab):

```
/plugin install athos --marketplace athos-agent/athos
```

In **Codex**:

```
codex plugin marketplace add athos-agent/athos
codex plugin add athos@athos
```

In **Muse Code**:

```
muse plugins marketplace add athos https://github.com/athos-agent/athos
muse plugins install athos@athos
muse plugins approve athos
```

In **OpenCode**, with the `athos` command from the installer:

```
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos opencode install       then restart OpenCode
```

Then `athos start` asks your language and profession and adds example ways of working (law and sports coaching today).

Requires Python 3.11+ (the installer picks the newest one you have). No other dependencies. Your know-how lives in
`~/.athos/know-how`, the same for every agent.

## Use

Athos works on its own: it loads matching know-how with each request and, after real work, offers to save what the
task taught. These are the commands you will reach for:

```
/athos:list          see your know-how and what is enabled
/athos:mark g        mark the last task: g good, c needed corrections, f failed
/athos:report        what each piece and each model brings to your work
/athos:codex         take your know-how to Codex
```

When a piece has proven itself, hand the task to a smaller, cheaper model: on your own machine through
[Ollama](https://ollama.com), or on Meta's models through Meta Model API (`--backend meta`, key in `MODEL_API_KEY` or
`~/.athos/.env`):

```
athos delegate <piece> "<request>"           runs in the current folder; asks before every command and write
athos delegate <piece> "<request>" --model qwen3.5:9b
athos delegate <piece> "<request>" --backend meta       muse-spark-1.3; --model muse-wonder-1.0 for the largest
```

The model follows the piece with four tools (run a command, read, edit and write a file), confined to the current
folder. The task lands in `/athos:report` as `local / <model>`, beside Claude Code and Codex, and you mark it like any
other. Nothing is delegated unless you run `athos delegate`. The default is `gemma4:12b`; in our tests a 4B model was
not enough for a release task, and the 12B one did it in about a minute and a half but still needed a correction.
`--yes` runs the model's commands without asking: use it only in a folder you can throw away.

To see what the know-how is worth before trusting a cheaper model with it, `athos bench` runs the same task several
times on each agent and model, with and without the know-how, and checks what each run left behind (git, the tests,
the files) instead of taking the agent's word:

```
athos bench --list                                         the cases: code, data, devices, a planning method, sports, law, literature
athos bench all --agents claude,meta,local --runs 5 --without --max-usd 5
athos bench report                                         success, time, tokens and cost per agent; the cheapest that keeps up
```

`athos bench transfer` asks whether what you taught one agent carries to the others, whole. Claude Code first works a
task the way a person teaches it (their checklist, their corrections, "save it"); then a fresh folder with another
document and no checklist gets a one-line request in Claude Code, Codex, Muse Code and OpenCode, with no Athos, with
only the project's `.athos/` folder, and with the folder plus the plugin. Each point of the person's know-how is
checked on its own, and the rules they added while teaching, which exist nowhere else, show what really travelled:

```
athos bench transfer contract-transfer --agents claude,codex,muse,opencode --arms A,B,C --runs 3 --max-usd 10
athos bench transfer chapter-transfer  --agents claude,codex,muse,opencode   an author's editing rules, the same way
athos bench transfer-report contract-transfer             per agent and arm: points applied, taught rules, time, cost
```

Each run gets a throwaway folder and its own Athos home, so your store and your recorded tasks stay untouched. Your own cases
(a folder with `case.json`, `piece.md`, `setup.py` and `check.py`, like the ones in `athos/bench/cases/`) go in
`~/.athos/bench/cases/` and never leave your machine.

Your know-how lives in `~/.athos/know-how/`, one markdown page per piece, as a wiki: each step is a statement
(when / do / because / links), the links follow the order things are done in a task, and `Index.md` says where each
kind of task starts. Walks that cross pages become subagents that improve with the pages. See [docs/WIKI.md](docs/WIKI.md). Choose what may load with
`/athos:load all | project <name> | pieces <id>... | none`, and copy everything out with `/athos:export <folder>`.

### In Codex

Athos is also a Codex plugin, reading the same store:

```
codex plugin marketplace add athos-agent/athos
codex plugin add athos@athos
```

The plugin brings the `athos` skill. In the Codex desktop app it also brings Athos's hooks; in the Codex CLI add them
once with `athos codex install` (Codex asks you to trust them with `/hooks`). Codex's footer takes no custom lines, so
run `athos watch` in a terminal beside it: one bar per agent for this project's know-how, the same bars Claude Code
shows under its prompt, marked with g / c / f.

### In Muse Code

Muse Code runs the same plugin as Claude Code: the pieces that match each request are loaded, every task is recorded
with the model that answered and its tokens (from Muse's own session log), and after a turn that changed something or
followed a checklist Athos asks once whether to save or improve a piece. `athos watch` and `/athos:report` show Muse Code beside Claude
Code and Codex. Keep Muse Code's Contributor mode off (`muse` → `/settings`) unless you want Meta to train on your
sessions; Athos warns when a task ran with it.

Without the plugin, `athos export --muse` writes your pieces as skills in `~/.agents/skills` and `athos import muse`
records past tasks from Muse's session logs.

### In OpenCode

Athos is an OpenCode plugin. Install it once:

```
athos opencode install       writes ~/.config/opencode/plugins/athos.js; restart OpenCode
```

With any model OpenCode runs, the pieces that match each message go into its system prompt, every task is recorded
with OpenCode's own token counts, and after a turn that changed something or followed a checklist Athos asks once
whether to save or improve a piece, as in Claude Code. `athos opencode uninstall` removes it.

### In Claude Desktop

In the **Code** tab, Claude Desktop runs Claude Code with the same settings, so the plugin works as it is, including
the trail pane beside the transcript. For the regular **chat**, which takes MCP servers but not plugins, install Athos
as a Desktop extension: `athos desktop` builds `dist/athos.mcpb`; double-click it (or drag it into Settings →
Extensions). It runs `athos mcp` against your own `~/.athos`.

In the chat, Athos finds the know-how for each request (`athos_find`) and opens its **trail panel** in the
conversation (MCP Apps): a greeting, the piece the task walks with each step ✓ done, ▶ now and ○ ahead as the model
reports it (`athos_step`), the steps your know-how lacks, and two buttons: **Adjust step** (you write how the step
changes; the piece is improved) and **Save new steps**. **Keep beside** pins the panel where the host allows it. In a
chat without MCP Apps, the same tools answer as text.

Step by step, for people who don't program: [docs/guides/claude-desktop-en.md](docs/guides/claude-desktop-en.md)
(en español: [docs/guides/claude-desktop.md](docs/guides/claude-desktop.md)).

Without the extension, the server can also be added by hand in Settings → Developer → Edit Config
(`claude_desktop_config.json`), with the absolute path of the `athos` command:

```json
{ "mcpServers": { "athos": { "command": "/Users/you/.local/bin/athos", "args": ["mcp"] } } }
```

### Inside a project, for any agent

`athos project sync` writes this project's know-how into `.athos/`, as plain markdown any agent reads without Athos
installed:

```
.athos/
  wiki/      Index.md (where a task starts), the pages, METHOD.md (how the pages and their trajectories were made)
  agents/    one subagent per trajectory, and AGENTS.md listing them
  skills/    one skill per page, and SKILLS.md listing them
  tools/     code the pages call when a step is a calculation, not a judgement
```

Each agent finds it where it already looks: `.claude/skills` and `CLAUDE.md` (Claude Code), `.agents/skills` and
`AGENTS.md` (Codex, Muse Code, OpenCode), `.claude/agents` and `.opencode/agents` (subagents). By default it picks the
pieces this project used or is tagged with (`--piece ID` or `--all` to choose), and adds itself to `.gitignore`: your
know-how stays yours even in someone else's repository, unless you share it with `--commit`. `athos project remove`
takes it all out again.

## Roadmap

- **Athos Cloud**: sync between your devices, a visual map of your know-how, daily control over what is shared, and an
  improvement agent as a service.

## Thanks

To the people whose ideas shaped Athos: see [WHY.md](WHY.md#thanks).

## License

Apache 2.0. See [LICENSE](LICENSE).
