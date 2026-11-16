# Athos in Claude Desktop: your know-how in the chat, with its panel

*Español: [claude-desktop.md](claude-desktop.md)*

This tutorial is for people who use Claude Desktop's **chat** (not the Code tab). No programming and no commands. When
you're done, every time you ask Claude for something:

1. Athos finds **your** way of doing that task and Claude follows it.
2. A **panel** opens in the conversation showing, step by step, how Claude walks through your way of working, the way
   it shows what it's thinking.
3. From the panel you can **adjust a step** or **save the new steps**, and next time Claude already knows them.

Everything stays on your computer, in the `~/.athos` folder, as text you can read and edit. Nothing is sent to any
Athos server.

## 1. What you need

- **Claude Desktop** on a Mac (or Linux), signed in.
- **Python 3**, which macOS already has. The first time it is used, the Mac may ask to install the "command line
  tools": accept.
- Two files, downloaded from Athos's page: [**athos.mcpb**](https://github.com/athos-agent/athos/releases/latest/download/athos.mcpb), the extension for Claude Desktop, and
  [**athos-skill.zip**](https://github.com/athos-agent/athos/releases/latest/download/athos-skill.zip), the skill. If you already have Athos in the terminal, `athos desktop`
  builds both in Athos's `dist/` folder, with your own ways of working in the skill.

## 2. Install (2 minutes)

1. **Double-click** `athos.mcpb`. Claude Desktop opens and shows the extension: press **Install**.
   (You can also drag the file into Claude Desktop → **Settings → Extensions**.)
2. Check that **Athos** is enabled in **Settings → Extensions**.
3. Open a **new chat**. Chats that were already open don't see the extension.

4. Upload the **skill** `athos-skill.zip` in Claude Desktop →
   **Customize → Skills**. Without it, Claude uses Athos only when you name it: in the chat, extension tools stay out
   of sight until the model searches for them, and a request like *"review this contract"* makes it search for
   nothing. The skill tells it what your tasks are. Upload it again when you save new ways of working.
   With `athos desktop --carry <id>,<id>` the skill carries the ways of working you choose, and Claude follows them
   even without calling Athos. Those are then kept in your Claude account too: pick only ones without private data.

To uninstall, disable or remove it in **Settings → Extensions**. Your know-how stays in `~/.athos`.

## 3. Your first way of working

If you already use Athos in Claude Code, Codex, Muse Code or OpenCode, your ways of working are already there: it is
the same folder. Go to step 4.

If you start from scratch, teach Claude a task **once**, with your steps and your criteria. For example:

> Always review lease agreements like this: first identify the parties and the term; then check the rent adjustment
> clause; then the termination clauses; and finally build a table of high, medium and low risks. Review this
> contract: [paste the text, fictional or anonymised].

When it's done, ask:

> Save this as a way of working.

Claude saves it with Athos and tells you its name. From then on, a short request like *"review this lease"* is enough.

## 4. Ask for something and watch the panel

Write a request that matches one of your ways of working:

> Review this lease: [text]

Before starting, Claude asks Athos and a small **Athos panel** opens in the conversation. While Claude follows one
of your ways of working, it shows:

```
■ Athos is collaborating                      (green)
Review a lease agreement
 ✓ Check the parties and the term
 ▶ Check the rent adjustment clause   [ Change this step ]
 ○ Check termination
 ○ Build the risk table
```

- **✓** step done, **▶** the step Claude is on now, **○** what's left. A step that leads to another of your ways of
  working shows its steps indented under it, marked *taken* or *not needed*.
- The panel updates by itself while Claude works.

If none of your ways of working fits the request, Claude notes the steps it takes, and the panel shows them as a new
way of working being drafted:

```
■ Athos is learning                           (red)
 ✓ Read the clauses
 ▶ Check the guarantee
[ Save as a way of working ]
```

When nothing fits and nothing is being drafted, the panel stays empty. When the task is done the square goes away.
The panel speaks the language you write in, English or Spanish.

## 5. Correct and improve without commands

- **[Change this step]**: a field opens. Write how the step Claude is on should change (for example *"also compare
  against the CPI"*) and press **Send**. Athos writes it into that step of your way of working (a new version is
  kept), and it goes to the chat as your message, so Claude goes on with the change.
- **[Save as a way of working]**: shows when there were new steps, also after the task is done. Athos saves them as a
  way of working of yours: a new one named after your request, or new steps added to the one Claude followed.

Only these two buttons save in the chat: Claude itself never saves your ways of working there.

Want the old, larger panel (greeting, stars on each step, a receipt at the end, **Keep beside**)? Add
`"ui": "classic"` to `~/.athos/config.json`.

Claude Desktop may ask you to confirm before a panel message is sent to the chat, or before an Athos tool is used.
That's normal.

## 6. See and edit your know-how

Each way of working is a text file in `~/.athos/know-how/` (in Finder: **Go → Go to Folder…** and paste
`~/.athos/know-how`). Open it with any editor. Each step has **When**, **Do** and **Because**.

You can also ask Claude in the chat:

> Show me my ways of working.

> Show me the way of working "review a lease agreement".

## 7. If something doesn't show

| What happens | What to do |
|---|---|
| No panel, but Claude follows your way of working | Your Claude Desktop doesn't draw extension panels yet. Athos still works, as text. Update Claude Desktop. |
| Claude doesn't ask Athos | Start a new chat, or ask: *"use my Athos know-how for this"*. In the chat, Claude decides when to use its tools. |
| The panel doesn't move while Claude works | It updates each time Claude marks a step. If your Claude Desktop doesn't let the panel ask Athos by itself, you see it at the end of the step. |
| It picks a way of working that doesn't fit | Tell Claude (*"that one doesn't apply"*). To stop it happening, adjust that way of working's **When** in its file. |
| The extension doesn't start | Check the Mac has Python 3 (the first time it may ask to install the command line tools). |

## Privacy

- Your ways of working and the panel's history stay in `~/.athos`, on your computer.
- Athos sends nothing to any server. What you write in the chat is processed by Claude, as always.
- Don't put client data or passwords in a way of working: keep **how** you work, not **what** data you work with.
