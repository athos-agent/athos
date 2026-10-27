# Athos

Your AI know-how. Free to move, fast to run.

![Claude Code learns how a package is released; Codex does the next release in the same folder with no explanation. The bars show each agent's success and how much shorter the request was.](demo/athos-claude-to-codex.gif)

*Claude Code learns once how this package is released. Codex then does the next release in the same folder with a
one-line request. Each bar: success over the tasks you marked, and how much shorter the request was than the first
time (real run, 17 s, waits cut).*

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

When a piece has proven itself, hand the task to a small model on your own machine, through
[Ollama](https://ollama.com):

```
athos delegate <piece> "<request>"           runs in the current folder; asks before every command and write
athos delegate <piece> "<request>" --model qwen3.5:9b
```

The model follows the piece with four tools (run a command, read, edit and write a file), confined to the current
folder. The task lands in `/athos:report` as `local / <model>`, beside Claude Code and Codex, and you mark it like any
other. Nothing is delegated unless you run `athos delegate`. The default is `gemma4:12b`; in our tests a 4B model was
not enough for a release task, and the 12B one did it in about a minute and a half but still needed a correction.
`--yes` runs the model's commands without asking: use it only in a folder you can throw away.

Your know-how lives in `~/.athos/know-how/`, one markdown file per piece. Choose what may load with
`/athos:load all | project <name> | pieces <id>... | none`, and copy everything out with `/athos:export <folder>`.

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

## Roadmap

- OpenCode.
- **Athos Cloud**: sync between your devices, a visual map of your know-how, daily control over what is shared, and an
  improvement agent as a service.

## License

Apache 2.0. See [LICENSE](LICENSE).
