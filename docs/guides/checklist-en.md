# Your checklist is know-how: how to keep it and carry it to any AI

*En español: [checklist.md](checklist.md)*

Almost every professional job has a checklist: what a lawyer checks in a contract, what an accountant closes at month
end, what HR prepares before someone starts, what a coach looks at before raising the load. That checklist is the most
valuable thing you can teach an AI, and the easiest to lose: it stays in one chat, and next time you explain it again.

Athos notices it and keeps it.

## How it works

1. **You work from your checklist.** You name it (*"against my checklist"*, *"follow the protocol"*), paste it as a
   list, or the AI opens a file called, say, `month-end-checklist.md`.
2. **Athos notices.** When the task ends it asks the AI whether it is worth keeping, even if the task changed no file
   (a review only reads and answers). The question says why: *"this task followed a checklist, which is know-how worth
   keeping"*.
3. **It becomes a way of working.** A plain text file of yours in `~/.athos/know-how`, one step per item: when it
   applies, what to do and why. You can read and correct it.
4. **Next time it applies by itself.** When a request matches, the AI opens by saying which of your ways of working it
   follows and how it applies to this case, and you don't paste the checklist again.
5. **It works in all your tools.** Claude, Meta's Muse Code, OpenCode and Codex read the same ways of working.

If a way of working already led the task, Athos doesn't ask about the checklist again: the right move is to improve
that piece, and the AI does when the task taught something new.

## A five-minute example

With Athos installed (see [the guide for lawyers](lawyer.md), step 1), in a test folder:

```
Do the October close against my checklist:
- reconcile each bank account with its statement
- invoices issued vs. paid: list those overdue by more than 30 days
- expenses without a receipt: flag them, don't invent them
- a one-page summary for the client, with the three things to resolve
The data is in transactions.csv and invoices.csv.
```

When it ends, Athos asks whether to keep the checklist. Say yes. Next time: *"Do the November close."*

## Writing a good checklist for an AI

- **One item, one action you can check.** *"List invoices overdue by more than 30 days"*, not *"review invoices"*.
- **Say what it must not do.** *"Flag them, don't invent them"*, *"the decision is the client's"*.
- **Include the format you expect.** A table, a one-page summary, specific columns.
- **Add the why when it isn't obvious.** An AI applies a rule better when it knows what it is for.

## What Athos doesn't do

- It doesn't decide for you: it keeps your way of working and the AI follows it, but the professional responsibility
  stays yours.
- It doesn't send your checklists anywhere: they live on your computer.
- It doesn't invent items: it keeps the ones you used. To add one later, edit the file.
