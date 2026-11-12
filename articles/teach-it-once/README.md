# Teach it once in Claude; Codex works your way

*Matías Molinas · November 12, 2026*

Most of what you pay a frontier model for, on work you repeat, is not intelligence. It is being told again how you do
things. So I tested a simple idea: let the strongest model do a task with you once, correct it in your own words, keep
what it learned as a plain page of markdown, and hand that page to a cheaper model, in the same tool and in a
different one.

It worked. And what transferred was not the strong model's knowledge. It was mine.

**Video (1:34):** [watch it here](https://athos-agent.github.io/athos/articles/teach-it-once/)

## The task: a month-end close with house rules

A bank reconciliation: about 120 ledger lines against about 115 bank lines, from fictitious books, with ten planted
problems. There is a duplicate entry, swapped digits, a wrong sign, a card sale settled net of a fee nobody booked, a
batch deposit missing a receipt, a payment that never left the bank, two bank charges, an exchange-rate difference and
a payroll difference.

Finding those is not the hard part. Without any house rules involved, even the smaller models found every one, with
no false alarms. What no model can know is what the firm does with each of them:

- Bank charges of $40 or less are posted without asking; above that they are a discrepancy.
- Exchange-rate differences under $60 are posted too; from $60 they get adjusted.
- Anything touching payroll, or any line of $5,000 or more, goes to the controller, and nowhere else.
- Each kind of correction has the firm's own action code. A payment that never left the bank is put on hold, not
  reversed; a batch deposit missing a receipt means asking the bank.

The request only says "reconcile it, our way" and gives the output format.

## Teaching once

The strongest model I had, Claude Fable 5.2, did the first month and got 7 of the 10 items the firm's way. Being
smarter does not help with rules it has never seen. Then the person answered once, the way people do: "Good, but
that's not quite how we do it here…", followed by the rules in their own words. Fable redid the month correctly and
wrote down the way of working: six steps, each saying when it applies, what to do and why, quoting the person.

That page is the only thing that carries over.

## Then the cheaper models, in Claude and in Codex

I froze the page and gave it to cheaper models for three different months, three runs each: nine runs per setup.

**Inside Claude.** Sonnet 5.5 on its own got 57% of the items right and never a full month correct. With a placebo
page of the same length and no rules, 64%, still no full month. With the page Fable wrote: 100% of the items and nine
correct months out of nine, the same as Fable itself, at about a quarter of the cost per run ($0.11 against $0.45).
Teaching it cost about $2, once.

**Across tools.** The same page, never edited, went to Codex. GPT-6.1-Sol on its own got 46% and no full month. With
the page Fable wrote in Claude: 100%, nine months out of nine. Sol already finds all ten problems on its own; what it
gets wrong is exactly the firm's policy. With the page, it works the person's way.

## The video: the same thing, live

The video is not a replay of those runs. It is a fresh set of takes, recorded on November 12 through Athos itself: the
plugin in Claude Code saves the page when the person asks, and Athos's hooks in Codex load it when a request matches.
One month, three runs per setup, and everything on screen comes from the real output.

- Fable's first answer: 6 of 10 the firm's way. After one correction, 10 of 10, and the page is saved.
- Next month, Sonnet with the page: 10, 10 and 9 of 10, at $0.18 to $0.24 a run.
- The same month in Codex, Sol without the page: 4 of 10, all three times. In its own words, the person's posting and
  escalation policy "wasn't provided or found".
- Sol with Athos: it opens by naming the person's way of working, reports each of the six steps as it applies them,
  and gets 10 of 10, all three times.

## One thing I did not expect

The request says "our way", and Sol took that literally. In every run without the page it went looking on disk for
the person's policies before answering. In a first batch it found leftovers of this very experiment in my own Athos
folder, and one run came out perfect "with no help". I removed them and ran the batch again; the numbers above are
from that clean batch. It was a fault in my setup, and also the most telling thing in the data: a capable agent now
expects your way of working to be written down somewhere, and goes looking for it.

## Where it did not carry all the way

**The smallest Codex model.** GPT-6-Luna went from 49% to 83% with the same page, not to 100%. Giving it the page three
different ways (project instructions, pasted into the request, as a skill) gave 83%, 79% and 76%, so the delivery is
not the cause. What fails almost every time is one item, the payment that never left the bank, which Luna misses
without the page too. The rule transferred; the ability to spot that one line among 120 did not. A page carries what
you know. It cannot carry what the model cannot see.

**Tasks with nothing to teach.** On self-contained problems, such as the same reconciliation without house rules or
seventeen exact-answer signal-processing problems, the cheaper models were already at the ceiling. There was nothing
to transfer.

## Ongoing: a long, open task

I am running the same idea on a 90-minute, open-ended exercise: planning a knee replacement on a public 1993 cadaver
CT with a synthetic defect. It is an educational exercise, not clinical work. Here the page is not a set of rules but
a method: six pages written in earlier work with Claude, handed to Codex untouched.

The first finding: GPT-6-Astra without the method delivered 2 of 10 planning stages, a careful discussion with no
measurements. With the method, in its furthest run so far, it reached 8 of 10, working the way the method asks: bone
models, landmarks and frames, six of seven reference measurements within tolerance, and the defect measured at 2.74
cm³ against a true 3.0, by mirroring the healthy knee, as the method says. Sonnet 5.5 with the same method in Claude
reached 8.5 to 9.

These are a handful of runs and none is complete yet, so this is a direction, not a result. I will publish the
finished runs when they are done.

## Limits, plainly

- Nine runs per setup, one domain, three months of fictitious books, house rules invented for the test.
- I did not measure Codex costs.
- I discarded and repeated runs three times for setup faults: a harness artifact, Codex picking up an unrelated page
  from my own store through my hooks, and Sol finding leftovers on disk. A Codex run "with nothing" only counts if its
  session shows it read nothing else; I checked that for Sol. Repeated Codex numbers moved by 2 to 9 points, which is
  the real precision of these figures.

## Why it matters

If the valuable part is yours, it should live with you, as files you own that any model in any tool can read. Then
picking a model stops being a question of loyalty and becomes a question of price: teach once with the best one, and
let the cheapest one that passes do the work, in Claude or in Codex.

That is what Athos does. It keeps your ways of working as plain markdown on your machine, loads the right one when a
request matches, in Claude Code, Claude Desktop and Codex, and shows you each step as the agent follows it. It is open
source: [github.com/athos-agent/athos](https://github.com/athos-agent/athos).
