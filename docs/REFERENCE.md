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
`/athos:load auto | all | project <name> | pieces <id>... | none`, and copy everything out with `/athos:export <folder>`.

### One memory per project

Each page says which projects it belongs to (`projects:` in its frontmatter; pages with none are general know-how).
By default (`auto`), a session in a project's folder loads that project's pages and the general ones; another
project's pages load only when the request names that project ("…like we did in heat-v2"). What a session starts
with is an index: this project's pages, and one line per other project saying what its know-how is about (its most
used pages, or your own words in `~/.athos/projects/<project>.md`). A folder no page belongs to, and Claude Desktop's
chat (no folder), see every page. `athos load all` brings back one pool for everything.

Measured on one person's store (71 pages over ten projects, 252 tasks marked good; `athos bench route --from-store`):
a page of another project loaded for 14 tasks with one pool and for none with `auto`.

### The journal: what happened lately in this project

Next to the ways of working (the long-term memory, which changes only when you save or approve), each session starts
with its project's recent past: the last tasks with what they used or saved and how they went, what was corrected or
failed in the last week, and the older tasks counted per way of working. `athos journal [--project <name>]` prints it.
It is read from the task log Athos already keeps on your machine; nothing new is stored, and another project's past
never shows up in this one.

### The library

`athos library [--port N] [--no-open]` opens every way of working you have as one page on `127.0.0.1` (default port
8712, the next free one otherwise), in English or Spanish like the rest of Athos:

- **What it gave you**: one bar per agent and model (the rows of `athos report`): its tasks, how many used your
  know-how, how many of those you marked went well, and the time and tokens of each.
- **The list**: each way of working with what it is for, how often it was used and how it went (good, corrected,
  failed, from your marks), in which agents and models, and its last improvement (`v3: …`). A filter narrows it by
  words. A page that is reached through another page's `**Calls:**` or `**If:**` sits under it, marked ↳ with the
  condition.
- **One page**: its steps as a checklist, with the branches nested under the step that leads there (↳, as in the
  panel); its versions with each one's note; **Go back to this version**, which asks first and then brings that version
  back as a new one (`athos revert <id> --to N` does the same; no version is ever deleted); and **Open in editor**,
  which opens the page's markdown file with your system's default app (only files inside `~/.athos/know-how`).

Nothing leaves your machine. The page's two actions are POST requests that need a random token made for each run and
carried only by the page itself, and the server answers only requests addressed to `127.0.0.1`/`localhost`, so another
website open in your browser can neither call them nor read your know-how. In Claude Desktop's chat the same page opens
as an MCP App when you ask to see your ways of working (`athos_library`, resource `ui://athos/library`); its buttons go
through the app-only tool `athos_library_do`.

### How the router picks the know-how, measured

On every request Athos loads the one or two pieces whose title and "when" share the request's words (rarer words count
more; [Didn't apply] remembers the words that loaded a piece by mistake). `athos bench route` measures that choice
before anything changes it:

```
athos bench route                         the public cases on a throwaway store of the starters (both languages),
                                          and each language's requests against the other language's starters only
athos bench route --scale 300             also a store padded to 300 pages with generated pages from other trades
athos bench route --router lexical,hybrid words only vs words + meaning (needs Ollama, see below)
athos bench route --from-store            your own tasks marked good against your own store: read-only, counts only
athos bench route --json
```

The cases (`athos/bench/route_cases.json`, fictional) are requests in English and Spanish for each starter (law,
sports, ops, journalism, science, finance), worded plainly and as paraphrases with few shared words, plus requests that
need no know-how ("what time is it", "write a haiku"). It reports hit@1 (the first piece loaded is the expected one),
missed (nothing loaded), wrong (a piece loaded that the request didn't call for; the pages an expected piece hands over
to don't count) and "none ok" (a request that needs nothing loaded nothing), with the time per request including
reading the store. `--from-store` uses the request that started each task you marked good and the pieces it used, and
prints only totals, never a request. Measured on 2026-10-31 (embeddinggemma through a local Ollama):

| router | store | hit@1 | wrong | none ok | ms/request |
|---|---|---|---|---|---|
| words | starters, en+es (18 pages) | 47/72 | 6 | 19/24 | 1.4 |
| words + meaning | starters, en+es | 57/72 | 6 | 19/24 | 17 |
| words | Spanish requests, English starters | 0/36 | 0 | 12/12 | 0.7 |
| words + meaning | Spanish requests, English starters | 9/36 | 0 | 12/12 | 24 |
| words | English requests, Spanish starters | 0/36 | 0 | 12/12 | 0.8 |
| words + meaning | English requests, Spanish starters | 15/36 | 0 | 12/12 | 13 |
| words | en+es, 300 pages | 44/72 | 18 | 21/24 | 13 |
| words + meaning | en+es, 300 pages | 54/72 | 21 | 19/24 | 33 |

`athos embed on` adds meaning to the words, with a local embedding model through Ollama (default `embeddinggemma`,
`athos embed on --model <name>` for another; `ollama pull embeddinggemma` first). It is off by default, and with it
off, or with Ollama down, loading is exactly the words-only router. When on, each piece's title, "when" and its
statements' `When:` lines are embedded once and kept in `~/.athos/index/` (by piece and a hash of that text, so an
edited piece is embedded again); pieces not indexed yet are filled by a background job, never while you wait. On each
request, when the words already found one clear piece nothing else happens; otherwise the request is embedded (under
300 ms, else words only) and the piece closest in meaning joins when it stands clearly above its usual closeness to
any request: this is what lets a Spanish request find an English piece. [Didn't apply] holds for these loads too.
`athos embed` shows whether it is on and how many pieces are indexed; `athos status --json` has `embed`. Nothing leaves
your machine. On the bench above it rescues cross-language and paraphrased requests without new wrong loads on the
starters, but on the 300-page store it adds three wrong loads, so it stays opt-in.

### Learning from your own edits

When the agent writes or edits a text file while following one of your pieces (a contract review, a report, code) and
you then change that file by hand, your change is usually a rule of how you work. Athos keeps a copy of each file as
the agent left it (`~/.athos/snapshots/<session>/`, text files up to 200 KB, only the last three tasks of the session).
On your next request in that session it compares the copy with the file: if you changed it, the agent gets a short diff
and is asked to propose the rule in one line, in your language, naming the step it belongs to, and to ask you before
adding it. Say yes and it improves the piece the same way [Adjust] does; a typo or spacing change is not mentioned.
Each edit is offered once and its copy is deleted right after; `athos status --json` shows it as `learned_from_edit`
(file, piece, step and the `Athos · adjust <piece>#<step>:` text a panel can prefill). The panels offer it as a
button, **Keep this rule** (Claude Code's pane, the Desktop panel, OpenCode's palette: *Athos: keep the rule from my
edit*); in Codex and Muse Code, `athos watch --trail` shows the edit and a plain "yes" to the agent keeps it. It works in Claude Code, Codex
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
athos opencode install       writes ~/.config/opencode/plugins/athos.js (it runs ~/.athos/bin/athos, the newest installed Athos); restart OpenCode
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

### First use and your other agents, from Desktop's panel

The panel also sets Athos up, one click at a time; nothing changes your setup without one.

- **First use**: with no ways of working yet, the panel asks what you do (law, finance, journalism, science, engineering
  on call, sports coaching, something else) in your language. A click adds that profession's example ways of working,
  exactly as `athos start` does, says in one line what it added, and offers a first request to try.
- **Use Athos in your other agents too**: the panel lists Codex, OpenCode and Muse Code when they are on this computer
  (their command on PATH, or their config folder), each with **Connect**. Codex runs the same code as
  `athos codex install` (then approve the hooks once with `/hooks` in Codex), OpenCode the same as
  `athos opencode install` (then restart OpenCode), and Muse Code runs `muse plugins marketplace add athos
  https://github.com/athos-agent/athos`, `muse plugins install athos@athos` and `muse plugins approve athos`.
- **Versions**: one line when an agent runs an older Athos than the newest on this computer, with what to do.

Both buttons call tools only the panel sees (`athos_start`, `athos_connect`); the model never calls them.

### athos doctor

```
athos doctor [--json]
```

Which Athos each agent would run, and which are behind the newest one on this computer: Claude Code (its plugin
cache), Claude Desktop (the extension's `manifest.json`), Codex (the `athos` its hooks run: `~/.athos/bin/athos` runs
the newest Claude Code plugin), OpenCode (the `athos` its plugin runs), Muse Code (its plugin record, or
`muse plugins list` with a short timeout) and the `athos` on PATH. It exits 1 when one is behind. The same line is in
`athos status --json` (`behind`) and in Desktop's panel.

### The gallery

`gallery/` holds ways of working anyone can take, in English and Spanish: normal Athos pages (frontmatter with `id`,
`title`, `when`, `profession`, `lang`; statements with **If:** and **Calls:** branches). Every example is fictional and
leaves the professional decisions to the person. `athos gallery build [--out DIR]` writes `gallery.json` (each page,
its steps and branches, and the pages it calls) and `index.html`, a static page that previews each entry as the panel
draws it, filtered by profession and language. Its **Use in Athos** button copies a short request:

```
Athos · add from gallery: review-a-services-contract
```

Pasted in any agent with Athos, the prompt hook (or `athos_find` in Desktop) has the agent run the add:

```
athos add <id | raw URL> [--dry-run]       athos_add in Desktop's chat
```

It downloads only from `https://raw.githubusercontent.com/athos-agent/athos/main/gallery/` (any other host or path is
refused), the entry and the pages it links to, and saves each one you don't have yet as version 1 with origin
`gallery`. A page you already have is left as it is. To contribute an entry, open a pull request with its pages in
both languages; `tests/test_gallery.py` checks that every link and branch leads to a page in the gallery.

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
