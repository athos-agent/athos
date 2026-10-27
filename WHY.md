# Why Athos exists

## The know-how you build with AI doesn't belong to you yet

I use coding agents for almost everything now, and most of it isn't software. A task that starts as "release this
package" or "move these records" or "check why that device stopped reporting" ends up writing code, running tools and
talking to machines along the way. After a few weeks you notice the real output isn't the code. It's the know-how: the
steps that worked, the convention nobody wrote down, the mistake you will never make again.

That know-how lives in one chat, inside one agent. Open a new session and it's gone. Switch to another agent and you
explain everything from scratch. The model helped build it, but nothing you can read, edit or carry with you ever comes
out of the session.

I hit the wall one evening: after a good piece of work I tried to have the agent write down what we had figured out,
and the attempt was flagged as distillation. Fair enough from the model provider's side. But it made the question
concrete: whose is this knowledge, and where does it live?

## Why no lab will build this

Every lab has a good reason to keep your know-how on its platform. Memory features are real, and they are getting
better, but each one remembers for its own agent, in its own format, on its own servers. None of them has a reason to
make what you taught it work just as well in a competitor's agent, or to tell you that a cheaper model does your task
just as well.

So the layer has to be neutral, and it has to be yours: plain markdown files on your machine that any agent can read,
that you can open in an editor, and that nothing uploads unless you move them.

## What Athos does

- **Captures.** When a task in Claude Code teaches something reusable, Athos asks the agent to write it down as a
  *piece*: when it applies, and the steps, criteria and mistakes to avoid, in the words that worked. Each reuse can
  improve the piece, with a version history.
- **Carries.** The same pieces load in Codex and in Muse Code (as skills both read), so the next agent does the task
  from a one-line request instead of a page of instructions.
- **Measures, on your work.** Benchmarks measure someone else's tests. Athos records every task you run, with any agent
  and model, and you mark each one good, corrected or failed. Per piece and per agent it shows the success rate and how
  much shorter your requests got compared to the first time.
- **Delegates.** A task you have mastered can go to a smaller, cheaper model, on your own machine or through Meta Model
  API, in Athos's own small loop that asks before every command.

## What it looks like today

On the demo task (release a small Python package: two version strings, a changelog entry on top, a test for the new
option, a commit and an annotated tag), the first request, the one that teaches the conventions, is 440 characters.
After that, Claude Code, Codex and Muse Code each did the next release from an 80-character request, with nothing
explained: 82% shorter, all marked good.

Delegated to Muse Spark through Meta Model API, the same release took 13 seconds. On my first measurement it cost about
US$0.04, against US$0.22 for the frontier agent doing it: about a fifth, for the same result. Cheaper, not faster: the
frontier agent was as quick. A small local model got there too, free and several times slower. These are single runs, not a benchmark yet; `athos bench`,
which repeats each task several times per model, is the next thing I'm building.

## Why now

Three things changed at once. Coding agents became general-purpose: they now do everyday work in any domain, which
makes the know-how they accumulate worth keeping. There are several serious agents, so lock-in became a real cost. And
smaller models became good enough for tasks you have already mastered, if they get your know-how with the request.

## What isn't solved

- **Capture is only in Claude Code.** Codex and Muse Code read the know-how and their tasks are recorded, but new
  pieces are written from Claude Code sessions.
- **Loading is too eager.** The matching that decides which pieces load with a request sometimes brings one that
  doesn't belong.
- **The numbers are early.** One task, a handful of runs. I'd rather show that than round it up.
- **Marks are yours to give.** Nothing invents a verdict: a task you don't mark stays unevaluated.

## The bet

If agents keep getting better, the scarce thing isn't the model, it's what you have taught them about how you work.
That should be a file you own, that moves with you, and that tells you, on your own tasks, which model is worth paying
for.

Athos is an early alpha and open source under Apache 2.0. Try it on a real task, tell me what breaks, and open an issue
with what you'd want it to do: https://github.com/athos-agent/athos
