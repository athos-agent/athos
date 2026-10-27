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
- One-folder demo: Claude Code and Codex release the same package in turn, measured against the run that taught the piece (`demo/setup.sh`, `demo/prep.sh`, `demo/SCRIPT_GREG.md`)

## Meta models used

None yet.
