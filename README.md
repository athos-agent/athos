# Athos

Your AI know-how. Free to move, fast to run.

<!-- Demo video or GIF goes here. -->

- **Captures and improves your know-how.** When a task in Claude Code teaches something reusable (your steps, your
  conventions, the mistakes to avoid), Athos saves it as a plain markdown file you can read and edit. Next time, only
  the pieces that match the request are loaded, and each reuse can improve them, with a version history.
- **Free to move.** The same know-how works in Codex, through its skills and hooks, from the one store on your
  machine. Nothing leaves your machine unless you move it.
- **Your own benchmark.** Benchmarks measure someone else's tests; Athos measures yours. Mark each task with one key,
  and `/athos:report` shows what every piece of know-how and every model brings to your own work.

## Install

In Claude Code:

```
/plugin install athos --marketplace athos-agent/athos
```

Requires Python 3.11+. No other dependencies.

## Use

Athos works on its own: it loads matching know-how with each request and, after real work, offers to save what the
task taught. These are the commands you will reach for:

```
/athos:list          see your know-how and what is enabled
/athos:mark g        mark the last task: g good, c needed corrections, f failed
/athos:report        what each piece and each model brings to your work
/athos:codex         take your know-how to Codex
```

Your know-how lives in `~/.athos/know-how/`, one markdown file per piece. Choose what may load with
`/athos:load all | project <name> | pieces <id>... | none`, and copy everything out with `/athos:export <folder>`.

## Roadmap

- Delegate a task you have mastered to a small local model (`athos delegate`).
- OpenCode.
- A native Codex plugin.
- **Athos Cloud**: sync between your devices, a visual map of your know-how, daily control over what is shared, and an
  improvement agent as a service.

## License

Apache 2.0. See [LICENSE](LICENSE).
