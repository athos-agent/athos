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
another project's pages load only when the request names that project ("…like we did in heat-v2"). A project with no
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

**In a public repository, everything else is private.** In a repository whose marker says `public = true`, only that
project's own pages load (and none of them marked private). Every other page is treated as private there, whatever its
`visibility`: it never loads and is never named, not in the session's index, a frontier request's index, `log.md`,
the journal, `athos list` or `athos show` run there, or anything the hooks add, even when the request names its
project, which elsewhere would bring it (the `route` event keeps only how many projects were named, `named_count`).
Profile pages are included in this: one loads in a public repository only once you allow it with `athos profile
allow-public <id>`; by default none does. You do not need to mark pages one by one: the per-page `visibility` field
stays available, and in a repository that is not marked public the usual rule holds.

**Declaring a repository public.** `athos public` writes `public = true` into the `.athos.toml` at the root of the
repository you run it in (creating it with the project's name when there is none, and keeping any other line); `athos
public off` writes `public = false`; `athos public status [--json]` says what is declared and which code-hosting sites
the repository is pushed to. Athos asks because it cannot know: whether a repository is public lives on the hosting
site, behind your account, and Athos makes no network call. Your local git configuration only says where the code is
pushed, not who can read it there. So `athos audit`, run in a repository that has a remote on a code-hosting site
(GitHub, GitLab, Bitbucket, Codeberg and the like) and no `public` line in its marker, reports `public_not_declared`
until you answer either way. Until then the repository is treated as not public.

In a public repository nothing taken from a request is kept either: the task log keeps the request's length but not
its first 120 characters, the audit events no fingerprint, the session no copy, and [Didn't apply] no words. The
`route` event says when a marker applied (`marker`, `public`).

Measured on one person's store (71 pages over ten projects, 252 tasks marked good; `athos bench route --from-store`):
a page of another project loaded for 14 tasks with one pool and for none with `auto`. Measured again on 2026-11-15
(91 pages, 343 tasks marked good), counting every task this time, also those of projects with no pages of their own
that the count used to skip: 2 tasks with the 0.1.110 scope, both in such projects, and none now.

### The journal: what happened lately in this project

Next to the ways of working (the long-term memory, which changes only when you save or approve), each session starts
with its project's recent past: the last tasks with what they used or saved and how they went, what was corrected or
failed in the last week, and the older tasks counted per way of working. `athos journal [--project <name>]` prints it.
It is read from the task log Athos already keeps on your machine; nothing new is stored, and another project's past
never shows up in this one.

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
  back as a new one (`athos revert <id> --to N` does the same; no version is ever deleted); and **Open in editor**,
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
the repository, since it holds real requests: `{"project": "<name>", "cwd": "<optional folder>", "cases":
[{"request": "...", "expect": []}]}`, `expect` being the piece ids it should load, none when empty) through the loading
mode and per-project scope the hooks apply, then `load.relevant`, and counts the requests where something loaded,
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
| `route` | every request the prompt hook sees, loaded or not | `task_id`, `model`, `tier`, `work_mode`, `collaborates` (an apply model always; a frontier one when a piece loaded), `mode` (the loading mode), `project`, `scope_reason`, `named_projects` (empty in a public repository), `named_count` (in a public repository: how many other projects the request named), `marker` (a `.athos.toml` applied), `public`, `private_held` (private pieces kept out, counted), `store_pieces`, `in_scope`, `request_chars`, `request_sha` (not in a public repository), `request_kind` (person, harness, empty), `wrapper`, `candidates` (up to 5: `piece`, `score`, `shared` (how many words it shares with the request, never which), `head_share`, `request_share`, `projects`, `kept`, `reason`), `scored`, `chosen`, `handed_over`, `meaning`, `thresholds`, `cut` (pages cut to fit), `left_out` (pages with no room), `steps_only` (pages given as their steps' When and Do only, whole), `delivery` (piece: the pages themselves, to an apply model; index: a list of the pieces in reach, to a frontier model; null when nothing was chosen), `offered` (the ids the index listed), `piece_chars` and `index_chars` (what each delivery costs, measured either way), `injected_chars` (the router's own text), `injected_total` (everything the prompt hook handed the model: the router's text plus an edit notice, a share request or a rating added after it), `injected_parts` (the characters of each: `pieces`, `connectors`, `offer`, `edit`, `share`, `rating`), `ms` |
| `edit_seen` | the edit detector keeps a file the agent wrote, sees the agent change it again, or finds a change on the next request | `task_id`, `file_sha` (a hash of the path), `decision` (snapshot, rebased (the agent changed it: the copy moves on), pending (the person changed it between two tool calls; told on the next request), attributed, unattributed (a change with no evidence: given to nobody)), `source` (agent_tool, agent_shell, outside, unexplained), `basis` (the evidence for the decision: `changed_during:<tool>`, `no_timing:<tool>`, `tool_failed`, `changed_between_tool_calls`, `changed_after_turn_end`, `no_tool_call_since`, or why there is none: `no_turn_end`, `changed_before_turn_end`, `tool_after_turn_end`, `background_task_running`), `attributed_to` (agent, person, or null), and for a change given to the person `detector` (between_tool_calls, after_turn_end), `piece` (not in a public repository), `piece_basis` (current_step, route_best, none) |
| `model` | a session starts, every request, and the end of a task whose replies could be read | `task_id`, `model`, `source` (event: the hook said so; transcript_switch: a `/model` switch newer than the latest reply; transcript_reply: the latest reply, since this request's own reply does not exist yet; session: what the session reported, when reported later than both, or last knew; replies: the replies that answered the task; unknown), `seen_in_transcript` (the model of the transcript's latest reply), `stage` (session_start, prompt, end), `changed`, `tier` (frontier, apply), `work_mode` (learn, collaborate), and at the end `answered` (the models whose replies answered the task) and `at_start` |
| `trigger` | a special path matches: save, adjust, gallery, share | `task_id`, `trigger`, `from_person` (true; false for a harness wrapper such as a subagent's message, also one that opens with another wrapper, or when the transcript says the harness sent it; null when the text opens with another tag or the transcript has no entry for it yet), `acted` (it acts only when `from_person` is true), `wrapper`, `origin_signal` (which signal decided: `heuristic`, `both`, `disagree`, `missing`, `missing:heuristic`), `transcript_origin` (person, harness, or null), `project`, `request_chars`, `request_sha`, `injected_total` (what the path handed the model: save, adjust and gallery; a share request is counted in its route event) |
| `context` | a session starts | `hook` (session_start), `project`, `injected_total` (everything the hook handed the model), `injected_parts` (`index`, `journal`, `guide`, `offer`, `audit_hint`, `review`), `index_cap` |
| `piece_opened` | the tool hook sees the agent run `athos show <id>` | `task_id`, `piece`, `projects`, `via` (show), `offered` (the frontier index of this request listed it), `again` (it was already in use for the task), `project` |
| `hook_error` | a hook swallows an exception so your session carries on | `hook`, `where`, `error` (the exception's kind), `line` (file and line inside Athos), never its message |
| `learn`, `grade`, `ui` | reserved for autonomous learning, a piece's grade and the panel's state | not written yet |

Every one of them also carries `at`, `session_id` and `v`, the version of Athos that wrote it. `candidates.reason`
says why a piece did or didn't load: `chosen`, `runner_up_too_weak`, `over_budget`, `beyond_top_k`, `below_min_score`,
`prefixes_only`, `head_share_low`, `request_share_low`, `no_head_match`, `dismissed` or `meaning`; `scope_reason` is the
saved mode (`all`, `project`, `pieces`, `none`) or, in `auto`, `auto:project`, `auto:project+named`,
`auto:no-own-pieces` (a project with no pages of its own: the profile only), `auto:no-own-pieces+named` or
`auto:no-folder`. Events written by 0.1.110 may say `auto:project-without-pieces`: such a folder then saw every page.

**Who wrote a request.** Save, adjust, gallery and share act only on text the person wrote. Two signals decide: the
wrappers the harness puts around its own text (a subagent's report, a notification), and, when the hook gives a
transcript path, the transcript's entry for that prompt (`promptId`; `origin.kind` human, or Athos's own button pressed
by the person, is the person). They must agree; when they disagree, or the transcript has no entry for the prompt, the
path does not act. Claude Code 2.1 writes that entry only after the prompt hook has run, so in Claude Code these paths
do not act by default (the [Save] button and a typed `Athos · adjust` included) until you add `"origin_check":
"heuristic"` to `~/.athos/config.json`, which lets a missing entry fall back to the wrappers alone. Agents that give no
transcript path (Codex, Muse Code, OpenCode) are judged by the wrappers, as before.

`~/.athos/log.md` says the same in one line per operation, for a person or an agent to read with grep and tail:

```
grep '^## \[' ~/.athos/log.md | tail
## [2026-11-15 09:21] route | my-app | loaded release-checklist · 1853 chars · scope auto:project
## [2026-11-15 09:24] route | my-app | none · scope auto:project
## [2026-11-15 09:30] trigger | my-app | share · harness text <agent-message> (heuristic) · ignored
```

Times are UTC. It names a piece only when the piece belongs to that project, or to none and is not private (another
project's are only counted), and it is moved to `log.1.md` once it passes 256 KB, so at most two files are kept. Each session starts with
one hidden line telling the agent where the log is and that `athos audit --session <id>` summarizes it.

`athos audit [--session <id> | --project <name> | --last N] [--show] [--json]` folds the log by session (by default
the session of the folder you run it in) and checks each one against these rules:

| rule | flags |
|---|---|
| `other_project_load` | a piece of another project loaded without the request naming that project |
| `load_without_own_pieces` | a piece loaded in a project that has no pieces of its own (since 0.1.111 such a project sees the profile, so only a piece of another project it didn't name is flagged) |
| `edit_without_basis` | an edit given to the person with no evidence that the person made it |
| `model_inconsistent` | a request recorded under a model other than the one whose replies answered it (a `/model` switch recorded on the requests after it is not flagged); for sessions before 0.1.113, the session's models disagree with themselves or with Claude Code's transcript |
| `injected_over_cap` | more characters handed the model with one request than the router's cap: since 0.1.114 everything the prompt hook adds (`injected_total`), not only the router's text, so an edit notice, a share request or a rating on top of a page counts; older route events are judged on `injected_chars` and the rule says partial |
| `trigger_not_from_person` | save, adjust, gallery or share fired on text the person didn't write (a path that held back, `acted` false, is not flagged) |
| `version_mismatch` | the session's events written by two versions, or Claude Code's plugin and the `athos` on your PATH differ now |
| `private_piece_named` | a private piece loaded, ranked or named outside its projects, in the route events or in this project's `log.md` lines (the agent's replies are not seen) |
| `weak_evidence_learning` | a piece learned with only the model's opinion as evidence (nothing writes `learn` yet) |
| `public_not_declared` | the repository the audit runs in (when it is the session's project) is pushed to a code-hosting site, read from its local git configuration, and its `.athos.toml` does not say whether it is public; `athos public` or `athos public off` answers it |

Each rule says how it was judged: flagged, clean, partial (checked with older data, which is not a proof) or not
evaluated (with what is missing). Sessions recorded before these events are checked as far as their task lines allow:
the pieces each task used and the first 120 characters of its request, the pieces as they are tagged today, and, for
the model, the replies in Claude Code's transcript when it is still on your machine. It only reads; requests are never
shown, and another project's pieces are named only with `--show`.

### Which model answered, and model tiers

The model is resolved for every request, not once per session: the hook's own field when the agent sends one (Codex);
else Claude Code's transcript, where a `/model` switch newer than the latest reply means the new model answers, and
otherwise the latest reply's model keeps answering (the request's own reply is not written yet); the model the session
reported at its start wins when it was reported later than both (a session resumed on another model). When the task
ends, the replies that answered it settle the model: the `task_end` records it, with `model_at_start` when the two
differ, and the next request starts from it. `athos status --json` has `model` (`id`, `source`, `tier`, `work_mode`,
`collaborates`).

Each model has a tier. **frontier** models may learn new ways of working (mode `learn`); **apply** models use what is
already known (mode `collaborate`), and a frontier session also collaborates when a piece loaded for the request. A
model no pattern matches counts as apply. Since 0.1.116 the tier decides how the router's choice is delivered (see
"Pull instead of push" below); it does not change what is saved.

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

A change counts as yours only on evidence that no tool call of the agent made it. The agent changes files in many
ways besides its edit tools (a script, `sed -i`, a formatter, `git checkout`, a build step); until 0.1.111 each of
them was taken for your edit. Now:

- after every tool call of the agent (in Claude Code also a failed one, `PostToolUseFailure`) each kept file is checked,
  with a `stat` first and its content only when that moved. A change that could have happened during the call is the
  agent's, and the copy moves to it. A change whose time (the file's ctime, which no tool can set back) falls before
  the call started, by Claude Code's `duration_ms` and a one-second margin, happened between two tool calls: yours;
- on your next request, a change made after the agent's turn ended, with no tool call since and no background task
  left running, is yours;
- anything else is given to nobody: the `edit_seen` event says `agent_shell`, `agent_tool` or `unexplained`, and the
  agent is told nothing.

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

What it cannot see: a process the agent left running that writes after the turn, when the agent's Stop hook reports no
background task (Claude Code's `background_tasks`), is taken for you; a change made while the agent writes its last
answer (after its last tool call) is given to nobody; a hand edit followed by the agent's own edit tool on the same file,
with no other tool call between, is folded into the agent's write; agents whose hooks carry no `duration_ms` (Codex,
Muse Code, OpenCode) only have the after-the-turn evidence. Checking the kept files costs well under a millisecond per
tool call with twenty files kept.

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

Without the plugin, `athos export --muse` writes your profile as skills in `~/.agents/skills` (that folder is read in
every project; `athos project sync` gives a project its own pieces) and `athos import muse` records past tasks from
Muse's session logs.

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
reports it (`athos_step`), the steps your know-how lacks, and two buttons: **Change this step** (you write how the step
changes; the piece is improved) and **Save as a way of working**. **Keep beside** pins the panel where the host allows it. In a
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
