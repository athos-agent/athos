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

Then `athos start` asks your language and profession and adds example ways of working (law, finance, journalism, science and engineering on call today).

Requires Python 3.11+ (the installer picks the newest one you have). No other dependencies. The hooks run under
whatever `python3` the agent finds, which may be older (macOS ships 3.9): they do not need `tomllib`, and read the
project marker's `name` and `public` lines without it. Your know-how lives in `~/.athos/know-how`, the same for every
agent. Several hooks, the background verifier and your editor may touch the same files at once, so every file Athos
writes there that more than one process writes (a page, a session's state, the profile, the loading mode, the
config, the review marks, the edit detector's clock) is replaced in one step (written beside it, then moved over it),
and the ones read, changed and written back (a session, the profile, the config, the review marks) are changed under a
lock. A state file that cannot be read is retried and then reported as an error: it is never read as empty and
written back over itself.

## Use

Athos works on its own: it loads matching know-how with each request and, on a frontier model, keeps what a task
proved without asking (see "Autonomous learning" below). These are the commands you will reach for:

```
/athos:list          see your know-how and what is enabled
/athos:mark g        mark the last task: g good, c needed corrections, f failed
/athos:report        what each piece and each model brings to your work
/athos:codex         take your know-how to Codex
```

### What you see: one small square

In Claude Code (the terminal and the Desktop app's Code tab) Athos shows one thing, at the right of the prompt's
footer, beside Claude Code's own mode labels, while the agent works and while it waits:

| state | what you see | when |
|---|---|---|
| learning | a red ■ and `Athos is learning` (`Athos está aprendiendo`) | the session runs on a frontier model with autonomous learning on, no piece is in use, and the task in progress did work or produced evidence (a verification, a commit), or a save or an independent verification this session started is still running |
| collaborating | a green ■ and `Athos is collaborating` (`Athos está colaborando`) | one of your pieces is in use for the task in progress: given to an apply model, or opened by a frontier model from the index; until the task ends |
| idle | nothing | everything else: Athos off, nothing matched, a question that only read, between tasks |

If both could apply, collaborating wins. Nothing else is drawn and no hook line is shown to you: no status line, no
trail pane, no band above the prompt or its buttons, no toasts, no "Stop hook feedback" line, and the model is not
asked to pass Athos's offers on to you (a cheaper model, the overnight review, a rule from your edits, a re-check).
What Athos decides still goes to its log (`athos audit`), and every change of the square is one `ui` event there.

`athos status --json` carries the same state as `state` (`learning`, `collaborating`, `idle`) with a short `why`
(`gathering_evidence`, `task_with_work`, `save_asked`, `verifying`, `piece_delivered`, `piece_opened`, `nothing_in_use`,
`between_tasks`, `no_task`, `off`, …); `athos status --ui` is what the hooks module polls (only that, in this
interface). Reading it writes nothing, except the one `ui` event and `sessions/ui/<session>.json` when the state
changes. An interrupted turn never reaches the Stop hook, so a task is shown as idle as soon as Claude Code's transcript
notes that you interrupted it (`interrupted`), or once its session has not moved in 6 minutes with no tool call
running; a tool call that started and has not ended keeps the square on however long it runs.

**The classic interface.** `ATHOS_UI=classic` in the environment Claude Code starts with, or `"ui": "classic"` in
`~/.athos/config.json` (which also reaches Desktop's chat and the hooks module however Claude Code was started), brings
back everything below: the status line, the trail pane, the band with [Save], [Not now], [Didn't apply], [Show trail],
[Change this step] and [Keep this rule], the verdict row, the bars, the "following" line and its steps, the toasts,
and the lines the model was asked to tell you. `ATHOS_UI=minimal` (or `"ui": "minimal"`) is the default.

What stays visible where, in the minimal interface: in Desktop's regular chat the trail panel no longer opens on its
own (the model's `athos_find` and `athos_done` no longer carry it), and `athos_library` still opens the library when
you ask; in OpenCode the sidebar stays where you put it, but its step toasts are off; `athos watch`, `athos watch
--web` and `athos library` show what they always showed, only when you run them. A command you type yourself
(`athos list`, `athos mark`, …) prints as before.

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

Meta's open-weights model also runs on [Baseten](https://www.baseten.co) Model APIs (`--backend baseten`), through
Baseten's OpenAI-compatible endpoint (`https://inference.baseten.co/v1`), in the same loop as `--backend meta`. Create
an API key at [app.baseten.co/settings/api_keys](https://app.baseten.co/settings/api_keys) (Organization settings →
API keys → Create API key; copy it at once, Baseten shows it only then) and put it on a line of `~/.athos/.env` (or
export it as `BASETEN_API_KEY`); Athos reads it only to send the request and never prints it:

```
BASETEN_API_KEY=<your key>
```

```
athos delegate <piece> "<request>" --backend baseten     meta-models/muse-spark-open-1026, recorded as `baseten`
athos delegate <piece> "<request>" --backend baseten --model meta-models/muse-spark-open
athos test <piece> --backend baseten                     your corrections as tests, on Baseten
athos shadow on --backend baseten                        the background comparison, on Baseten
athos merge <piece> <their-files>... --backend baseten   a model merges differing texts, on Baseten
athos bench <case> --agents baseten,meta,local --runs 3
```

The default model is the slug the Meta hackathon names; Baseten's model page lists `meta-models/muse-spark-open`, so
use `--model` if your account shows another (`GET https://inference.baseten.co/v1/models` lists them). The model
always reasons; Athos asks for `reasoning_effort: low` (Baseten's default is `xhigh`). With `--by-step`, a statement
whose `**Model:**` is `baseten` or `baseten:<model>` runs there, with `--allow-meta` as for Meta. Like `--backend
meta`, it sends the request and the files the model reads to a hosted service; nothing goes there unless you choose it.
In `athos bench`, a Baseten run's cost shows as unknown.

The same open-weights model also runs through [OpenRouter](https://openrouter.ai) (`--backend openrouter`), which
serves `meta/muse-spark-open` from several inference providers (BaseTen, Fireworks, Together, Nebius, Modal…) at
US$1.25 / 4.25 per million tokens in and out. Create a key at [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys),
add credits, and put it on a line of `~/.athos/.env` (or export it as `OPENROUTER_API_KEY`):

```
OPENROUTER_API_KEY=<your key>
```

```
athos delegate <piece> "<request>" --backend openrouter     meta/muse-spark-open, recorded as `openrouter`
athos test <piece> --backend openrouter                     your corrections as tests, through OpenRouter
athos bench <case> --agents openrouter,meta --runs 5 --without
```

Athos asks for `reasoning: {effort: low}`. With `--by-step`, a statement whose `**Model:**` is `openrouter` or
`openrouter:<model>` runs there, with `--allow-meta`. It sends the request and the files the model reads to OpenRouter
and the provider it picks; nothing goes there unless you choose it. A bench run is priced at the list price above.

To see what the know-how is worth before trusting a cheaper model with it, `athos bench` runs the same task several
times on each agent and model, with and without the know-how, and checks what each run left behind (git, the tests,
the files) instead of taking the agent's word:

```
athos bench --list                                         the cases: code, data, devices, a planning method, finance ops, law, literature
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

A way of working can also be dictated. Record yourself explaining how you do a task (a voice memo is enough) and run
`athos save --from-audio memo.m4a [--lang es|en]`: Meta's Muse Voice Transcribe (`muse-voice-transcribe-1.0`, Meta
Model API's file endpoint) writes down what you said, and Muse Spark (`muse-spark-1.3`) turns it into a draft piece in
the format above, one statement per step, keeping your words and leaving out what you did not say. You see the draft
and it is saved only when you answer yes; `--yes` saves it without asking, and without a terminal (an agent running
the command) the draft is printed with the `athos save` command that stores it. The endpoint takes a mono 16-bit WAV
at 16 or 24 kHz of up to 10 minutes; any other recording is converted first with `afconvert` (macOS) or `ffmpeg` when
one of them is installed, and nothing is installed for you. The recording and its transcript go to Meta only when you
run this command, with your `MODEL_API_KEY`.

### One memory per project

Each page says which projects it belongs to (`projects:` in its frontmatter). A page you save belongs to the project
you saved it in. By default (`auto`), a session in a project's folder loads that project's pages and your **profile**;
another project's pages load only when the request names that project ("…like we did in heat-v2"; "heat v2" counts
too). The longest name wins: "heat-v2" names heat-v2, not a project called heat; and a name of four letters or fewer
counts only as a word of its own ("api" is named by "the api", not by "api.js").

**A project named like a common word needs a cue** (since 0.1.165). A name that is also a common word in your store
(every word of it is in at least 10% of the other projects' pages, and in two of them: the same word rarity the router
weighs words by, with the project's own pages left out) or a one-word name of three letters or fewer ("api", "web") is
ambiguous: "the api returns 500" may not mean the project at all. Such a name counts only with a reference cue: a
preposition or phrase of reference ("in api", "from api", "from the api repo", "the api project", "como hicimos en api",
"del proyecto api", "en el repo api"), a path (`~/api`, `api/`, `/api/`), or the name in backticks or quotes. A
distinctive name ("heat-v2") keeps working without one. Without a cue, on a frontier model, the request's index gets one
line instead (the request may also mean the project `api`, with how many pages it has, and `athos list --project api`
to list them), so the model decides; nothing of that project is loaded or listed by id. On an apply model the mention is
dropped. In a repository marked public nothing is offered. The `route` event records how each mentioned project was
decided (`named_how`: cue, distinctive, offered, rejected; in a public repository only `named_how_count`) and the
projects offered (`offered_projects`), never the words; `athos audit` does not flag a piece of an offered project the
model opened itself. Measured on 2026-11-15 over one person's 1769 recorded request heads: 40 named another project
before; with the cue rule 17 by a cue, 22 by a distinctive name, and 6 are ambiguous mentions that no longer bring that
project's pages in. `bench route` (34/56 hit@1, 1 wrong, 24/24 none ok), `--from-store` and the private replay of one
session (0 of 29 loaded, both tiers) are unchanged.

A project with no
pages of its own yet sees only the profile (until 0.1.110 it saw every page, and loaded other projects' pages on its
first day). Claude Desktop's chat, which has no folder, still sees every page, and `athos load all` brings back one pool
for everything (but a private page, below, stays in its projects).

The profile is a short list you choose of the pages that apply everywhere, how you always work (at most 12):

```
athos profile                         the pages in it
athos profile add <id>... | remove <id>...
athos profile allow-public <id>... | deny-public <id>...   whether a profile page also loads in a public repository
athos profile --untagged [--json]     the pages with no project, and whether each is in the profile (read-only)
```

A page with no project is not general just because it has no tag: outside the profile it loads only where no folder is
known, or with `athos load all`. `athos start` puts the profession's example pages in the profile, and so does
`athos add` for a page from the gallery. Only the profile goes to `~/.agents/skills`, the folder Codex and Muse Code
read in every project (`athos export --codex` and the refresh after each save); `athos project sync` gives a project's
own pages to the agents in that project.

What a session starts with is an index: this project's pages and the profile, and of the other projects only a count
("12 ways of working in 4 other projects"), never their names or titles.

**Who may see a page.** A page's frontmatter may say `visibility: private`, `project` or `general`. Without it, a page
with projects is `project` and one without is `general`. A private page loads only in a session of one of its own
projects, never where the repository is marked public (below), and is never named in another project's session: not in
its index, the audit log, `log.md` or anything the hooks add, not even when the request names its project.
`athos privacy [--json]` lists the pages that look private (data that points at a person or an account, or a body about
clients, patients, money or production), by id, for you to review; it changes nothing. To mark one, add the line
`visibility: private` under `projects:`.

**The project marker.** An optional `.athos.toml` at the root of a repository:

```
name = "my-app"      # the project's name, whatever the folder is called (default: the repository's folder name)
public = true        # a public repository
```

Whoever wrote a repository wrote its marker, so a `name` is not taken on trust: a cloned repository could name itself
after one of your projects and get that project's pages. Athos uses the marker's `name` when it is the folder's own
name, or once you accept it for that folder on this machine with `athos public name` (kept in
`~/.athos/marker-names.json`, never in the repository; a later change of the name is not accepted until you run it
again). Until then the folder's name is used, `athos public status` says so, and `athos audit` reports
`marker_name_ignored`. `public = true` holds whatever the name: declaring a repository public can only restrict.

Athos looks for it in the folder a session runs in and in every folder above it, without relying on git, and fails
closed: any marker on the way up that says `public = true` makes the folder public, so a subfolder, a repository
nested in a public one, and a folder where git cannot run (not installed, timed out, refused by `safe.directory`) are
public too. In a `git worktree` with no marker of its own, the main worktree's marker applies (found from the
worktree's `.git` file, so this needs no git either). A marker that is there but cannot be read (not valid TOML, not
text, or a `public` that is not `true` or `false`, such as `public = "true"`) is read as public. What still escapes it:
a marker in a folder that is neither the session's folder nor above it (a sibling checkout, a submodule's
superproject reached only through git, a repository whose `.git` lives elsewhere through `GIT_DIR`), and a public
repository with no marker at all, which Athos cannot know about (below).

**In a public repository, everything else is private.** In a repository whose marker says `public = true`, only that
project's own pages load (and none of them marked private). Every other page is treated as private there, whatever its
`visibility`: it never loads and is never named, not in the session's index, a frontier request's index, a page
handed over to, `log.md`, the journal, the pane, or anything the hooks add, even when the request names its project,
which elsewhere would bring it (the `route` event keeps only how many projects were named, `named_count`). No command
run there names one either: `athos list`, `profile` (and `--untagged`), `report`, `wiki`, `status --json`, `privacy`
and `audit` leave them out or only count them; a command given the id of a page that may not be named there (`show`,
`revert`, `test`, `share`, `route`, `verify`, `dismiss`, `delegate`, `merge`, `export --piece`) answers exactly as for
an id that does not exist, so the answer does not say whether another project has it, and so does `athos save` with
such an `id:` (nothing is changed or created; a new page is saved by leaving `id:` out); `athos audit` reads only this
project's sessions and refuses `--show` and `--project` of another one; `athos journal --project` of another project
is refused; `athos export` to a folder writes only this project's pages, and `--dataset` (which holds requests) is
refused. One check (`control.Here`) decides for all of them, and a test runs every command in a public repository.
Profile pages are included in this: one loads in a public repository only once you allow it with `athos profile
allow-public <id>`; by default none does. You do not need to mark pages one by one: the per-page `visibility` field
stays available, and in a repository that is not marked public the usual rule holds.

**Declaring a repository public.** `athos public` writes `public = true` into the `.athos.toml` at the root of the
repository you run it in (creating it with the project's name when there is none, and keeping any other line); `athos
public off` writes `public = false`; `athos public status [--json]` says what is declared and which code-hosting sites
the repository is pushed to; `athos public name` accepts the name its marker gives it. The line goes among the
marker's top-level keys, before any `[table]`, and the file is read back: the command fails, and leaves the file as it
was, unless it now says what was asked. A marker that cannot be read is not touched: the command says that Athos
treats the repository as public until the file is fixed. Athos asks because it cannot know: whether a repository is public lives on the hosting
site, behind your account, and Athos makes no network call. Your local git configuration only says where the code is
pushed, not who can read it there. So `athos audit`, run in a repository that has a remote on a code-hosting site
(GitHub, GitLab, Bitbucket, Codeberg and the like) and no `public` line in its marker, reports `public_not_declared`
until you answer either way. Until then the repository is treated as not public.

In a public repository no words of a request and no hash of a request are stored: the task log keeps the request's
length but not its first 120 characters, the audit events and the session no fingerprint (`request_sha`,
`prompt_sha`), the session no copy, and [Didn't apply] no words. Without a fingerprint, a special path (save, adjust)
that acted on text reading as the person's before Claude Code wrote its transcript entry can be checked against the
transcript only when the hook gives the prompt's id; otherwise it stays unverified. What is still stored there are
flags derived from a request, never its words: a mark inferred from the person's reaction and `reaction_corrected`,
`+named` in a scope reason in `log.md` and `named_count` (how many other projects it named, never which), whether it
mentioned a checklist, the language it was written in (`lang_seen`), and its length. The `route` event says when a
marker applied (`marker`, `public`).

Measured on one person's store (71 pages over ten projects, 252 tasks marked good; `athos bench route --from-store`):
a page of another project loaded for 14 tasks with one pool and for none with `auto`. Measured again on 2026-11-15
(91 pages, 343 tasks marked good), counting every task this time, also those of projects with no pages of their own
that the count used to skip: 2 tasks with the 0.1.110 scope, both in such projects, and none now.

### The journal: what happened lately in this project

Next to the ways of working (the long-term memory, which changes only when you save or approve), each session starts
with its project's recent past: the last tasks with what they used or saved and how they went, what was corrected or
failed in the last week, and the older tasks counted per way of working. `athos journal [--project <name>]` prints it.
It is read from the task log Athos already keeps on your machine; nothing new is stored, and another project's past
never shows up in this one. Since 0.1.166 the journal is short-term memory in the strict sense: its lines come from
the live log's window (below); tasks the dream cycle archived are only counted in "Before that", never quoted.

### Long-term memory: the live log, its archive, and the dream cycle

The task log (`~/.athos/events.jsonl`) used to grow without bound, and the hooks read all of it. It now has three
layers:

| layer | where | what |
|---|---|---|
| short-term | `events.jsonl` | the raw events of a recent window: the hooks append here |
| consolidated | `memory/archive/events-NNNNN.jsonl.gz`, `archive/manifest.json`, `memory/ledger.json`, `memory/rollups.json` | the events outside the window, compressed and never deleted (the manifest keeps each segment's lines, bytes and sha256); the ledger, those events folded per task without a word of any request; the rollups, small sums the hooks read: per piece (uses, outcomes, by platform, model tier and project, last use, means, the run that taught it), per project (tasks, the pieces they used, requests that found no piece, counted, never quoted), pieces used in the same task, the grading history of learned pieces, the verifier's and the shadow runs' outcomes, the stars |
| long-term | `know-how/`, `projects/<name>.md` | the wiki: your pieces, and a page per project saying what is known about working in it |

The ledger and the rollups are derived: delete them and `athos memory rebuild` folds the archive again into the same
files (`athos memory check` compares them with a rebuild and checks every segment against its manifest).

**The window.** The live log keeps at least `keep_days` (30) and at most `keep_bytes` (4 MB), cutting older days
when it is over, but never the last `min_keep_days` (8), so the journal and the marks that look a week back always
read the live log. All of these are `"memory"` keys in `~/.athos/config.json`.

**What reads what.** The hooks (session start, prompt, tool, stop) and `athos status` read only the rollups and the
live log, so what they cost does not grow with the archive: a piece's record and the bars, the journal, the grading
history of a learned piece, which candidates wait for the verifier, the shadow runs and the star review. Offline
commands read the whole history, the archive decompressed and then the live log: `athos report`, `audit`, `curate`,
`repair`, `bench route --from-store`, the importers of Codex and Muse Code sessions; `report`, `audit` and `repair`
say so on stderr (`history: N archived event(s) in K segment(s) read with the live log`) when there is an archive.
A task begun before the cut and continued after it is kept whole in the rollups and folded with its live lines. A
line written about an archived task (an `athos repair` correction, a late `athos mark`) is left out of the hooks'
numbers until the rollups take it, which `athos repair --apply` and `athos mark` do at once, and the next cycle does
in any case; offline commands count it immediately.

**The dream cycle**, in three phases (after the slow-wave replay, REM abstraction and consolidation of sleep):

1. **Replay and prune.** The events outside the window, a prefix of the live log, are written to a new compressed
   segment, folded into the ledger and the rollups, and only then trimmed from the live log. Nothing is deleted.
2. **Abstraction**, by counting, no model: pieces used in the same task (three or more), requests that found no
   piece and the ones that came back more than once still without one (by fingerprint, never their words), pieces
   that look like the same way of working (the test `athos curate` uses, and statements for the same moment), steps
   you corrected by hand at least twice, pieces whose own Check failed in at least two reuses; and the star review
   `athos dream` has always made. They are kept in `memory/findings.json` (`athos memory findings`).
3. **Consolidation.** One page per project, `projects/<name>.md`: its ways of working with their uses, outcomes and
   status, the pieces used together, how often a request found nothing, and what to look at. It names only pieces
   that may be named in that project's own sessions (another project's are counted, and in a project whose
   repository is marked public, only what may load there); no request is quoted. A page without the line
   `written_by: athos` in its frontmatter is yours and is never touched; a page Athos wrote and rewrites is kept in
   `projects/.history/` first. Whether a project's repository is public is kept with its counts, so it holds after
   its route events are archived. `athos memory project [<name>]` prints it; in a repository marked public only that
   project's own page, and never the stored page as it is: one Athos wrote is made again as that repository may see
   it, and any line naming a piece that may not be named there is left out. `athos memory findings` there keeps only
   this project's rows and pieces that may be named in it. The no-model cycle writes no piece file: associations stay in the rollups and the project
   pages.

Every step can be interrupted and run again: a segment is written atomically before anything refers to it (synced,
with its folder, and so are the manifest, the ledger and the rollups, so a power cut leaves the old file or the new
one), the ledger lists the segments it folded, and the live log is trimmed only while it still starts with the
segments' exact bytes, under the lock every append takes, held only for the copy of what stays. A first cycle on a
long log reads it as a stream and writes segments of 8 MB at most.

Nothing is lost or counted twice whoever else writes the log:

- *A writer without the lock* (an older Athos, another tool) that opened the log before a trim and writes after it
  writes into the old file: it stays reachable under a hidden name (`.events.jsonl.trim-…`) and what reaches it is
  carried over at the end of the cycle and again at the next one (the Stop hook asks for a cycle when something waits
  there), until nobody has written into it for 30 seconds.
- *A log put back* after a trim (a backup restore, a sync tool, two machines sharing the home) starts with segments
  already archived: every reader skips them by their bytes, whatever their state, and the next cycle trims them
  again; bytes the archive already holds are never written as a new segment. A log that repeats archived lines
  without starting at a segment's boundary is neither archived nor trimmed, and a log replaced between archiving and
  trimming is left as it is (its segment is marked `kept`); either way the cycle's `replay` event says why
  (`refused`).
- *Readers during a cycle* read the live log first and then the manifest and the rollups (a full-history read takes
  the append lock for those two reads), so a cycle that archives and trims meanwhile can neither hide a segment from
  them nor make them count one twice.

Tidying never deletes a segment: a temporary segment left by a power cut is promoted when it decompresses (dropped
only when the same bytes are already in place, set aside in `memory/archive/damaged/` otherwise); one the manifest
does not list is listed again; one that cannot be read is moved to `damaged/`; a manifest that cannot be read is
moved there too and rebuilt from the segments on disk; and a ledger or rollups that are lost or unreadable are made
again by the next cycle, which the hooks start as soon as they notice. One cycle runs at a time: an exclusive `flock`
on `memory/.cycle.lock` held for the whole run, so it is never taken from a live process and goes with a process that
died. The
Stop hook starts it detached and at low priority, the way it starts the verifier, when the live log passes
`trigger_bytes` (6 MB) or its oldest event is older than `trigger_days` (37), or a segment was left half done, or a
late line waits; `"memory": {"auto": false}` turns that off. Each phase is a `memory_cycle` event (`run_id`, `phase`
(replay, abstraction, consolidation, model, done), its counts, `duration_ms`, for replay `archived_lines`,
`archived_bytes`, `compressed_bytes`, `live_before`, `live_after`, `rollup_bytes`, and `spend_usd` at the end).

```
athos memory [status]                  the layers' sizes and dates, and whether a cycle is due or running
athos memory cycle [--model] [--json]  run it now, in the foreground
athos memory check                     every segment against its manifest; ledger and rollups against a rebuild
athos memory rebuild                   make the ledger and the rollups again from the archive
athos memory findings                  what the last counting found
athos memory project [<name>]          a project's page
```

**The model pass**, opt-in and off by default (`"memory": {"model": {"on": true, "model": "<id or alias>"}}`, or
`athos memory cycle --model` once): on a frontier model, only when no session has moved in `idle_minutes` (30), and
under the daily cap it shares with the independent verifier (`autolearn.budget`: the run's cap is reserved first, a
`model_run` event with `purpose` dream). One project per pass, the one with the most to look at. The model gets, as
files in a folder and nothing else, the project's counted summary (no request words) and the text of that project's
own pieces that are not private (title, when, body: never another project's, never a private piece, never
frontmatter or history), and runs as the verifier does:
headless, read-only tools confined to that folder, no plugins, hooks or MCP, a throwaway Athos home. What it proposes
is always a candidate:

- a short paragraph of what is known about working in the project goes to `projects/<name>.candidate.md`
  (`status: candidate`), beside the page the counting writes; it is not injected anywhere;
- two or more of the project's pieces that are the same way of working become a **new** candidate piece (the sources
  stay as they are), only if `bench route --from-store` with it is no worse than without it (no fewer first hits, no
  more loads of a piece the task didn't use, of a piece where nothing was needed, or of another project's), and then it
  goes to the independent verifier like any candidate;
- an avoid or keep rule for a step is a new candidate version of a learned piece of the project, through the same
  versioned update path and the verifier (a verified piece is verified again from scratch); for a piece you own (no
  `status`) it is only a proposal in `memory/findings.json`, never written into its file.

Every write is listed in the cycle's `model` event (`wrote`, each with the piece's status before).

**Pieces used together, at load time.** `"memory": {"associations_line": true}` adds at most one line to a frontier
model's index: the piece most often used in the same task as the router's first choice (three tasks or more, from the
rollups and the live log), when it is in reach and not listed yet; an apply model gets nothing more. It is off: on one
person's 343 good tasks (2026-11-15, each task's own pairs left out of the counts), the router chose a piece for 91
of them per project and 56 of those used another piece too; the line was added to 16 indexes and named a piece the
task used in none, and the tasks whose other piece reached the index stayed 18 (with one pool: 25 lines, none used,
20 and 20). The router's choice, and so `bench route`, `--from-store` and the private replay, do not change either
way.

**`athos dream`** is the star review, unchanged: `athos dream` lists its proposals and `athos dream --apply N` turns
one into the request your agent carries out. It is now one part of the cycle's abstraction phase, which refreshes it;
`athos dream --cycle` runs the whole cycle.

What you see does not change: the cycle shows nothing in the interface, and the only new output is that of the
commands above when you run them, and the `history:` line of the offline commands once there is an archive.

### Curating: tidy the memory as it grows

`athos curate` lists what is worth tidying, found from your pages and your task log: a page used in a project it
isn't tagged with (per-project loading would leave it out there), a page unused for 45 days (one that another page
calls is never proposed), two pages that look like the same way of working, links to pages or steps that don't
exist, and work that keeps coming back in a project with no page for it. `athos curate apply <n>...` does the
mechanical ones: tag the page with the project (a new version) or move it to `~/.athos/archive/` (it no longer
loads; `athos curate restore <id>` brings it back). The rest are for you to act on. Nothing changes until you say
which.

It also learns from what went wrong: when you corrected a task that followed a page (your words after marking it
corrected), it proposes a "don't" step for that page with your corrections, and prints the request that adds it, ready
to paste; a page with at least three corrected or failed tasks and more than twice as many as good ones is flagged
for review. Each pass is logged in `~/.athos/curate.json`: proposals not shown before are marked new, and `athos curate
dismiss <n>...` hides one for good. Tests and rehearsals propose nothing: tasks in a temporary or demo folder, projects
named like one (prueba, test, demo, tmp, scratch, sandbox, example), and any project you mark with `athos curate
ignore <project>`.

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
  back as a new one (`athos revert <id> --to N` does the same; no version is ever deleted, and the page keeps the
  `visibility` and `projects` it has now, so a `visibility: private` added by hand survives); and **Open in editor**,
  which opens the page's markdown file with your system's default app (only files inside `~/.athos/know-how`).

Nothing leaves your machine. The page's two actions are POST requests that need a random token made for each run and
carried only by the page itself, and the server answers only requests addressed to `127.0.0.1`/`localhost`, so another
website open in your browser can neither call them nor read your know-how. In Claude Desktop's chat the same page opens
as an MCP App when you ask to see your ways of working (`athos_library`, resource `ui://athos/library`); its buttons go
through the app-only tool `athos_library_do`.

### How the router picks the know-how, measured

On every request Athos loads the one or two pieces whose title and "when" share the request's words (rarer words count
more, and a word counts with its endings: publish, published, publishing; publicar, publicado; [Didn't apply]
remembers the words that loaded a piece by mistake). Since 0.1.111 a piece also needs a margin, because a score grows
with the request's length and a long pasted text shares words with almost any page: at least 5% of the words of its
title and "when" must be in the request (`head_share_min`), and those shared words must be at least 7% of the request's
own words (`request_share_min`), so a request cannot win on volume. What a request adds is capped at 8000 characters.
A page that doesn't fit comes as its steps (since 0.1.117): each statement's When and Do, and its hand-overs, without
the reasons, links and history, with a note on how to read the whole page (`athos show <id>`); if even that doesn't
fit, as many whole steps as fit, naming the ones left out. A page without statements is cut at a line. The route event
records it (`steps_only`, `cut`, `left_out`). On one person's store (91 pieces, 2026-11-15) 13 piece files pass 8000
characters (by 126 to 18963, median 2410) and 12 did not fit a request: cut at a line, they delivered 112 of their 191
steps with When and Do; as steps, 158, and 7 of the 12 arrive with every step. Nothing in it asks the model for visible work: no opening line naming the page, no
step commands; only the page and a short note on how to answer. `athos bench route` measures that choice
before anything changes it:

```
athos bench route                         the public cases on a throwaway store of the starters (both languages),
                                          and each language's requests against the other language's starters only
athos bench route --scale 300             also a store padded to 300 pages with generated pages from other trades
athos bench route --router lexical,hybrid words only vs words + meaning (needs Ollama, see below)
athos bench route --from-store            your own tasks marked good against your own store: read-only, counts only
athos bench route --replay <file>         one session's requests again, through the scope the hooks apply
athos bench route --json
```

The cases (`athos/bench/route_cases.json`, fictional) are requests in English and Spanish for each starter (law,
ops, journalism, science, finance), worded plainly and as paraphrases with few shared words, plus requests that
need no know-how ("what time is it", "write a haiku"). It reports hit@1 (the first piece loaded is the expected one),
missed (nothing loaded), wrong (a piece loaded that the request didn't call for; the pages an expected piece hands over
to don't count) and "none ok" (a request that needs nothing loaded nothing), with the time per request including
reading the store. `--from-store` uses the request that started each task you marked good and the pieces it used, and
prints only totals, never a request. `--replay <file>` runs the requests of one session (a JSON file you keep outside
the repository, since it holds real requests: `{"project": "<name>", "cwd": "<optional folder>", "public": <optional
true>, "cases": [{"request": "...", "expect": []}]}`, `expect` being the piece ids it should load, none when empty)
through the loading mode and per-project scope the hooks apply, the public rule (the case's `public`, or the marker of
its `cwd`), and what the tier's model may be given (no retired piece; to an apply model only verified and legacy
ones), then `load.relevant`, and counts the requests where something loaded,
where a piece of another project loaded, where a general piece loaded, the ones that loaded exactly what was expected,
and the characters added (largest and mean); `--show` adds, per request that loaded something, its number, its length
and the ids loaded, never its text. Measured on 2026-10-31 without the sports starters (embeddinggemma through a local Ollama):

| router | store | hit@1 | wrong | none ok | ms/request |
|---|---|---|---|---|---|
| words | starters, en+es (14 pages) | 34/56 | 2 | 23/24 | 1.3 |
| words + meaning | starters, en+es | 43/56 | 2 | 23/24 | 17 |
| words | Spanish requests, English starters | 0/28 | 0 | 12/12 | 0.6 |
| words + meaning | Spanish requests, English starters | 6/28 | 0 | 12/12 | 20 |
| words | English requests, Spanish starters | 0/28 | 0 | 12/12 | 0.7 |
| words + meaning | English requests, Spanish starters | 10/28 | 0 | 12/12 | 14 |
| words | en+es, 300 pages | 33/56 | 7 | 23/24 | 15 |
| words + meaning | en+es, 300 pages | 40/56 | 11 | 21/24 | 36 |

With the margin (0.1.111, measured on 2026-11-15, words only): starters en+es 34/56, 1 wrong, 24/24 none ok; 300
pages 33/56, 6 wrong, 24/24; the cross-language runs unchanged. The two values were the largest that cost no hit on
these cases while turning down most of the loads of one real session whose requests needed nothing (long pasted texts
among them). On one person's own tasks (`--from-store`, per project) hit@1 went from 38 to 28 of 141: 8 of the 10
lost were turned down by the margin (7 of them single-word matches on pages with a long "when") and 2 are pages no
longer in reach there (one untagged page outside the profile). That bench counts as expected whatever loaded at the
time, so it rewards the old router; requests that needed nothing and loaded something went from 20 to 13 of 202.

**Pull instead of push, on frontier models.** When the model answering a request is in the frontier tier (`athos
tiers`), the router's choice is not pasted in: the request gets a short index of the pieces in reach instead, best
first (the router's choice and the pages it hands over to, then the other pieces it scored, then the rest of this
project's pieces and your profile, most recently used first), one line each with id, title and "when", at most 6 lines
and 1200 characters, and one sentence: if one applies, read it with `athos show <id>` and follow it; if none does,
ignore the list. The model opens what it needs, and that counts as using the piece (below). A wrong choice of the
router then costs a few lines instead of a page. An apply model, or one whose tier is unknown, still gets the pieces
themselves, since it follows better than it picks. Nothing chosen means nothing added, on either tier. The route event
says which delivery was used (`delivery`: index or piece) and measures both (`index_chars`, `piece_chars`).
`athos bench route --replay <file> --tier frontier|apply` replays a session as to either tier (both by default).

On the bench, "loaded" is the router's choice under either delivery: the pieces an apply model is given, and the
first lines of the index a frontier model is offered. hit@1 is therefore the same for both, and says whether the
right piece is at the top of the index on frontier; what changes is the size. Measured on 2026-11-15 on the public
cases (starters en+es, requests that loaded something): pieces mean 3336 and max 6823 characters, index mean 1013 and
max 1075.

**Reading a piece writes nothing.** `athos show <id>` prints a piece and leaves everything as it was: no session, no
event, not the piece's last-used date, so you (or an agent checking your rules) can read any piece without it counting
as used. When the agent runs `athos show` inside a session, the tool hook sees the command and counts the piece as used
for that task (`piece_opened` event; the piece joins the task's pieces and is credited after the routed ones for an
edit); a piece's file read straight from the store is drawn on the trail but not counted. `athos show --use <id>`
counts it from the command line, in the session of the folder you run it in.

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
starters, but on the 300-page store it adds four wrong loads, so it stays opt-in.

### The audit log: what Athos decided, for an agent to check

Every decision the hooks make is written down on your machine, next to the task log (`~/.athos/events.jsonl`), and none
of it keeps a request's words: only its length and a 12-character fingerprint (`request_chars`, `request_sha`).

| event | written when | fields |
|---|---|---|
| `route` | every request the prompt hook sees, loaded or not | `task_id`, `model`, `tier`, `work_mode`, `collaborates` (an apply model always; a frontier one when a piece loaded), `mode` (the loading mode), `project`, `scope_reason`, `named_projects` (empty in a public repository), `named_count` (in a public repository: how many other projects the request named), `named_how` (how each mentioned project was decided: cue, distinctive, offered, rejected; not in a public repository, where `named_how_count` counts them), `offered_projects` (projects with a common-word name offered in one index line to a frontier model), `marker` (a `.athos.toml` applied), `public`, `private_held` (private pieces kept out, counted), `store_pieces`, `in_scope`, `request_chars`, `request_sha` (not in a public repository), `request_kind` (person, harness, empty), `wrapper`, `candidates` (up to 5: `piece`, `score`, `shared` (how many words it shares with the request, never which), `head_share`, `request_share`, `projects` (in a public repository only this project, never another's name), `kept`, `reason`), `scored`, `chosen`, `handed_over` (pages a chosen page's `**Calls:**` or `**If:**` brought along; only pages in this request's scope, the same ones the router could choose), `meaning`, `thresholds`, `cut` (pages cut to fit), `left_out` (pages with no room), `steps_only` (pages given as their steps' When, Do and Check only, whole), `delivery` (piece: the pages themselves, to an apply model; index: a list of the pieces in reach, to a frontier model; null when nothing was chosen), `offered` (the ids the index listed), `piece_chars` and `index_chars` (what each delivery costs, measured either way), `injected_chars` (the router's own text), `injected_total` (everything the prompt hook handed the model: the router's text plus an edit notice, a share request or a rating added after it), `injected_parts` (the characters of each: `pieces`, `connectors`, `offer`, `edit`, `share`, `rating`), `ms` |
| `edit_seen` | the edit detector keeps a file the agent wrote, sees the agent change it again, or finds a change on the next request | `task_id`, `file_sha` (a hash of the path), `decision` (snapshot, rebased (the agent changed it: the copy moves on), pending (the person changed it between two tool calls; told on the next request), attributed, unattributed (a change with no evidence: given to nobody)), `source` (agent_tool, agent_shell, outside, unexplained), `basis` (the evidence for the decision: `changed_during:<tool>`, `no_timing:<tool>`, `tool_failed`, `changed_between_tool_calls`, `changed_after_turn_end`, `no_tool_call_since`, or why there is none: `no_turn_end`, `changed_before_turn_end`, `tool_after_turn_end`, `background_task_running`), `attributed_to` (agent, person, or null), and for a change given to the person `detector` (between_tool_calls, after_turn_end), `piece` (not in a public repository), `piece_basis` (current_step, route_best, none) |
| `model` | a session starts, every request, and the end of a task whose replies could be read | `task_id`, `model`, `source` (event: the hook said so; transcript_switch: a `/model` switch newer than the latest reply; transcript_reply: the latest reply, since this request's own reply does not exist yet; session: what the session reported, when reported later than both, or last knew; replies: the replies that answered the task; unknown), `seen_in_transcript` (the model of the transcript's latest reply), `stage` (session_start, prompt, end), `changed`, `tier` (frontier, apply), `work_mode` (learn, collaborate), and at the end `answered` (the models whose replies answered the task) and `at_start` |
| `trigger` | a special path matches: save, adjust, gallery, share | `task_id`, `trigger`, `from_person` (true; false for a harness wrapper such as a subagent's message, anywhere in the text and in any case, also one that opens with another wrapper, or when the transcript says the harness sent it; a save or adjust whose text opens with its own words ("Athos · save:") is the person's even when it mentions a wrapper tag, unless a whole wrapped element (the tag and its closing tag) came with it; null when the text opens with another tag or the transcript has no entry for it yet), `acted` (it acts only when `from_person` is true), `wrapper`, `origin_signal` (which signal decided: `heuristic`, `both`, `disagree`, `missing:verify` (acted on the text, checked later), `missing` (`origin_check` strict: held back), `missing:heuristic`), `transcript_origin` (person, harness, or null), `verified` (null while a check is pending); the check itself is another `trigger` event with `stage` verify, `verified` (true, false, or null when the turn ended with no entry), `hook` (tool, stop), `undone` (offer_restored, edit_offer_restored, model_told) and `saved_meanwhile`, `project`, `request_chars`, `request_sha`, `injected_total` (what the path handed the model: save, adjust and gallery; a share request is counted in its route event) |
| `context` | a session starts | `hook` (session_start), `project`, `injected_total` (everything the hook handed the model), `injected_parts` (`index`, `journal`, `guide`, `offer`, `audit_hint`, `review`), `index_cap` |
| `piece_opened` | the tool hook sees the agent run `athos show <id>` | `task_id`, `piece`, `projects` (in a public repository only this project, never another's name), `via` (show), `offered` (the frontier index of this request listed it), `again` (it was already in use for the task), `project` |
| `hook_error` | a hook swallows an exception so your session carries on | `hook`, `where`, `error` (the exception's kind), `line` (file and line inside Athos), never its message; what the hook prints on stderr is the same kind and place, never the message either (it may quote a request or a path) |
| `learn` | autonomous learning decides about a task: it asks the model to keep what it taught, saves, or skips (every decision, with its reason) | `task_id`, `decision` (asked, saved, skipped), `reason` (strong_evidence, no_strong_evidence, last_verification_failed, correction_after_success, apply_model, model_unknown, private_data, no_project, off, invalid, model_saved_nothing), `model`, `tier`, `work_mode`, `mode` (learn, apply, unknown), `project`, `strong`, `weak`, `positive`, `negative` (the task's evidence counted), `evidence` (its short summary), `grounds`, and for a save `piece`, `version`, `risk`, `checks` (runnable Check lines), `confidence`; for a private-data refusal `private` (the kinds found, never the text) |
| `ui` | reserved for the panel's state | not written yet |
| `memory_cycle` | each phase of a dream cycle (see "Long-term memory") | `run_id`, `phase`, `duration_ms`, the phase's counts, for the model pass `wrote` |

Every one of them also carries `at`, `session_id` and `v`, the version of Athos that wrote it. `candidates.reason`
says why a piece did or didn't load: `chosen`, `runner_up_too_weak`, `over_budget`, `beyond_top_k`, `below_min_score`,
`prefixes_only`, `head_share_low`, `request_share_low`, `no_head_match`, `dismissed` or `meaning`; `scope_reason` is the
saved mode (`all`, `project`, `pieces`, `none`) or, in `auto`, `auto:project`, `auto:project+named`,
`auto:no-own-pieces` (a project with no pages of its own: the profile only), `auto:no-own-pieces+named` or
`auto:no-folder`. Events written by 0.1.110 may say `auto:project-without-pieces`: such a folder then saw every page.

**Who wrote a request.** Save, adjust, gallery and share act only on text the person wrote. Two signals decide: the
wrappers the harness puts around its own text (a subagent's report, a notification), and, when the hook gives a
transcript path, the transcript's entry for that prompt (`promptId`, or, without one, the same text; `origin.kind`
human, or Athos's own button pressed by the person, is the person). When both are there they must agree. Claude Code
writes that entry only after the prompt hook has run, so at prompt time it is usually missing: then the path acts on
the wrappers alone and the entry is checked at the next tool hook, or at the end of the turn (since 0.1.120; in 0.1.112
to 0.1.119 a missing entry meant the path did not act, so [Save] and a typed `Athos · adjust` never acted in Claude
Code). If the entry says the harness wrote it, Athos undoes what it can: the [Save] offer comes back, the edit the band
offered comes back, and, at a tool hook, the model is told to drop the instruction; a save that already happened is
counted, not undone (`athos revert` puts a piece back). The `trigger` event of that check has `stage` verify,
`verified` false and what was undone, and `athos audit` flags it. `"origin_check"` in `~/.athos/config.json` picks
another way: `"strict"` does not act while the entry is missing, `"heuristic"` acts on the wrappers and never checks.
Agents that give no transcript path (Codex, Muse Code, OpenCode) are judged by the wrappers, as before.

`~/.athos/log.md` says the same in one line per operation, for a person or an agent to read with grep and tail:

```
grep '^## \[' ~/.athos/log.md | tail
## [2026-11-15 09:21] route | my-app | loaded release-checklist · 1853 chars · scope auto:project
## [2026-11-15 09:24] route | my-app | none · scope auto:project
## [2026-11-15 09:30] trigger | my-app | share · harness text <agent-message> (heuristic) · ignored
```

Times are UTC. It names a piece only when the piece belongs to that project, or to none and is not private (another
project's are only counted), and it is moved to `log.1.md` once it passes 256 KB (under a lock, so two hooks never rotate it twice), so at most two files are kept. Each session starts with
one hidden line telling the agent where the log is and that `athos audit --session <id>` summarizes it.

`athos audit [--session <id> | --project <name> | --last N] [--show] [--json]` folds the log by session (by default
the session of the folder you run it in) and checks each one against these rules:

| rule | flags |
|---|---|
| `other_project_load` | a piece of another project loaded (chosen, handed over to by a loaded page, or opened by the model) or offered in a frontier model's index, without the request naming that project; a profile piece is never another project's, whatever its tags |
| `load_without_own_pieces` | a piece loaded in a project that has no pieces of its own (since 0.1.111 such a project sees the profile, so only a piece of another project it didn't name is flagged) |
| `edit_without_basis` | an edit given to the person with no evidence that the person made it |
| `model_inconsistent` | a request recorded under a model other than the one whose replies answered it (a `/model` switch recorded on the requests after it is not flagged); for sessions before 0.1.113, the session's models disagree with themselves or with Claude Code's transcript |
| `injected_over_cap` | more characters handed the model with one request than the router's cap: since 0.1.114 everything the prompt hook adds (`injected_total`), not only the router's text, so an edit notice, a share request or a rating on top of a page counts; older route events are judged on `injected_chars` and the rule says partial |
| `trigger_not_from_person` | save, adjust, gallery or share fired on text the person didn't write (a path that held back, `acted` false, is not flagged), or acted on text that read as the person's and the transcript then gave to the harness (flagged even when undone) |
| `version_mismatch` | the session's events written by two versions, or Claude Code's plugin and the `athos` on your PATH differ now. Each finding says what it costs: an older Athos that rewrites a piece drops the frontmatter lines it does not know (`visibility`, `status`, `risk`, `confidence`, `evidence`), so a private piece becomes visible again; nothing on the older side can prevent it. |
| `private_piece_named` | a private page (today's `visibility`; in a repository marked public, every page that may not load there) chosen, handed over to, offered or ranked in a route event of a session outside its projects, or named, as a whole id, in this project's `log.md` lines written while the session ran; with no route events for the session it says `not_evaluated` (nothing was checked), and a clean result covers only what Athos wrote, not the agent's replies |
| `weak_evidence_learning` | a piece saved by autonomous learning with no strong item of evidence (an exit status or an artifact the hooks saw): only the model's opinion |
| `save_in_apply_mode` | a piece saved on an apply model: an autonomous save on a model that is not frontier, or, in sessions written by 0.1.124 or later, a task answered by an apply model that saved a piece (older sessions: only autonomous saves are judged, partial) |
| `promotion_without_verifier` | a piece of the session's project moved to verified with no earlier passing verdict of the independent verifier whose prompt carried paths only |
| `verifier_saw_summary` | a verifier run of the session's project whose recorded `paths_only` is false, whose inputs were not exactly the four files, or whose kept `prompt.txt` is not the fixed text with the four paths |
| `verifier_over_cap` | a UTC day whose model runs (verifier and replay, every project) went over the runs or the cost cap they recorded (a run with no reported cost counts its estimate) |
| `marker_name_ignored` | the repository the audit runs in has a `.athos.toml` whose `name` is not the folder's own and was never accepted on this machine (`athos public name`), so Athos uses the folder's name |
| `public_not_declared` | the repository the audit runs in (when it is the session's project) is pushed to a code-hosting site, read from its local git configuration, and its `.athos.toml` does not say whether it is public; `athos public` or `athos public off` answers it |
| `memory_rollup_mismatch` | the ledger or the rollups the hooks read differ from a fold of the whole archive and the live log (`athos memory rebuild` makes them again) |
| `memory_archive_integrity` | an archived segment is missing, unreadable, or not the bytes and sha256 its manifest recorded (an offline command still reads it as it is, and says so) |
| `memory_wrote_legacy` | the dream cycle reported writing into a piece with no status, or such a piece has a version written by the dream (`athos-dream` in its history) |
| `memory_model_over_cap` | a model pass of the dream cycle settled without a reservation before it, or on a day over the cap shared with the verifier |

Each rule says how it was judged: flagged, clean, partial (checked with older data, which is not a proof) or not
evaluated (with what is missing). Sessions recorded before these events are checked as far as their task lines allow:
the pieces each task used and the first 120 characters of its request, the pieces as they are tagged today, and, for
the model, the replies in Claude Code's transcript when it is still on your machine. It only reads; requests are never
shown, and another project's pieces are named only with `--show`.

### Which model answered, and model tiers

The model is resolved for every request, not once per session: the hook's own field when the agent sends one (Codex);
else Claude Code's transcript, where a `/model` switch newer than the latest reply means the new model answers (only
the output Claude Code writes right after a `/model` command counts, never the same words in your own message), and
otherwise the latest reply's model keeps answering (the request's own reply is not written yet); the model the session
reported at its start wins when it was reported later than both (a session resumed on another model). When the task
ends, the replies that answered it settle the model: the `task_end` records it, with `model_at_start` when the two
differ, and the next request starts from it. `athos status --json` has `model` (`id`, `source`, `tier`, `work_mode`,
`collaborates`).

Each model has a tier. **frontier** models may learn new ways of working (mode `learn`); **apply** models use what is
already known (mode `collaborate`), and a frontier session also collaborates when a piece loaded for the request. A
model no pattern matches counts as apply. Since 0.1.116 the tier decides how the router's choice is delivered (see
"Pull instead of push" below), and since 0.1.124 what is saved: only a frontier model learns (see "Autonomous learning"), and on an apply model `athos save` refuses and no save is ever offered or asked for.

```
athos tiers [--json]                              the patterns of each tier
athos tiers add frontier|apply <pattern>...       e.g. 'local-big-*', or an exact id, which wins over any pattern
athos tiers remove frontier|apply <pattern>...
athos tiers reset                                 back to the defaults
athos tiers which <model>...                      the tier and mode of a model id
```

Defaults: frontier `claude-fable-*`, `claude-mythos-*`, `claude-opus-*`; apply `claude-sonnet-*`, `claude-haiku-*`.
They are kept in `~/.athos/config.json` under `tiers`, matched without regard to case and to a context-size suffix
such as `[1m]`.

### Learning from your own edits

When the agent writes or edits a text file while following one of your pieces (a contract review, a report, code) and
you then change that file by hand, your change is usually a rule of how you work. Athos keeps a copy of each file as
the agent left it (`~/.athos/snapshots/<session>/`, text files up to 200 KB, only the last three tasks of the session),
also of the files a shell command of the agent names inside the project.

A change counts as yours only on evidence that no tool call of the agent made it, and in doubt it is given to nobody.
The agent changes files in many ways besides its edit tools (a script, `sed -i`, a formatter, `git checkout`, a build
step, another plugin's hook, a subagent, a task it left running in the background); until 0.1.111 each of them was
taken for your edit. Now:

- the start of each tool call is stamped by a PreToolUse hook (the hook's own clock, not an estimate). After every tool
  call of the agent (in Claude Code also a failed one, `PostToolUseFailure`) each kept file is checked, with a `stat`
  first and its content only when that moved. A change that could have happened during the call is the agent's, and
  the copy moves to it. A change is yours only when its time (the file's ctime, which no tool can set back) falls
  before the call's stamped start by more than a second, more than 15 seconds after the previous tool call ended (a
  formatter another plugin runs after a write), and while no other tool call, no subagent and no background task was
  running;
- on your next request, a change is yours only when it came more than 15 seconds after the agent's turn ended (another
  Stop hook may still be writing), with no tool call since or still open, no background task left running, and no
  other agent session working in the same project since;
- anything else is given to nobody: no start stamp, a subagent's call (Claude Code's `agent_id`), a call or task still
  running, a change inside a grace window, a ctime in the future (a network file system's clock). The `edit_seen` event
  says `agent_shell`, `agent_tool` or `unexplained` with the reason, and the agent is told nothing.

A change of yours is credited to the step the agent was on when it wrote the file, else to the best-ranked piece the
request loaded, else to no piece (and then the agent is not told). The agent gets a short diff and is asked to propose
the rule in one line, in your language, and to ask you before adding it. Say yes and it improves the piece the same way
[Adjust] does; a typo or spacing change is not mentioned. Each edit is offered once and its copy is deleted right after;
`athos status --json` shows it as `learned_from_edit` (file, piece, step and the `Athos · adjust <piece>#<step>:` text a
panel can prefill). The panels offer it as a button, **Keep this rule** (Claude Code's pane, the Desktop panel,
OpenCode's palette: *Athos: keep the rule from my edit*); in Codex and Muse Code, `athos watch --trail` shows the edit
and a plain "yes" to the agent keeps it. The `learned_from_edit` event keeps the file's path, the piece and its title,
and the evidence (`basis`); in a repository marked public (`.athos.toml`) it keeps only hashes of the path, the piece
and the step. It works in Claude Code, Codex (`apply_patch`), Muse Code and OpenCode, stays on your machine, and is
off with `ATHOS_CAPTURE=off`.

What it cannot see: a process the agent left running that writes after the turn and after the grace window, when the
agent's Stop hook reports no background task (Claude Code's `background_tasks`), is taken for you; a change made while
the agent writes its last answer (after its last tool call) is given to nobody; a hand edit followed by the agent's own
edit tool on the same file, with no other tool call between, is folded into the agent's write; a hand edit within 15
seconds of a tool call or of the end of a turn is given to nobody; agents with no PreToolUse hook (Codex, OpenCode)
only have the after-the-turn evidence. Checking the kept files costs well under a millisecond per tool call with twenty
files kept; the PreToolUse stamp is one small file write.

### Autonomous learning: candidates, checks and a verifier

On a frontier model Athos can learn on its own, and only a piece proven by objective evidence reaches an apply model.

**Status and provenance.** A page's frontmatter may carry, after `visibility`, each line only when set:

| field | values |
|---|---|
| `status` | `candidate` (learned, not proven yet), `verified` (proven: see below), `retired` (superseded after repeated failures; never loads) |
| `risk` | `normal` or `high` (its steps publish, merge, deploy, delete, force-push or touch production) |
| `confidence` | a number from 0 to 1 |
| `last_verified` | the date it was last proven |
| `learned_by` | the model that wrote it |
| `evidence` | a short inline list of `kind:detail` items, e.g. `[verify:unittest:ok, commit, task:3f9a1c2b7d10, verifier:pass]` |

A page with no `status` (every page written before 0.1.122, and any page you write yourself) is **legacy**: it loads,
is offered and is delivered exactly as a verified one. Its file is yours: Athos never rewrites it unless you ask for
a change to that page (`athos save` with its `id:`, `athos revert`, a curate or merge you apply). Using it, grading it,
ageing it and bookkeeping (confidence, evidence) leave it byte for byte as it is, comments and keys Athos does not know
included; what they would have recorded goes to the audit log (a `grade` event, from legacy to legacy, with what was
seen), the review marks (the next frontier model's index says it needs review) and, for its last use,
`~/.athos/last-used.json`. A learned page's file is not rewritten on use or grading either: its last use goes to
`last-used.json` and its confidence, last verification and evidence to `~/.athos/piece-meta.json`, and the file takes
them with its next status change or improvement. A status change is a new version, the outgoing one archived in
`.history` as for any improvement, so `athos revert <id>` brings it back; retiring supersedes a page and deletes nothing.

**Verified means verified for that text.** A change to a verified page's title, when or body, by anyone, makes it a
`candidate` again (its history says so), and a verifier's verdict counts only for the exact text it read. `athos
revert` to a version that was verified brings it back verified only when the verifier passed that very text;
otherwise it comes back a candidate.

**Check lines.** A statement may say how to tell that its step went right, next to When, Do, Because and Links:

```
## #run_tests
**When:** after changing the parser.
**Do:** run the unit tests.
**Check:** `python3 -m unittest discover -s tests` exits 0
```

A Check is a command in backticks, or a fact anyone can observe. An apply model runs the check instead of judging its
own work, and a candidate needs at least one runnable Check before it can be verified: a command in backticks that is
itself a verification (a test runner, a build, a linter, a type checker, as in the table below). A Check of `git status`
or `cat VERSION` only reads something: it is not runnable, and running it is no evidence. The
capture guide asks for one per step; a page given as its steps only, to fit the 8000-character cap, keeps each step's
Check with its When and Do.

**Evidence, gathered without asking.** During every task the hooks note what objectively happened, in
`~/.athos/evidence/<task>.jsonl` (the last 300 tasks), and keep the last 4000 characters of each verification
command's output beside it, for the verifier:

| item | written when | strength |
|---|---|---|
| `verify` | a verification command ends: a test runner (pytest, `python -m unittest`, `npm test`, `npm run test:*`, `go test`, `cargo test`, `make test`/`check`, jest, vitest, …), a build (`npm run build`, `cargo build`, `go build`, `tsc`, …), a linter (`ruff check`, eslint, flake8, `black --check`, …), a type checker (mypy, pyright, `tsc --noEmit`, `go vet`, `cargo check`), or the **Check** of a piece the task uses; with `ok`, `kind`, `label` and `check_of` | strong when the hook saw that command's own exit status |
| `commit` | `git commit` succeeded, owned the command's success, and moved HEAD from where the PreToolUse hook saw it (with its hash) | strong |
| `revert` | `git revert`, `git reset --hard`, `git checkout -- …` or `git restore` succeeded (not `git revert --abort` or `--quit`, `git reset --hard` onto `origin/…`, `upstream/…` or `@{u}`, nor `git restore --staged` alone) | strong, against the work |
| `person_edit` | the edit detector gave a change to you (see above): a correction | strong, against the work |
| `reaction` | your next words plainly judged the task (`ok`, `corrected`) | weak: read from words |
| `model_claim` | the model's own statement about its work | weak |

A command's exit status is its own only when it runs alone or in a chain joined by `&&`: `pytest | tail` reports
`tail`'s status and `pytest || true` always succeeds, so those count as weak. A failure counts as that command's only
when it is last and only setup (`cd`, `export`, `source`) or a `;` comes before it; a failed chain with a verification
in it whose failure cannot be pinned on one command (`pytest && npm run build`, `pytest 2>&1 | tail`) is a strong item
against the work all the same (`unattributed`), until a later verification passes. Strong is kept for commands that
really checked something: a run that only asks the runner about itself or lists what it would do (`--version`,
`--help`, `--collect-only`, `--no-run`, `make -n`), a linter told to fix (`--fix`, `lint:fix`), the tasks a gradle run
leaves out (`-x test`), a command sent to the background (its hook comes when it starts, so its status is not known),
anything after a `#` comment, and a test run whose output says no test ran (`Ran 0 tests`, `collected 0 items`, `[no
test files]`, `running 0 tests`, `No tests found`, `0 passing`) are not strong. A longer word is another command:
`pytest-watch` is not pytest and `make test-clean` is not `make test`. Up to 60 weak items are kept per task; strong
ones are never dropped. Claude Code runs PostToolUse after a command
that exited 0 and PostToolUseFailure after one that did not; agents whose tool hooks give no exit status (Codex, Muse
Code and OpenCode unless the event carries an exit code) only produce weak items. Subagents' commands and Athos's own
are left out, and in a repository marked public the command itself is not kept, only what kind it was. With
autonomous learning on (below), and always on an apply model, an edit of yours is only evidence: the agent is no longer
told about it and asked to propose a rule.

**Saving on its own, on a frontier model.** When a task on a frontier model ends with grounds to keep it (the same
rule that used to ask: an edit within three tool calls, five commands that changed something, or a checklist
followed, and nothing saved yet), Athos looks at its evidence. At least one strong item for the work (a verification
that passed, a commit), no failed verification as the last one, and no revert or edit of yours after the last success.

How the model hears it is `autolearn.ask` in `~/.athos/config.json`:

- `"guide"` (the default): nothing is said at the end of the task. The session guide (hidden, at session start, and
  again on the first request of a session whose model became a frontier one later) tells a frontier model once: before
  its final answer to a task whose work an objective check proved in this session, if the task taught something
  reusable, save it with `athos save --auto`; otherwise do nothing and don't mention Athos. The Stop hook only records
  the task as `qualified`.
- `"stop"`: the Stop hook also says one short line to the model when a task qualifies, which you also see (Claude Code
  shows it as "Stop hook feedback"; the square stays red while the model answers it):

```
Athos: if this task taught something reusable, keep it as one piece with Check lines (`athos save --auto`, as the session guide says); otherwise just stop.
```

The trade-off: the line arrives at the moment the task ends, with the evidence fresh, so a model acts on it more
reliably than on an instruction read at the start of a long session, which it may forget or weigh against your
request; but you read it after every qualifying task. With `guide`, check that saves still happen: `athos audit`
prints, per session, `learning on its own: N saved · M task(s) qualified without a save before the end · K ended with
nothing saved` (and how many qualified tasks ran without the session guide); qualified tasks that keep ending with
nothing saved, while saves stay at zero, mean the model is not acting on the guide, and `"ask": "stop"` brings the line
back.

The guide says how: one new piece, every step with a Check, no secrets, emails, links, folders of this computer or
other projects' names. `athos save --auto` then saves it without asking you, as a `candidate` of the current project only (`visibility: project`), with
`learned_by`, the evidence summary, `confidence: 0.3` and the risk the detector finds, after two checks: the task's
evidence must still qualify, and the private-data detector of `athos share` must find nothing (emails, phone and ID
numbers, links, folders of this computer, another project's name, your name); if it finds something the piece is not
saved and the model is told which kinds, never the text. It never changes your own pieces (no `status`) or a retired
one; a learned piece of this project it may improve, under the same checks, and the new version is a candidate with its
own verifier run (a verified piece improved this way is verified again from scratch). A candidate does not
reach an apply model until it is verified. Every decision is a `learn` event: qualified (`ask: guide`), asked (`ask:
stop`), saved, or skipped with its reason (no strong evidence, a failed last verification, private data, an apply
model, or the model stopping without saving).

**Who may save.** Every save or change of a piece is either yours or the model's, and in doubt it is the model's:

- **yours**: you pressed [Save] (or [Adjust], [Keep this rule]), or typed a request that opens with `Athos · save:` or
  `Athos · adjust`, and the who-wrote-the-prompt check reads it as your text (the text's own wrappers, and Claude
  Code's transcript entry for the prompt when it is there: should the transcript say the harness sent it, the
  permission is withdrawn). The `athos save` the model then runs in that task, from any folder of the project, is
  yours: it works on any model and stores a piece you own (no `status`), as before autonomous learning. It lasts until
  your next request (30 minutes at most). An `athos save` you run in your own terminal, where no agent runs it and no
  session works in that folder or above it, is yours too.
- **the model's**: anything else. A command an agent runs (Claude Code's shell sets `CLAUDECODE` and the session's id,
  `CLAUDE_CODE_SESSION_ID`, which also tells which session it is when two work in one folder), a command in a folder
  where a session worked in the last 30 minutes (or in a folder above it: a subfolder belongs to the project's
  session), a subagent's `athos save` (its model is not the session's), and every `athos_save` through `athos mcp`
  (an MCP server cannot tell who wrote the request).

A save the model starts, with or without `--auto`, goes through the autonomous pipeline above: on a frontier model it
gives a candidate, on strong evidence, after the private-data check, then the verifier; on an apply model, or one Athos
could not resolve, nothing is saved or changed at all, from any folder, through the CLI or MCP (`athos save`, `athos
revert`, `athos merge --apply`, `athos curate apply|restore`, `athos_save` and `athos_merge` with `apply`), and the
refusal says how you can save it yourself. No session found while an agent runs the command counts as a model Athos
could not resolve. In Claude Desktop's chat the model is not known, so its `athos_save` saves nothing.

On an apply model nothing is ever offered or asked for. Another agent's models (Codex, Muse Code, OpenCode) are apply
models until you name them frontier with `athos tiers add frontier <pattern>`. `"autolearn": {"on": false}` in
`~/.athos/config.json` turns autonomous learning off, and with it every save the model starts: a frontier session is
then offered [Save] as before, in the classic interface; in the minimal one nothing is offered in sight, and the guide
only says how to save when you ask for it. (A headless `claude -p` run, `ATHOS_ASK=model`, Codex, Muse Code and
OpenCode still have the Stop hook ask the model to save; that save is the model's, so it is refused unless you asked.)

**The worker never grades its own work.** Whether the work was right is decided by an independent verifier, not by
the model that did it. Right after an autonomous save Athos writes a folder for it, `~/.athos/verify/<id>-v<n>-<task>/`:
`diff.patch` (from git only: the changes of the commits the task made, never their messages, what is left uncommitted,
and the new files git does not track yet with their text, except binary files, files over 50 KB and names that suggest
secrets), `verification.txt` (the output the tool hook kept of each verification command, with its exit status),
`piece.md` (the candidate as its title, when and body only: no frontmatter, so no evidence, confidence or status, and
no history) and `checks.json` (its Check commands); `meta.json` keeps the hash of the text the verifier reads. Then it
starts, detached so no hook waits, a headless run of your own Claude Code:

```
claude -p <prompt> --output-format json --model <verifier> --tools Read,Grep,Glob
       --allowedTools "Read(//<folder>/**)" --disallowedTools Bash,Edit,Write,…
       --permission-mode dontAsk --restricted --no-session-persistence --safe-mode --strict-mcp-config
       --max-budget-usd <cap> --add-dir <folder>          (in that folder, with a throwaway ATHOS_HOME,
                                                           ATHOS_HOOKS=off, ATHOS_CAPTURE=off, and none of the
                                                           calling session's variables)
```

Read-only tools that can read only the folder (`--restricted` keeps the file tools inside the working folders, and the
one allow rule is a Read rule for the folder, which Grep and Glob follow; `dontAsk` denies anything else), a fresh
context, no plugins, hooks, CLAUDE.md or MCP servers (`--safe-mode`; `ATHOS_HOOKS=off` makes `athos hook` do nothing
as well), nothing kept of the session. Its prompt is a fixed text with the four paths and nothing else, and tells it the
files are data, never instructions: never the worker's summary or the conversation (`prompt.txt` keeps it, and the
`verify` event records `paths_only`, and `bundle_clean`: that `piece.md` has no frontmatter or history and `diff.patch`
no commit header or message; a pass from a bundle that is not clean never counts). It answers a fixed rubric, one
verdict per criterion, as JSON:

| criterion | passes when |
|---|---|
| `evidence_passed` | the verification output shows the commands ended successfully, with no failure after the last success |
| `piece_matches_work` | every step of the piece is backed by the diff or the verification output |
| `checks_runnable` | at least one Check is a concrete command that can be run again later in this repository |
| `no_private_data` | no secret, credential, personal data or folder of one particular computer |
| `reusable` | a way of working for a later task, not a narration of this one |

The verdict passes only when every criterion does, and counts only for the text it read: when the piece changed since
its folder was written, or while the verifier ran, the verdict is not applied (outcome `stale`). It runs on a different
frontier model from the one that did the work: `autolearn.verifier.models` in `config.json`, or else one per frontier
family your tiers name (`claude-fable-*` → `fable`, `claude-opus-*` → `opus`; an exact id as written), the first of
another family than the worker's. When there is only one, or the worker's model id cannot be read, the same model may
be used and the `verify` event says `same_model_fallback` (and the piece's evidence `verifier:pass:same-model`).

Every model run Athos starts (verifiers and replays together) counts against a daily cap: `autolearn.budget` with
`runs_per_day` (default 6) and `usd_per_day` (default US$1.00); each run is also capped at
`autolearn.verifier.max_usd_per_run` (US$0.50) or what is left of the day, whichever is less, and stopped after
`autolearn.verifier.timeout_s` (300 s). The caps are hard: before a run starts its cap is reserved, under a lock, in
`~/.athos/autolearn/runs.json`, and settled afterwards with what the run reported spending; a run that reported nothing
(a timeout, a verifier that was killed) counts its whole reservation. A run that never started (no `claude` on PATH,
not logged in, a model the account cannot use) costs nothing and uses no attempt, and an unavailable model is retried
once with the worker's own model. Only one verifier runs at a time (its lock is taken in one step). A cap of 0 turns
model runs off, and `"verifier": {"on": false}` turns the verifier off. A run refused by the cap, failed or timed out
leaves the piece a candidate and says why (`grade` and `learn` events); a candidate still waiting is picked up at a
later end of turn, at most two attempts. Bundles are pruned to the last 50 at the end of a turn, except those still
waiting. `athos verify <id>` runs it by hand, in the foreground; `athos verify --pending` the oldest waiting one.

| event | written when | fields |
|---|---|---|
| `verify` | a verifier run ends, or is refused | `piece`, `version`, `task_id`, `outcome` (pass, fail, error, skipped, stale), `model`, `worker_model`, `same_model_fallback`, `verdict` (per criterion, true or false), `why` (one line per criterion), `error`, `cost_usd`, `bundle`, `inputs` (the file names it was given), `prompt_file`, `paths_only`, `bundle_clean`, `attempts`, `body_sha` (the text it read) |
| `model_run` | before a model run starts (`phase` reserved, with `usd_reserved`), when it ends (`phase` settled), or when the cap refuses it (`phase` refused); a run with a reservation and no settled event (killed) counts its whole reservation | `phase`, `purpose` (verify, replay), `piece`, `version`, `model`, `run_id`, `started` (false for one that never started), `refused` (why), `ok`, `error`, `cost_usd`, `cost_estimated`, `cost_counted` (what the day's budget counts for it), `usd_cap_run`, `usd_per_day`, `runs_per_day`, `duration_s` |

**Promotion and demotion.** Each move is a `grade` event with its basis, and so is a decision not to move:

- **candidate → verified** when the verifier passed on the piece as it is now (its title, when and body; `body_sha`
  in the `verify` event), it has at least one runnable Check, and since it became a candidate either **two clean
  reuses on a frontier model** or **one pass on an apply model** (a replay, below, or a real use whose Checks the hooks
  saw pass). A `risk: high` piece needs the verifier and at least one clean reuse; a replay alone does not verify it.
  Reuses alone, without the verifier, never verify anything.
- **verified → candidate** after a reuse that was corrected or failed, which takes strong evidence tied to that piece:
  a change you made credited to it, or one of its own Checks failing last. A legacy piece never moves: on such evidence
  it is marked for review instead, and a `grade` event says what was seen. Weak signals never change a status: a
  reaction read from your words only lowers confidence (−0.1) and keeps that reuse from counting as clean.
- **→ retired** when 3 of its last 5 judged reuses were corrected or failed, counted from its last status change,
  revert or improvement (each is a new version, and the count starts again), so a piece brought back with `athos
  revert` is not retired again by its next reuse (a legacy piece is marked for review instead). Retiring supersedes it
  as a new version; `athos revert` restores it.
- **ageing, without a model**: a verified piece with no use and no re-verification in `autolearn.age_days` (90) days
  goes back to candidate, checked when a session starts. Using a piece moves its last-used date, so use slows ageing.
  Legacy pieces do not age.

A reuse is judged when your next request arrives, once your reaction and your edits are known: a `reuse` event per piece
the task used (opened, on a frontier model; given, on an apply model), never in the session that saved or improved
it. A message the harness sends in the middle of the work (a background task's `<task-notification>`, a subagent's
report: text in one of the harness's wrappers) does not start a task: the open task goes on (a `task_continued`
event), so one piece of work is judged once. On a frontier model it is **clean** when the task's evidence has a strong item for the work and nothing against
it, **corrected** on strong evidence tied to the piece (an edit of yours credited to it, one of its Checks failing
last), and **unverified** (not counted) when nothing proved the work, when something was against the work without
naming this piece (a revert, an edit of yours credited to another piece or to none, a failed verification that is not
one of its Checks), or when your words read as a correction. On an apply model it is **clean** only when at least one
of its Checks was seen passing and none failing last, **failed** on the same tied evidence, and unverified otherwise. A failure on an apply model also marks the piece for review:
the next frontier model's index says so.

Confidence (0 to 1) starts at 0.3, moves +0.2 on a verifier pass, −0.1 on a fail, +0.1 per clean reuse, −0.2 per
corrected or failed one, −0.1 when the environment check below finds something missing, is at least 0.7 once verified
and 0.05 once retired. It multiplies the router's score by 1 + 0.2 × (confidence − 0.7), from 0.92 to 1.06: the words
decide and confidence only breaks near ties. A legacy piece has no confidence, its factor is exactly 1, and its file is
never given one. `athos bench route` gives the same hit@1, wrong loads and "none ok" as before.

**Checking an old piece against the environment.** Before a frontier model's index lists a piece not created or
verified in `autolearn.reverify_days` (14) days, Athos checks once per session, without running anything, that what it
names is still there: files in backticks relative to the repository, the commands its command lines start with (on
PATH), its `npm run` scripts (in package.json) and its `make` targets (in the Makefile). Flags of other commands cannot be
checked this way and are not. What is missing goes in the index line (`may be stale: 1 named file(s) not found here`), a
`reverify` event, and, for a learned piece, a lower confidence. A frontier model's index also says `candidate, not
verified yet` for a candidate and `needs review: it failed on an apply model` after such a failure.

**On an apply model.** Only verified and legacy pieces load, and never a retired one;
`"autolearn": {"apply_candidates": true}` also lets its own project's candidates load. A learned piece comes as a short
checklist: each step's When and Do, its Check and hand-overs, without reasons, links or history, under "Steps, in order.
After each one, run its Check and go on only when it holds; if a Check fails, stop and say which one failed." Any piece's
risky steps, legacy ones too, get a line after their Do: `**Ask first:** this step publishes: ask the person and do it
only on their clear yes.` (a frontier model reads pages as written). The apply model never saves or changes a piece:
what the hooks saw (its Checks passing or failing, your corrections) is the evidence.

**Replaying a candidate on an apply model**, off by default because it costs two model runs: with
`"autolearn": {"replay": {"on": true, "model": "haiku"}}`, an autonomous save also keeps the task as the candidate's case
(the request and the frontier answer, `mark: frontier`, never in a public repository), and once the verifier passes, the
apply model answers that request with the piece as its know-how and a frontier model judges it against the frontier
answer, as `athos shadow` does. A pass is a `reuse` event (tier apply, `replay_pass`) that can verify a normal-risk
piece. Both runs count against the same daily cap.

| event | written when | fields |
|---|---|---|
| `grade` | a piece moves, or a verifier outcome or a rule leaves it where it is | `piece`, `version`, `from`, `to` (candidate, verified, retired, legacy), `basis`, and for a move `trigger`, `verifier_pass`, `verifier_model`, `frontier_clean`, `apply_pass`, `risk`, `checks` |
| `reuse` | the next request after a task that used a piece, or a replay | `piece`, `version`, `task_id`, `tier` (frontier, apply), `model`, `outcome` (clean, corrected, failed, unverified, replay_pass, replay_fail), `basis` (strong_positive, no_correction, check_passed, check_failed, person_edit, person_edit_not_this_piece, revert, last_verification_failed, reaction_corrected, no_check_ran, nothing_proved_the_work, replay, score), `status` |
| `reverify` | an old piece is checked against the environment | `piece`, `version`, `age_days`, `checked`, `missing` (files, commands, scripts, targets: counts), `stale` |

**Repairing polluted statistics.** Sessions recorded before 0.1.111 counted pieces of other projects as used (a
project with no pieces of its own then saw every piece), and before 0.1.112 the edit detector gave the agent's own
edits to you. Those lines stay as they were; `athos repair --session <id>` appends `correction` events instead, and the
statistics (`athos report`, the bars, curating, grading) stop counting what they name:

```
athos repair --session <id> [--pieces mistaken|foreign|all|none] [--apply] [--show] [--json]
```

It corrects the session's `learned_from_edit` events with no evidence (no `basis`), and the task uses of pieces that
were only injected: other projects' pieces, and, when the session's project has no pieces of its own, every piece
(`--pieces mistaken`, the default; `foreign` keeps general pieces; `all`; `none` touches no use). A piece the model
opened itself (`piece_opened`) stays a use. It is a dry run unless `--apply`; running it again writes nothing new. The
`correction` event has `target` (learned_from_edit, task_pieces), `task_id`, `piece`, `original_at` and `reason`
(no_evidence_the_person_edited, another_project, project_without_own_pieces, asked_all); `athos audit` still lists the
old edits, marked `corrected`.

**Risk lanes.** A step is high risk when its When or Do publishes (`npm publish`, `git push`, `docker push`, `gh
release create`, the word publish), merges (`gh pr merge`, `git merge`, merge), deploys (deploy, `kubectl apply`,
`terraform apply|destroy`, `helm install|upgrade`, `vercel --prod`), deletes (`rm -r`, `rm -f`, delete, `DROP TABLE`,
`git branch -D`, `git clean -f`), force-pushes (`--force`, `-f`, `--force-with-lease`) or touches production (prod,
production), in English or Spanish. The detector is conservative on purpose: in doubt a step is high risk, which only
makes promotion stricter and, on an apply model, asks you before the step runs. A piece with any such step is saved
with `risk: high`.

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
followed a checklist Athos asks once whether to save or improve a piece (the model's save is refused unless you asked
with `Athos · save:`: see "Who may save"). `athos watch` and `/athos:report` show Muse Code beside Claude
Code and Codex. Keep Muse Code's Contributor mode off (`muse` → `/settings`) unless you want Meta to train on your
sessions; Athos warns when a task ran with it.

Without the plugin, `athos export --muse` writes your profile as skills in `~/.agents/skills` (that folder is read in
every project; `athos project sync` gives a project its own pieces) and `athos import muse` records past tasks from
Muse's session logs.

### In OpenCode

Athos is an OpenCode plugin. Install it once:

```
athos opencode install       writes ~/.config/opencode/plugins/athos.js (it runs ~/.athos/bin/athos, the newest installed Athos); restart OpenCode
```

With any model OpenCode runs, the pieces that match each message go into its system prompt, every task is recorded
with OpenCode's own token counts, and, in the classic interface, after a turn that changed something or followed a
checklist Athos asks once whether to save or improve a piece, and a toast follows the steps; in the minimal one
(the default) neither. `athos opencode uninstall` removes it.

### In Claude Desktop

In the **Code** tab, Claude Desktop runs Claude Code with the same settings, so the plugin works as it is, including
the trail pane beside the transcript. For the regular **chat**, which takes MCP servers but not plugins, install Athos
as a Desktop extension: `athos desktop` builds `dist/athos.mcpb`; double-click it (or drag it into Settings →
Extensions). It runs `athos mcp` against your own `~/.athos`.

In the chat, Athos finds the know-how for each request (`athos_find`) and, in the classic interface (`"ui": "classic"`
in `~/.athos/config.json`), opens its **trail panel** in the conversation (MCP Apps); in the minimal one (the default)
the panel does not open on its own. The panel: a greeting, the piece the task walks with each step ✓ done, ▶ now and ○ ahead as the model
reports it (`athos_step`), the steps your know-how lacks, and two buttons: **Change this step** (you write how the step
changes; the piece is improved) and **Save as a way of working**. **Keep beside** pins the panel where the host allows it. In a
chat without MCP Apps, the same tools answer as text. The chat's model is not known to Athos and an MCP server cannot
tell who wrote a request, so the model's `athos_save` (and `athos_merge` with `apply`) saves and changes nothing there
(see "Who may save").

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
  on call, something else) in your language. A click adds that profession's example ways of working,
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

Which Athos each agent would run, and which are behind the newest one released or installed (the newest version the
marketplaces on this computer last fetched, or the newest an agent runs; never the copy running the command, which
may be a checkout ahead of the release): Claude Code (its plugin
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
In a repository marked public it writes only the pages that may load there (this project's own and the profile pages
you allowed in public), whatever `--all` or `--piece` asked.

**Trajectory subagents.** `athos wiki agents --install` writes the subagents that walk this project's trajectories
(its own pages and your profile, never another project's) into the repository's `.claude/agents` (or `--dir <folder>`),
keeps them out of git on this machine (`.git/info/exclude`) and rewrites them after each save. It refuses in a
repository marked public (the one it runs in, or the folder named with `--dir`), and they are never rewritten from
one or into one: a save made in a public repository leaves them alone, and so does any save once the repository they
were installed in is declared public. `athos wiki agents --uninstall [--dir <folder>]`
removes them and stops the rewriting. Before 0.1.121 they went to `~/.claude/agents`, which Claude Code reads in every
project, and walked the whole store, so their descriptions carried every project's page titles into every session; an
install made that way is no longer kept in step after a save until you install again.

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

### Your know-how as a fine-tuning dataset (Fireworks AI, OpenAI)

`athos export --dataset FILE` writes your statements and marked tasks as JSON lines. With `--format fireworks` it
writes them instead as the chat JSONL that Fireworks AI's supervised fine-tuning reads (and OpenAI's, which is the same
shape, so `--format openai` writes the same rows): one `{"messages": [system, user, assistant]}` per line. For each
piece, the user turn is a situation it is for (its **When**, and the request of every task you marked good that used
it) and the assistant turn is its statements in order (when, do, because). Tasks marked corrected or failed, and
unmarked ones, give no row. Every row is checked before the file is written (valid JSON, user and assistant turns
alternating and ending on the assistant, no empty message), and Athos prints how many rows it wrote and where:

```
athos export --dataset know-how.fireworks.jsonl --format fireworks
firectl dataset create my-know-how know-how.fireworks.jsonl
firectl sftj create --base-model <MODEL_ID> --dataset my-know-how --output-model my-know-how-model
```

Fireworks wants at least 3 rows (OpenAI at least 10; Athos warns below that) and cuts each example at the model's
context length (32,768 tokens by default). Older `firectl` builds spell the first command `firectl create dataset`.
To train without uploading a dataset, the Serverless Training starter in Fireworks' cookbook (`fw-ai/cookbook`,
`examples.sft.muse_glimmer_starter`, shown in the hackathon's Muse open models session) takes the same file with
`--file`. The file holds your requests as you typed them: nothing leaves this machine until you upload it.
