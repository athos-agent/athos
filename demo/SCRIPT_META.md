# Three minutes for the Meta hackathon

Only what was built during the hackathon (everything after the `pre-hackathon` tag; see `HACKATHON.md`). One sentence of
context for what existed before: Athos already captured know-how in Claude Code and carried it to Codex.

Every take is real and repeatable: `sh demo/setup.sh && sh demo/prep.sh`, then the tapes below. Each mark the tapes press
is checked against `git log`, `git tag -n1` and the tests before a take is kept.

| Time | What is on screen | Take |
|---|---|---|
| 0:00–0:20 | The problem: your know-how stays locked in one agent, and you pay frontier prices for tasks you have already mastered. One line on what existed before the hackathon. | title card |
| 0:20–1:00 | **Your know-how in Meta's agent.** Claude Code learns how this package is released; Muse Code, on Muse Spark, does the next release in the same folder from a one-line request: both versions, changelog, test, commit, tag. `athos watch` fills both bars: `1/1 good · 82% shorter prompt`. | `vhs demo/meta.tape` |
| 1:00–1:50 | **The same task on Meta Model API, in Athos's own loop.** `athos delegate <piece> "…" --backend meta`: Muse Spark does the release in seconds, then `athos report` puts it beside Claude Code and a local model, on your own task. | `sh demo/bench.sh && vhs demo/delegate.tape` |
| 1:50–2:30 | **Measured on your work, not someone else's tests.** The report's per-model lines: each agent and model with its success over the tasks you marked, its time and its tokens. Say it plainly: Muse Spark costs about a fifth of the frontier model here for the same result; it is cheaper, not faster. | same |
| 2:30–3:00 | Close: one store of know-how on your machine, three agents (Claude Code, Codex as a plugin, Muse Code), Meta's models for the tasks you have mastered. `HACKATHON.md` and the compare link for what was built. | title card |

Numbers come from the take itself and are never edited. If a model fails in a take, it is shown failing or the take is
redone; a failed task is never marked good.
