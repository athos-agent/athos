# Athos for professionals (law, medicine and any other trade)

No programming needed. If you can explain to a new colleague how you do your work, you can use Athos.

## What it does, in one sentence

Every time you work with an AI (Claude, Codex or Meta's Muse) you explain how you do things: your checklist, your
format, what must never be forgotten. Athos keeps those **ways of working** as plain files of yours, on your computer,
and gives them to the AI next time, so you never repeat them.

## Start without a terminal (recommended)

1. Install **Claude Desktop** and sign in.
2. Open the **Code** tab and choose the folder with the documents you will work on (a test folder, at first).
3. Type in the chat:
   ```
   /plugin install athos --marketplace athos-agent/athos
   ```
   and restart Claude Desktop when it asks.
4. Ask Claude, in your own words: *"Run `athos start --lang en --profile law`"* (or `--profile medicine`, or `other`).
   It adds example ways of working for your profession and tells you what to do next.

Athos needs Python 3; on a Mac it installs itself the first time something asks for it (accept the command line tools).

## Start from a terminal

If you already use `claude`, `codex` or `muse` in a terminal:

```
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos start
```

`athos start` asks your language and profession. Then open `claude`, `codex` or `muse` in your documents' folder: Athos
works the same in all three.

## Day to day

- **Ask as you would ask a colleague.** *"Review this contract against my checklist"*, *"Organise the planning of this
  knee from these studies"*. If Athos has a way of working for it, the AI follows it on its own.
- **The first time, explain.** When a task has no way of working yet, explain to the AI how you do it. At the end,
  Athos asks whether it is worth keeping, and it is there next time.
- **Mark how it went.** After each task three buttons appear: **Good**, **Corrected**, **Failed**. With those marks
  Athos knows which ways of working help you, and on which model.
- **Change them any time.** They are text files in `~/.athos/know-how`. Open them in any editor (or in
  [Obsidian](https://obsidian.md), where they read as a wiki) and write how you do things. Every change keeps the
  previous version.

## The examples it brings

Generic ways of working to start with, **not legal or medical advice**: all of them leave professional decisions to
you and ask the AI to ask instead of deciding.

| Profession | Way of working |
|---|---|
| Law | Build the argument of a brief for its audience (whom to convince, agreed premises, techniques, objections, order) |
| Law | Review a contract against your checklist (clause by clause, a table of comments) |
| Medicine | Organise the planning of a total knee replacement (studies, measurements with their source, the surgeon's decisions) |
| Medicine | Summarise a referral for the visit (every item with its document, gaps) |

Replace them with yours: the best way of working is the one you already use.

## Your data

- **Your ways of working never leave your computer.** Athos has no server and no account; it sends nothing.
- **The AI does see what you show it.** Claude, Codex and Muse process in the cloud the documents you open in the
  session. With client or patient data: anonymise (no names, IDs or birth dates) or use a model that runs on your
  computer, offline (`athos delegate`, with [Ollama](https://ollama.com)).
- **Muse Code:** keep *Contributor* mode off (`/settings`) unless you want Meta to train on your sessions.
- Professional responsibility stays yours: the AI proposes, you decide and sign.
