# Guide for lawyers: your way of reviewing contracts, in every AI tool you use

*En español: [abogado.md](abogado.md)*

For practising lawyers who use (or want to use) AI to review contracts and draft briefs. No programming. In half an
hour your checklist is saved as a **way of working**, and every AI tool you use follows it without being told again.

![A lawyer reviews a lease in Claude Code against their checklist and Athos keeps it; then OpenCode, on Meta's Muse Spark, reviews a services agreement from a one-line request and says which way of working it follows.](../../demo/lawyer-en.gif)

## What you get

1. The AI reviews contracts **with your checklist**, not a generic one: your clauses, your order, your table.
2. You explain it **once**. Next time, *"review this contract"* is enough.
3. It works the same in **Claude**, Meta's **Muse Code**, **OpenCode** (with the model you choose) and **Codex**. Your
   know-how is yours and moves with you.
4. Every task shows **which way of working was used**, and you mark it: good, corrected or failed.

## 1. Install (10 minutes, no terminal)

1. Install **Claude Desktop** and sign in.
2. Make a test folder, say `Test contracts`, with a **fictitious or anonymised** contract.
3. In Claude Desktop open the **Code** tab, pick that folder and type:
   ```
   /plugin install athos --marketplace athos-agent/athos
   ```
   Restart Claude Desktop when asked.
4. Ask Claude: *"Run `athos start --lang en --profile law`"*. It adds two example ways of working: **review a contract
   against your checklist** and **build the argument of a brief**.

## 2. Your first review: teach it your checklist

Ask as you would ask a colleague, and the first time paste your own checklist:

```
Review lease.md against my checklist. I act for the tenant.
My checklist:
- parties, object, term, price and payment, governing law and jurisdiction
- deposit: amount and conditions for return
- early termination and notice, for both sides
- repairs: who pays for what
- penalties, automatic renewal, assignment
Give me a table: clause, problem, proposal, priority.
```

What you will see:

- The AI opens with a line like *"Following your 'Review a contract against your checklist': client data first, then
  the summary and the clause table."* You know which method it applies.
- Before opening the contract it asks whether it holds client data that should not leave your computer.
- While it works, the steps it follows show under the input box, in order.
- When it finishes, since the task followed a checklist, Athos asks the AI whether it is worth keeping. Your checklist
  becomes a way of working: a plain text file of yours, on your computer.

Next time: *"Review this services agreement, I act for the supplier."*

## 3. Mark how it went

After each task three buttons appear: **Good**, **Corrected**, **Failed**. One second, and with those marks Athos
shows which ways of working serve you, and in which tool (the bar under the input box).

## 4. The same, in your other tools

| Tool | How to install |
|---|---|
| The `athos` command (needed by the ones below) | `curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh \| sh` |
| **Muse Code** (Meta) | `muse plugins marketplace add athos https://github.com/athos-agent/athos`, then `muse plugins install athos@athos` and `muse plugins approve athos` |
| **OpenCode** (any model) | `athos opencode install`, then restart OpenCode |
| **Codex** | `codex plugin marketplace add athos-agent/athos` and `codex plugin add athos@athos` |

In each one you ask the same thing, the AI follows your way of working and Athos records the task. We tried the same
fictitious contract in Muse Code and in OpenCode with Meta's Muse Spark: both followed the checklist (five-line
summary, clause table, the decision left to the lawyer).

## 5. Client confidentiality

- **Your ways of working never leave your computer.** Athos has no server and no account.
- **The AI does see what you show it.** With client data: anonymise names, IDs and amounts, or use a model that runs
  on your computer with no internet (`athos delegate` with [Ollama](https://ollama.com)).
- **Muse Code:** keep *Contributor* mode off (`/settings`).
- The AI proposes and you decide: the example ways of working are not legal advice and ask the AI to ask rather than
  decide.

## 6. Make it yours

Your ways of working live in `~/.athos/know-how`, one per file. Open them in any editor (or
[Obsidian](https://obsidian.md)) and write your way: the order you read clauses in, the risks you always look for,
your table format. Every change keeps the previous version.

Questions, ideas or a case you'd like to see? Open an issue at
[github.com/athos-agent/athos](https://github.com/athos-agent/athos/issues).
