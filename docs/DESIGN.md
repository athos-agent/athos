# Athos: technical design

For an AI agent that has to reason about Athos or change it. Short on purpose: the exact formats, flags and limits are
in [REFERENCE.md](REFERENCE.md); this page says how the parts fit and which rules must not break.

## The idea in one paragraph

A person's way of working is kept as markdown pages (*pieces*). A strong model learns a piece once, from a task whose
work something objective proved. A second strong model checks it. From then on any model, a small local one included,
is handed the piece and follows it. Everything Athos decides is an event in a local log, so an agent can audit it.
Nothing leaves the machine.

## Parts

```
agent (Claude Code, Codex, Muse Code, OpenCode, Claude Desktop)
   │  hooks: session-start, prompt, tool-start, tool, tool-failed, stop
   ▼
bin/athos hook <moment>            Python, standard library only, must run on 3.9
   ├─ load/        router: which pieces this request gets
   ├─ tiers.py     which models learn (frontier) and which reuse (apply)
   ├─ evidence.py  what each tool call proved (tests, builds, commits)
   ├─ autolearn.py whether this task may be saved without asking
   ├─ verify.py    the independent verifier (detached, another frontier model)
   ├─ grade.py     candidate → verified → retired, from verdicts and reuses
   ├─ memory/      live log → compressed archive → rollups (the dream cycle)
   ├─ audit.py     reads the log back and flags what Athos did wrong
   └─ indicator.py the one state the UI shows: learning, collaborating, idle
~/.athos/                          the person's store (the only state)
```

The hooks are short processes: each reads a little, appends events, and exits. Nothing in a hook waits for a model.
Long work (the verifier, the dream cycle) is started detached by the Stop hook.

## Data

| What | Where | Notes |
|---|---|---|
| A piece | `know-how/<id>.md` | frontmatter + one statement per step (`When`, `Do`, `Check`, `Because`, `Links`); earlier versions in `.history/` |
| Moving numbers of a learned piece | `piece-meta.json` | confidence, last verified, evidence; never written into the piece's file |
| Events | `events.jsonl` | append-only, one JSON line each, appended under a lock |
| Old events | `memory/archive/events-NNNNN.jsonl.gz` + `manifest.json` | compressed segments, never deleted, each with its sha256 |
| Derived views | `memory/ledger.json`, `memory/rollups.json` | rebuilt from the archive at any time (`athos memory rebuild`) |
| Readable log | `log.md` | one line per decision |
| Settings | `config.json` | `tiers`, `autolearn`, `memory`, `ui` |
| A repository's marker | `<repo>/.athos.toml` | `name`, `public` |

Files more than one process writes are replaced in one step (written beside, then moved) and, when read-changed-written,
changed under a lock. A state file that cannot be read is an error, never an empty value written back.

## A request, step by step

1. **Session start.** The hook records the session and a provisional model guess. A frontier model gets a short index
   of the pieces in reach, plus the instruction for saving on its own. An apply model gets no saving instruction.
2. **Prompt.** The router scores the pieces in scope against the request's words. Scope is this project's pieces and
   the profile (the few pieces the person marked as general). A project with no pieces of its own sees only the
   profile. Another project's pieces enter only when the request names that project; a project named like a common
   word needs a phrase that refers to it as a project. Two margins keep a weak match out. Delivery depends on the
   tier: an apply model receives the matching pages (capped); a frontier model receives an index and opens pages with
   `athos show`. A `route` event records what was chosen and why, without the request's words in a public repository.
3. **Model observed.** The model is taken from the first API request of the session, not from settings. Until it is
   observed, nothing is saved: a guessed model never learns.
4. **Tool calls.** `tool-start` and `tool` record evidence: a verification command and its result, a commit (seen by
   watching `HEAD`), a piece opened, an edit. An edit is attributed to the person only when the evidence shows the
   agent did not make it.
5. **Stop.** The task ends. Reuses of pieces are graded on the evidence. If the model saved a candidate with
   `athos save --auto`, the verifier is started detached. If the live log is past its window, the dream cycle is
   started detached.

## Learning

A save without asking needs all of: a frontier model that was observed; a task with strong evidence (a passing test
run, build or linter, or a commit); a piece with at least one runnable `Check`; no private data (secrets, emails,
absolute paths, other projects' names); and no existing piece that already says the same (then that piece is
improved instead). The piece starts as a `candidate`.

**The verifier** is another frontier model, run headless with read-only tools (`Read`, `Grep`, `Glob`) on a bundle:
the piece, the task's diff, the verification output, a snapshot of the files the piece names, and the subjects of
earlier commits. It judges five criteria: the evidence passed, the piece matches the work, its checks can be run, it
holds no private data, it is reusable. Its verdict counts only for the exact text it read. Defaults: 6 runs and
US$1 per day, US$0.50 per run. A rejection comes back to the author as feedback the next time the piece is opened;
three rejected versions in a row set the candidate aside for the person.

**Grades** (`grade.py`):

- `candidate → verified`: the verifier passed this text, and since then two clean reuses on a frontier model or one
  on an apply model whose `Check`s the hooks saw pass. A `risk: high` piece always needs a clean reuse.
- `verified → candidate`: a reuse corrected or failed on evidence tied to the piece, or 90 days without use.
- `→ retired`: three corrected or failed reuses among its last five. Retired pieces never load; `athos revert`
  restores.
- A page with no `status` belongs to the person: it loads like a verified one and Athos never rewrites it.

A reuse is clean only on objective evidence. The person's words ("good", "no, wrong") move confidence, never status.
A reuse in the session that wrote the piece does not count.

## Models and tiers

`tiers.py` matches a model id against two lists of patterns in `config.json`. Frontier: learns, gets an index. Apply:
reuses, gets pages. A model no pattern matches is apply, so supporting a new model as a reuser needs no code: it
already is one. Making a model a learner is one line, `athos tiers add frontier '<pattern>'`, and should be done only
for a model trusted to write know-how others will follow.

Small and local models reach Athos three ways:

1. **As the agent's model** (for example OpenCode on any model): the hooks run as usual, the model is apply.
2. **`athos delegate <piece> "<request>"`**: Athos's own loop gives the model the piece as instructions and a small
   set of tools, on Ollama (`--model <name>`), OpenRouter, Baseten or Meta's API. A model newly published for Ollama
   works by name.
3. **`athos shadow` / `athos bench`**: the same task on a cheaper model, compared with the answers the person
   approved, to decide whether it can take the task over.

What a weak model needs from a piece is in the piece's form: steps in order, each with a `Check` it can run. That is
why a piece without a runnable `Check` is never verified.

## Memory

The live log holds a recent window (30 days or 4 MB, never less than 8 days). The **dream cycle**, started by the Stop
hook and run without a model, has three phases: archive the events older than the window into a compressed segment;
fold them into the ledger and the rollups; trim the live log. Hooks read only the live log and the rollups, so their
cost does not grow with history; a test asserts that no hook path reads the whole history.

Invariants the cycle keeps, each with a test and a stress run (real processes, half of them ignoring the lock, the
cycle killed at random):

- No line lost and none counted twice, with writers that take the lock and writers that do not.
- A log put back from a backup is trimmed, not archived again.
- A damaged segment or manifest is reported and rebuilt from the folder, never read as "no archive".
- A cycle that cannot make progress says why once and backs off.
- The ledger and the rollups always equal a rebuild from the archive.

An optional model pass that proposes merging pieces used together is off by default and only proposes.

## Privacy rules (do not weaken)

- **Project scope.** A piece tagged with a project loads only there, unless the person names that project.
- **Public repositories.** In a repository marked public (`.athos.toml`, `athos public on`), or one whose marker
  cannot be read, Athos loads and names only that project's own pieces and the profile pieces explicitly allowed
  there, stores no words or hash of requests, and no memory command prints another project or a hidden piece. A test
  walks every memory command to hold this.
- **Private pieces** (`visibility: private`) are never named outside their project and never put in a bundle sent to
  a model.
- **`athos show` has no side effects.** Use is counted by the tool hook inside a session, not by the command.
- **No telemetry.** The only network calls are the ones the person starts: a model backend for `delegate`, `bench`
  or `shadow`, and the verifier through the agent's own CLI.

## Auditing

`athos audit` reads a session's events and checks rules, for example: a piece of another project loaded; a load in a
project with no pieces; an edit given to the person without evidence; a model recorded that differs from the one that
answered; a save by an apply model; overlapping pieces; an older Athos writing to an archived history. A wrong
history is never edited: `athos repair --apply` appends correction events.

## What the person sees

`indicator.py` reduces everything to one state, read by the single UI module (`hooks/ui.tsx`) through
`athos status --ui`: `learning` (a frontier model is doing work that can be learned from, or the verifier is
running), `collaborating` (a piece is in use), `idle` (nothing drawn). The module draws a red or green square beside
the mode labels of the prompt footer. A failure anywhere clears the mark instead of showing an error.

Claude Desktop's chat has no hooks: `indicator.chat` computes the same three states from the MCP server's session
(`collaborating` while a piece `athos_find` handed over, or a step of one, is in use, and it wins; `learning` while new
steps are drafted with no piece, or while a save from the chat is written; `idle` otherwise), recorded as the same
`ui` event. `athos_find` opens the panel (`athos/mcp/trail.html`) in a minimal form that draws the square alone, one
short line: its payload is the state, its `why`, the language and the interface, never a piece, a title, a step or the
request. The model still reports steps with `athos_step`, which drive the state. `"ui": "classic"` brings back the old
panel.

The chat saves on its own when the person lets it (`autolearn.chat`, `own` by default): the model's `athos_save` there
becomes the person's own piece (no status), through `autolearn.save_chat`, after the same content checks as an
automatic save (`private_findings`, and `wiki.same_way` against the pieces the chat may name: improve that one
instead). It records a `learn` event marked `chat` with the model unobserved, which the audit lists as a chat save
instead of flagging it while the setting is `own`. With `off` the model's save is refused there, as on any model
Athos cannot resolve. Every MCP tool carries annotations (read-only, destructive, open-world) so the host can group
them and remember the person's permission.

## Changing Athos

- Tests use a throwaway `HOME`; never the real `~/.athos`.
- Hook code stays compatible with Python 3.9 and reads only the recent window.
- Every append to the events log goes through the locked append.
- A change to what loads is measured with `athos bench route` before and after.
- A new event type must be handled by the memory fold (archived, folded, unknown fields tolerated).
- A new command that prints pieces or projects must honour the public-repository rule.

## Known limits

- A weak model's gain from a verified piece is not yet measured on a task it cannot do alone.
- On a filesystem without hard links, a line written late into the old log during a trim can be lost; the cycle
  records that it ran without links.
- The ledger keeps one row per task, so a cycle's peak memory grows with the archive.
- The private-data check before an automatic save can refuse harmless text, and the verifier can need more than one
  version of a correct piece.
