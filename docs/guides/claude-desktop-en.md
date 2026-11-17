# Athos in Claude Desktop: your know-how in the chat

*Español: [claude-desktop.md](claude-desktop.md)*

This tutorial is for people who use Claude Desktop's **chat** (not the Code tab). No programming and no commands. When
you're done, every time you ask Claude for something:

1. Athos finds **your** way of doing that task and Claude follows it.
2. A small **square** in the conversation tells you whether Athos is collaborating (following one of your ways of
   working) or learning (noting a new one). Nothing else is shown.
3. When a task taught something new, Athos **saves it on its own**, as a way of working of yours, and next time
   Claude already knows it.

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

## 4. Ask for something and watch the square

Write a request that matches one of your ways of working:

> Review this lease: [text]

Before starting, Claude asks Athos, and one short line appears in the conversation:

```
■ Athos is collaborating                      (green)
```

That is all the chat shows: Claude follows your way of working, step by step, out of sight, and answers as always. If
none of your ways of working fits and the task takes several steps, Athos notes them as a new way of working:

```
■ Athos is learning                           (red)
```

When nothing fits and nothing is being noted, nothing is shown. When the task is done the square goes away. It speaks
the language you write in, English or Spanish.

## 5. It learns on its own

When a task of several steps followed none of your ways of working, Athos saves what it taught once it is done, as a
way of working of **yours**: it doesn't announce it or ask. When the task followed one of yours and added steps, it
improves that one instead of creating another (the old version is kept). Before saving, Athos refuses what looks
private (emails, links, ID numbers, folders of your computer, the names of your projects) and anything that repeats a
way of working you already have.

To see what was saved, ask in the chat *"what ways of working do I have?"*, or type `athos list` in a terminal. To
change one, ask Claude, or edit its file (see step 6).

Don't want the chat to save on its own? Add this to `~/.athos/config.json` (create it if it isn't there):

```json
{ "autolearn": { "chat": "off" } }
```

With `"off"` the chat saves nothing, unless you remove that line again.

Want the old, larger panel (each step, stars, a receipt at the end, **Keep beside**)? Add `"ui": "classic"` to the
same file.

**Permissions.** The first time each Athos tool runs, Claude Desktop asks for your permission. Choose **Always
allow** there, or set it once in **Settings → Extensions** (or **Connectors**) → **Athos** → tool permissions. The
names may differ slightly by version.

## 6. See and edit your know-how

Each way of working is a text file in `~/.athos/know-how/` (in Finder: **Go → Go to Folder…** and paste
`~/.athos/know-how`). Open it with any editor. Each step has **When**, **Do** and **Because**.

You can also ask Claude in the chat:

> Show me my ways of working.

> Show me the way of working "review a lease agreement".

## 7. If something doesn't show

| What happens | What to do |
|---|---|
| No square, but Claude follows your way of working | Your Claude Desktop doesn't draw extension panels yet. Athos still works, as text. Update Claude Desktop. |
| Claude doesn't ask Athos | Start a new chat, or ask: *"use my Athos know-how for this"*. In the chat, Claude decides when to use its tools. |
| The square doesn't change while Claude works | It changes each time Claude marks a step. If your Claude Desktop doesn't let the panel ask Athos by itself, you see it at the end of the step. |
| Claude Desktop asks before each Athos tool | Choose **Always allow**, or set it in **Settings → Extensions** (or **Connectors**) → **Athos**. |
| It picks a way of working that doesn't fit | Tell Claude (*"that one doesn't apply"*). To stop it happening, adjust that way of working's **When** in its file. |
| The extension doesn't start | Check the Mac has Python 3 (the first time it may ask to install the command line tools). |

## Privacy

- Your ways of working and Athos's history stay in `~/.athos`, on your computer.
- Athos sends nothing to any server. What you write in the chat is processed by Claude, as always.
- Don't put client data or passwords in a way of working: keep **how** you work, not **what** data you work with.
