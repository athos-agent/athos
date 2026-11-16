# Athos

![A musketeer walks a sunlit road from an open tower gate, holding an open notebook whose glowing pages lift into a floating checklist: two steps checked, one in progress, two ahead. Along the road, other towers with open gates show the same checklist, ticking in the same order.](docs/athos-banner.jpg)

Your AI know-how. Free to move, fast to run.

**Athos keeps how a person works (their steps, criteria and checklists) as markdown files on their own computer, so
any AI agent works by their rules without being told twice.** A frontier model learns a way of working once; every
other model, down to a small local one, reuses it.

This page is written for an AI agent that has to use, install or change Athos. How it works inside:
[docs/DESIGN.md](docs/DESIGN.md). Every command and file: [docs/REFERENCE.md](docs/REFERENCE.md). Why it exists:
[WHY.md](WHY.md). For people: [professionals](docs/PROFESSIONALS.md) ([en español](docs/PROFESIONALES.md)),
[Claude Desktop](docs/guides/claude-desktop-en.md), [the gallery](https://athos-agent.github.io/athos/).

## What it does, in five lines

1. **Loads.** With each request, a router picks the pieces of know-how that match, from this project and the
   person's profile only. Another project's piece comes in only when the person names that project.
2. **Learns on its own, on a frontier model.** A task whose work an objective check proved (a test run, a build, a
   commit) can be saved as a *candidate* piece without asking the person.
3. **Verifies.** A second frontier model, with read-only tools, checks the candidate. Clean reuses then raise its
   confidence; failures retire it. Only know-how proven this way reaches a weaker model.
4. **Reuses.** An apply model (cheaper, or local) gets the matching pieces and follows them. It never learns.
5. **Records.** Every decision (what loaded and why, which model answered, what was saved) is an event in a local
   log an agent can read back: `athos audit`.

## Models

| Tier | What it does | Default models |
|---|---|---|
| `frontier` | learns and reuses; gets an index of pieces and opens what it needs | `claude-fable-*`, `claude-mythos-*`, `claude-opus-*` |
| `apply` | reuses only; gets the matching pieces in full | `claude-sonnet-*`, `claude-haiku-*`, and **every model no pattern names** |

A model Athos does not know is `apply`: an unknown model never learns. Change the lists with
`athos tiers add frontier '<pattern>'`; `athos tiers which <model-id>` answers for one model.

**Local and open models.** `athos delegate <piece-id> "<request>"` runs a task that follows one piece on a model
served by Ollama on this machine (`--model <name>`), or on a hosted open model (`--backend openrouter|baseten|meta`).
Any model Ollama serves works this way with no change to Athos, a newly released one included: pull it, pass its name.
`athos bench` and `athos shadow` measure whether it keeps up with the answers the person approved.

## Install

**Claude Code** (and Claude Desktop's Code tab):

```
/plugin install athos --marketplace athos-agent/athos
```

**The `athos` command** (needed for OpenCode, the terminal, and `delegate`), Python 3.11+ and nothing else:

```sh
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos start          # language, profession, example ways of working
```

**Codex, Muse Code, OpenCode, Claude Desktop's chat:** [REFERENCE, Install](docs/REFERENCE.md#install). Update the
command and the plugin together: an older Athos reads only the recent part of a history a newer one has archived
(`athos doctor` says which agent is behind).

## What an agent working with Athos must know

- **A piece is a markdown page** in `~/.athos/know-how/`, with frontmatter (`title`, `when`, optional `projects`,
  `visibility`, `status`) and one statement per step: `**When:**`, `**Do:**`, `**Check:**`, `**Because:**`,
  `**Links:**`. A `Check` is a command or an observable fact that proves the step; without one a piece is never
  verified.
- **Follow a piece that was loaded for the request; open one from the index with `athos show <id>`.** `athos show`
  writes nothing.
- **Save with `athos save` (stdin).** On a frontier model the session start says when to use `athos save --auto`;
  an automatic save with secrets, emails, absolute paths of this computer or other projects' names is refused.
- **Status:** `candidate` (learned, not proven), `verified` (the verifier passed that exact text), `retired` (never
  loads). A page with no `status` is the person's own: Athos never rewrites it unless asked.
- **A repository marked public** (`athos public on` writes `.athos.toml`) loads and names only that project's own
  pieces, and keeps no words of the person's requests. If the marker cannot be read, Athos treats the folder as public.
- **`visibility: private`** pieces are never named outside their project and never sent to a model by Athos itself.
- **Nothing leaves the machine** unless the person asks. No telemetry.

## Commands an agent reaches for

```
athos status            the store and this folder's session, in one line
athos list              every piece; ● marks the ones allowed to load here
athos show <id>         print one piece (no side effects)
athos save [--auto]     store the piece written on stdin
athos audit             what Athos decided in this session, and what it got wrong
athos report            what each piece and each model adds to the person's work
athos tiers             which models learn and which reuse
athos verify <id>       run the independent verifier on a candidate
athos memory check      the archive of old events against its manifest
athos public [on|off]   mark this repository public or not
athos profile           the few pieces that load in every project
athos delegate          hand a mastered task to a smaller or local model
athos doctor            which Athos each agent runs
```

## What the person sees

One mark at the right of the prompt's footer in Claude Code: a red ■ "Athos is learning" while a frontier model does
real work or the verifier runs, a green ■ "Athos is collaborating" while one of their pieces is in use, nothing
otherwise. `ATHOS_UI=classic` brings back the earlier interface (trail pane, status line, band).

## Where things are

| Path | What |
|---|---|
| `~/.athos/know-how/` | the pieces (markdown), with `.history/` of earlier versions |
| `~/.athos/events.jsonl` | the live log of events; older ones move to a compressed archive |
| `~/.athos/log.md` | the same decisions, one line each, for an agent to read |
| `~/.athos/config.json` | tiers, interface, caps of the verifier, memory settings |
| `.athos.toml` in a repository | its name for Athos and whether it is public |
| `athos/` in this repo | the CLI (Python, standard library only) |
| `hooks/` | the Claude Code hooks and the one UI module (`ui.tsx`) |
| `athos/adapters/`, `codex/`, `opencode/` | the other agents |

## Working on this repository

```sh
HOME=$(mktemp -d) python3 -m unittest discover -s tests -t .   # never against the real ~/.athos
claude plugin test . && claude plugin validate .
```

Hook code must run on Python 3.9 (what macOS ships). Every change is a pull request; nothing is committed straight to
`main`. The repository is public: no real project names, people or request text in code, tests or commit messages.

## What is measured, and what is not

- With a person's know-how, Meta's Muse Spark did 25 of 25 bench runs right and 2 of 25 without it; the open-weights
  Muse Spark Open 35 of 35 and 0 of 35 ([runs, and what each missed](docs/bench/README.md)). These are small cases
  written for the bench.
- Autonomous learning was tried live: a piece was rejected twice by the verifier, passed on its third version and
  became verified after three clean reuses.
- Not measured yet: how much a verified piece helps a weak model on a task it cannot do alone. On an easy task, a
  small with/without comparison showed no difference.

## License

Apache License 2.0: [LICENSE](LICENSE), [NOTICE](NOTICE). Thanks: [WHY.md](WHY.md#thanks).
