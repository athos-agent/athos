# Athos reference: every command

*The [README](../README.md) shows how to use Athos without commands. This page is for people who like the terminal:
installing in each agent, handing tasks to cheaper models, the bench, and project folders.*

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
kind of task starts. Walks that cross pages become subagents that improve with the pages. See [docs/WIKI.md](WIKI.md). Choose what may load with
`/athos:load all | project <name> | pieces <id>... | none`, and copy everything out with `/athos:export <folder>`.

### Learning from your own edits

When the agent writes or edits a text file while following one of your pieces (a contract review, a report, code) and
you then change that file by hand, your change is usually a rule of how you work. Athos keeps a copy of each file as
the agent left it (`~/.athos/snapshots/<session>/`, text files up to 200 KB, only the last three tasks of the session).
On your next request in that session it compares the copy with the file: if you changed it, the agent gets a short diff
and is asked to propose the rule in one line, in your language, naming the step it belongs to, and to ask you before
adding it. Say yes and it improves the piece the same way [Adjust] does; a typo or spacing change is not mentioned.
Each edit is offered once and its copy is deleted right after; `athos status --json` shows it as `learned_from_edit`
(file, piece, step and the `Athos · adjust <piece>#<step>:` text a panel can prefill). It works in Claude Code, Codex
(`apply_patch`), Muse Code and OpenCode, stays on your machine, and is off with `ATHOS_CAPTURE=off`.

### Per-step models

For `athos delegate`: within one way of working, most steps are mechanical (extract the data, run a script, format a table) and one or two
need real reasoning. A statement can name the model it needs with an optional line:

```
## #judge
**When:** the totals are extracted.
**Do:** decide which invoices look wrong, and why.
**Model:** meta
```

The value is `local` (the default Ollama model), `meta` (muse-spark-1.3), `ollama:<model>` or `meta:<model>`. A
statement without it runs on the task's model (`--model` / `--backend`, else the default), and pieces without any
`**Model:**` line behave as before. An unknown value stops the run before anything starts.

```
athos delegate <piece> "<request>" --by-step                 each statement in turn, on its own model
athos delegate <piece> "<request>" --by-step --allow-meta    also let the steps marked meta run on Meta Model API
athos route <piece>                                          per step: which models ran it and how those tasks ended
athos route <piece> --apply                                  write the suggested **Model:** lines (a new version)
```

`--by-step` runs the piece statement by statement in one conversation: for each one the model is told "Now do only
this step: #id — <Do>" and works with the same tools and confirmations as a plain delegation. Each step is reported
to the trail, so `athos watch` ticks it as it goes, and the task's record keeps, per step, the model, the time and the
tokens. A step on Meta's hosted model sends the request and the files it reads off your machine, so it only runs with
`--allow-meta` (or `--backend meta`).

`athos route` reads your past by-step delegations of a piece and your marks on them, and suggests for each step the
cheapest model (local before hosted, a smaller local model before a larger one) that had at least three good marked
runs there and never ended in a corrected or failed task; otherwise it says why it has no suggestion. A mark is for
the whole task, so every step shares its task's mark, and unmarked runs prove nothing. `--apply` saves the suggestions
as a new version noted "routed by results"; `athos revert <piece>` undoes it.

### Your corrections as tests, your approved answers as references

When you mark a task that followed one of your pieces, Athos keeps it as a **case**, on your machine only, in
`~/.athos/cases/<piece>/<task>.json`: the whole request, the agent's final answer (from the agent's transcript, when
it can be read), the piece and version used, your mark, and for a corrected task your correction: the words you said
next that judged it wrong ("no, the notice is 30 days"), or your next request after `/athos:mark c`. Tasks you never
mark, or that used no piece, are not kept.

Each corrected case is a **test** of the piece. After you improve a piece, the save line says how many of your past
corrections can be re-checked, and the agent offers to run them:

```
athos test <piece>                           each past request answered again with the piece as it is now, and a
                                             second call judges whether the answer respects your correction
athos test <piece> --backend meta            the same on Meta Model API (--model to choose the model)
```

It prints one line per case (pass or fail, and why) and records the run. Each good case is a **reference**: `athos
shadow` answers your approved requests again on a cheaper model, with the piece, and judges how close each answer is
to the one you approved (0-100, equivalent or not):

```
athos shadow [--limit N]                     the approved tasks not yet compared on this model
athos shadow on                              after each task, compare one approved task in the background
athos shadow on --backend meta               the same on Meta Model API; `athos shadow off` stops it
```

Both answer with no tools (the piece as instructions, your request as the message) and run on Ollama on your machine
by default; nothing goes to a hosted model unless you choose `--backend meta`. In the background, the comparison runs
as a separate low-priority process that never delays your agent. Once a cheaper model has run at least 5 of a piece's
approved tasks and matched 9 of the last 10, Athos tells you once, in your language, at the start of a session or
when that piece loads: "Your «Review a contract» way of working is solid: Muse Spark matched 9 of your last 10
approved tasks. Want to hand it to Muse Spark?" Saying yes means running those tasks with `athos delegate`.
`athos status --json` shows the counts (`tests` per piece loaded) and the suggestions (`handoff`).

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

Step by step, for people who don't program: [docs/guides/claude-desktop-en.md](guides/claude-desktop-en.md)
(en español: [docs/guides/claude-desktop.md](guides/claude-desktop.md)).

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

### Guilds: one way of working for the team

When several people in a firm or a team improve their own copy of the same piece ("Review a lease"), Athos can merge
the best of each into one team version. Each colleague exports theirs:

```
athos export --guild <folder> --as Ana [--piece review-a-lease]
```

This writes each piece file and a `<id>.stats.json` beside it: per statement, how many of that person's tasks walked
it (the steps the agent reported) and how those tasks were marked (ok, corrected, failed). Only counts: no request, no
client, nothing about the work itself. Then, with their folders (or files) on your machine:

```
athos merge review-a-lease ./team                 a dry run: what it would keep, take from whom, drop, and why
athos merge review-a-lease ./team --apply         save it as a new version of your piece (the old one stays in history)
athos merge review-a-lease ana/lease-review.md --as-id lease-review     their copy has another id
athos merge review-a-lease ./team --model qwen3.5:9b                    let a local model merge differing texts
```

Statements are lined up by id, or by a **When** for the same moment when the ids differ (your id is kept, so links
still resolve). A statement only one copy has is kept if its tasks went well or nobody marked them, and dropped (and
listed) when most of its marked tasks were corrected or failed. Where the copies say different things, the text with
the best record wins; nobody's marks at all keeps yours. With `--model` (Ollama on this machine) or `--backend meta`
(sends those statements to Meta Model API), a model merges the differing texts into one, keeping your conventions, and
any answer that is not one clean statement falls back to the best record. The dry run writes the proposal to
`~/.athos/guild/<id>.merged.md` (`--out` to choose); `--apply` saves it with a history note naming the sources, and
`athos revert <id>` undoes it. In Claude Desktop's chat the same merge is the `athos_merge` tool ("merge my lease
review with Ana's version in this folder"): it proposes first and applies only when asked.
