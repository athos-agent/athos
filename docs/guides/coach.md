# Guide for coaches: your method, in every AI tool you use

*En español: [entrenador.md](entrenador.md)*

For coaches of athletes or teams who want the AI to plan and write reports **their way**, not by generic rules. No
programming.

## What you get

1. The AI plans the week with **your rules**: how you compute load, when you cut back, how many hard days, what comes
   after the long run.
2. You explain them **once**. Next time, *"plan Juan's week"* is enough.
3. It works the same in **Claude**, Meta's **Muse Code**, **OpenCode** (with the model you choose) and **Codex**.
4. The athlete's own decisions (a tune-up race, the goal pace) stay open, as you would leave them.

## Why it pays off: we measured it

We asked Meta's Muse Spark to plan an athlete's next week from four weeks of log. **With** the coach's method saved in
Athos: 3 of 3 plans right, all 9 steps met. **Without** it: 0 of 3. Without the method it never cut back after a week
with a spike, the one thing a coach never forgets. (The `training-week` case of the public bench; 3 runs per arm.)

## 1. Install (10 minutes, no terminal)

1. Install **Claude Desktop** and sign in.
2. Make a folder, say `Athletes`, with one athlete's log (a spreadsheet exported as CSV: date, session type, minutes,
   perceived effort 1–10).
3. In Claude Desktop open the **Code** tab, pick that folder and type:
   ```
   /plugin install athos --marketplace athos-agent/athos
   ```
   Restart when asked.
4. Ask Claude: *"Run `athos start --lang en --profile sports`"*. It adds two example ways of working: **plan the
   training week** and **write the post-match report**.

## 2. Your first plan: teach it your rules

The first time, write your rules as you would tell an assistant:

```
Plan next week for the athlete in athlete.json from log.csv.
My rules:
- session load = minutes × effort (1–10); compute it with code, not by eye
- if last week is above 1.3 times the four-week mean, next week drops 10%; otherwise it rises 10% at most
- at most two hard days (effort 7+), never back to back
- one long run; the day after is rest or very easy
- tune-up race and goal pace are the athlete's call: leave them as questions
```

What you will see:

- The AI opens by saying which way of working it follows and how it applies to this athlete.
- It computes the loads with code, not from memory, and shows the numbers.
- While it works, the steps it follows show under the input box, in order.
- When it finishes, since the task followed a list of rules, Athos asks the AI whether it is worth keeping. Your rules
  become a way of working.

Next time: *"Plan Juan's week."*

## 3. The post-match report

The same with your report format: *"Write the match report from stats.csv and my notes."* The example asks for numbers
with their source, three things done well and three to fix, and leaves team decisions to you. Swap it for your format.

## 4. Mark how it went

After each task: **Good**, **Corrected** or **Failed**. With those marks you see which way of working serves you, and
in which tool.

## 5. The same, in your other tools

| Tool | How to install |
|---|---|
| The `athos` command (needed by the ones below) | `curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh \| sh` |
| **Muse Code** (Meta) | `muse plugins marketplace add athos https://github.com/athos-agent/athos`, then `muse plugins install athos@athos` and `muse plugins approve athos` |
| **OpenCode** (any model) | `athos opencode install`, then restart OpenCode |
| **Codex** | `codex plugin marketplace add athos-agent/athos` and `codex plugin add athos@athos` |

## 6. Your athletes' data

- **Your ways of working never leave your computer.** Athos has no server and no account.
- **The AI does see what you show it.** Training logs can include health data: use initials instead of names, or a
  model that runs on your computer (`athos delegate` with [Ollama](https://ollama.com)).
- **Muse Code:** keep *Contributor* mode off (`/settings`).
- The AI proposes and you decide: with an injury or a symptom, what counts is your judgement and a health
  professional's, not the plan.

## 7. Make it yours

Your ways of working live in `~/.athos/know-how`. Open them in any editor and write your method: your thresholds,
your session types, your periodisation. Every change keeps the previous version.

A case from your sport you'd like to see? Open an issue at
[github.com/athos-agent/athos](https://github.com/athos-agent/athos/issues).
