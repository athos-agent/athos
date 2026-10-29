# Athos at the Meta hackathon

Athos existed before the hackathon. This file separates what was built before the kickoff (26 Oct 2026, 16:00 UTC)
from what was built during the event.

- Everything before the kickoff is tagged [`pre-hackathon`](https://github.com/athos-agent/athos/tree/pre-hackathon).
- Everything built during the event comes in through pull requests labelled
  [`hackathon`](https://github.com/athos-agent/athos/pulls?q=label%3Ahackathon).
- The whole hackathon diff:
  https://github.com/athos-agent/athos/compare/pre-hackathon...main

## Before the kickoff

- [#1](https://github.com/athos-agent/athos/pull/1) Core plugin: capture, store, improve, load and control know-how
- [#2](https://github.com/athos-agent/athos/pull/2) Local evaluation: your own benchmark (`athos report`)
- [#3](https://github.com/athos-agent/athos/pull/3) Terminal status line and one-key marking band
- [#4](https://github.com/athos-agent/athos/pull/4) Capture: count only the main conversation's work for the current request
- [#5](https://github.com/athos-agent/athos/pull/5) Codex adapter: same know-how, same evaluation
- [#6](https://github.com/athos-agent/athos/pull/6) Import Codex tasks from its session files
- [#7](https://github.com/athos-agent/athos/pull/7) README, demo script and `/athos:codex`
- [#8](https://github.com/athos-agent/athos/pull/8) `athos delegate`: run a mastered task on a small local model (Ollama)

## During the hackathon

- [#9](https://github.com/athos-agent/athos/pull/9) Hackathon setup: this file, the `hackathon` label and the `athos/adapters/meta/` and `athos/eval/meta/` modules
- [#11](https://github.com/athos-agent/athos/pull/11) One bar per agent for this project's know-how (success rate, mean tokens, tokens saved against the first run): under the prompt in Claude Code, and `athos watch` beside Codex and Muse Code (0.1.7)
- Bars measure tokens instead of time: mean tokens per task and tokens saved against the run that taught the piece (0.1.8)
- Bars measure what the know-how spares you: success over marked tasks and how much shorter each request is than the first run's; tasks keep their full request length, and imported Codex tasks skip the context Codex injects (0.1.10)
- `WHY.md`: why Athos exists, what it does today with the measured numbers, and what isn't solved
- Install without Claude Code: `curl -fsSL …/install.sh | sh` puts the `athos` command in `~/.local/bin` with the newest Python 3.11+ found (for Muse Code, Codex or the terminal); README says what Athos is for any domain, and lists the three ways in (0.1.17)
- `athos bench`: the same task, several runs per agent and model (Claude Code, Codex, Muse Code, Muse Spark on Meta Model API, a local model), with and without the know-how, each verdict from a check of what the run left behind (git, tests, files); four cases in four domains (a release, a monthly report, a device setup, a tiling plan that counts method stages done and client decisions invented), results apart from real work in `~/.athos/bench/`, and a report that recommends the cheapest agent at the best success rate (0.1.18)
- `athos bench` takes your own cases from `~/.athos/bench/cases/` (or `ATHOS_BENCH_CASES`), for tasks whose data must stay on your machine; a case can set its own timeout, budget per run, step limit, check time and network access for Codex and Muse Code, and the report adds the check's own cost (a reader model) to the spend cap (0.1.19)
- Quieter capture: the instructions for saving know-how go in once at session start, out of sight, so the Stop hook asks with one short line; a save is announced by Athos itself as one line under the answer (`athos · saved «title» · ready in Claude Code · Codex · Muse Code`), and refreshes the Codex/Muse Code skills export when there is one (0.1.20)
- The know-how as a wiki (`docs/WIKI.md`): pages of statements (When / Do / Because / Links) whose links are trajectories (what applies next or alongside in a real task), an `Index.md` rebuilt on every save, broken links reported back in the same turn, `athos wiki` to check it, and trajectory subagents in markdown (`athos wiki agents [--install]`) rebuilt whenever one of their pages improves (0.1.21)
- While a task runs, the line under the prompt says which know-how it follows, its size and where else it is ready (`athos · following «title» v5 · 8 steps · ready in Claude Code · Codex · Muse Code`), in the terminal and in Claude Desktop's Code tab (0.1.21)
- `athos mcp`: the know-how as an MCP server over stdio with no dependencies (find for a request with its trajectory, show, list, save), so Claude Desktop's chat and any MCP app use the same `~/.athos` (0.1.21)
- The Stop hook asks to save know-how only after a turn that changed something (an edit, a commit, a command that is not a pure read); a turn of reads and checks, such as answering a question, ends without it (0.1.22)
- README: the know-how is yours (plain files, no agent or provider lock-in), and delegation to cheaper models is up front, with the public bench result (Muse Spark 19/20 with the know-how, 2/20 without, 8–24× cheaper than Claude Code); thanks in WHY.md for the talk whose ideas shaped the wiki's hygiene
- A wiki that stays clean: a save reports statements of other pages for the same moment, so the agent checks they agree; `athos wiki` lists candidates to retire from your recorded tasks (unused pages, mostly failed pages, links never followed); `athos export --dataset` writes your statements and marked tasks as JSON lines, to evaluate or specialise a model on your own work (0.1.23)
- For people who don't program: `athos start` asks language (Spanish or English) and profession, adds example ways of working for law (build the argument of a brief, review a contract) and, since 0.1.27, sports coaching, each leaving professional decisions to the person; a bare `athos` greets instead of failing; guides in `docs/PROFESSIONALS.md` and `docs/PROFESIONALES.md` start from Claude Desktop's Code tab, no terminal; a second piece loads only when it matches nearly as well as the first (0.1.24)
- Plain words, in the person's language: the status line, the line under the prompt, the save line, the marking band (Salió bien / Lo corregí / Falló), the Stop line, `athos mark`, `athos list` and `athos status` follow the language chosen with `athos start` (Spanish or English), and say "ways of working" instead of "pieces" (0.1.25)
- Tested a lawyer's first run end to end in Codex and in Muse Code (Muse Spark 1.3): both found the contract-review piece as a skill and followed it (Codex first asked whether the contract held client data, as the piece says). Fix found there: Codex's per-turn skill catalog no longer counts as using every skill; only reading one does (0.1.26)
- Sports coaching replaces the health examples in `athos start` (plan the training week with the coach's own rules; write the post-match report), and a fifth bench case, `training-week`: a runner's last four weeks with a load spike, scored stage by stage against the coach's method. The request names the output format, so both arms know it; the difference is the method. Muse Spark: 3/3 good with the know-how (9/9 stages), 0/3 without (6–7/9: it kept building after the spike instead of cutting back) (0.1.27)
- Delegation take recorded: Claude Code, local gemma and Muse Spark each release 0.3.0 with the piece; Muse Spark 13 s and 17.5k tokens. The demo's verdict now also requires the test the piece asks for, so a release without it is marked corrected, not good
- The three-minute script (`demo/SCRIPT_META.md`), the delegation take (`demo/bench.sh` + `demo/delegate.tape`: the same release in Claude Code, on a local model and live on Muse Spark, each marked by git and the tests), the report's pieces line now says how much shorter the requests are, and a demo store imports only sessions after it was created (`import-since`) (0.1.16)
- Muse Code take (`demo/meta.tape`): Claude Code releases 0.3.0, Muse Code (muse-spark-1.3) releases 0.4.0 in the same folder with a one-line request, both bars `1/1 good · 82% shorter prompt`; a Muse Code session killed without its end is imported once its log has been still for ten minutes (0.1.15)
- Muse Code tasks are imported once finished (another request followed, or the session ended), so a running task is never recorded cut short (0.1.14)
- Muse Code as a third agent: `athos export --muse`, and `athos import muse` records its tasks from Muse's session logs (model, tokens with subagents, pieces read, request length); its bar in `athos watch`, and a warning when a task ran in Contributor mode (0.1.13)
- `athos delegate --backend meta`: a mastered task runs in Athos's own loop on Meta Model API (`muse-spark-1.3`), recorded as `meta` (0.1.12)
- Bars count a piece's uses only after the run that taught it, so an old session that names it is not a use (0.1.11)
- Athos as a Codex plugin (`.codex-plugin/plugin.json`, marketplace in `.agents/plugins/marketplace.json`): `codex plugin marketplace add athos-agent/athos`; token counts read as 1.1M (0.1.9)
- README demo GIF: Claude Code then Codex in the same folder, both `1/1 good · 82% shorter prompt` (`demo/athos-claude-to-codex.gif`)
- One-folder demo: Claude Code and Codex release the same package in turn, measured against the run that taught the piece (`demo/setup.sh`, `demo/prep.sh`, `demo/SCRIPT_GREG.md`)
- [#37](https://github.com/athos-agent/athos/pull/37) OpenCode plugin: `athos opencode install`; matching know-how in the system prompt, tasks recorded with OpenCode's token counts, the ask-to-save after real work; tested end to end with Muse Spark through Meta Model API (0.1.28)
- [#38](https://github.com/athos-agent/athos/pull/38) `athos opencode install` run inside a Claude Code session no longer writes a plugin-version path into the OpenCode plugin (0.1.29)
- [#39](https://github.com/athos-agent/athos/pull/39) Muse Code runs the Athos plugin (`muse plugins install athos@athos`): hooks recorded as `muse-code`, tokens from Muse's session log, Muse's read-only tools known, no double import; tested end to end with Muse Spark through Meta Model API (0.1.30)
- [#40](https://github.com/athos-agent/athos/pull/40) Loading needs the same words, not words that only start alike ("checklist" loaded a CI-checks piece); the best piece loads even when it is long; background-task notices load nothing (0.1.31)
- [#41](https://github.com/athos-agent/athos/pull/41) The installer's next steps name the OpenCode and Muse Code plugins instead of `athos export --muse`, which would duplicate pieces next to the Muse plugin (0.1.32)
- [#42](https://github.com/athos-agent/athos/pull/42) A task that follows a checklist asks to be saved even when it changes no file; the agent says which of your ways of working it follows and how it applies; the steps show under the prompt; the bars include OpenCode and Muse Code once installed (0.1.33)
- [#43](https://github.com/athos-agent/athos/pull/43) README for the people using Athos: the know-how moving across Claude Code, Codex, Muse Code and OpenCode and what was checked in each; three guides (lawyers, coaches, your checklist is know-how), in English and Spanish (0.1.34)
- [#44](https://github.com/athos-agent/athos/pull/44) The lines the person reads say plain `athos save` instead of a full path with their user name; file names and punctuation split into words when matching ("contrato-servicios.md" loaded nothing); the agent opens with a fixed `Athos · «piece»: how it applies` line, which Muse Spark now writes (0.1.35)
- [#45](https://github.com/athos-agent/athos/pull/45) A checklist file named in the request counts as the person's own checklist (0.1.36)

## Meta models used

- `muse-spark-1.3` (default) and `muse-wonder-1.0` through Meta Model API (Chat Completions with tools), behind
  `athos delegate --backend meta` in `athos/adapters/meta/`.
- Muse Code (Meta's coding agent, its own Muse Spark model), with Athos's know-how as skills; `athos/adapters/muse/`.
