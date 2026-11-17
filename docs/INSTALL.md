# Installing Athos

*Español: [INSTALACION.md](INSTALACION.md)*

Pick the way you use AI. The first one needs no terminal and no programming; the others are for people who already
work with Claude Code, a terminal or another coding agent. Every way reads and writes the same folder, `~/.athos`, so
you can start with one and add the others later.

1. [Claude Desktop, regular chat (no terminal)](#1-claude-desktop-regular-chat-no-terminal)
2. [Claude Code, or Claude Desktop's Code tab](#2-claude-code-or-claude-desktops-code-tab)
3. [The `athos` command (terminal, OpenCode, delegate)](#3-the-athos-command-terminal-opencode-delegate)
4. [Codex, Muse Code, OpenCode](#4-codex-muse-code-opencode)
5. [Update](#5-update) · [Uninstall](#6-uninstall) · [Privacy](#7-privacy)

## 1. Claude Desktop, regular chat (no terminal)

**What you need:** Claude Desktop on a Mac or on Linux, signed in, and Python 3.9 or newer. A Mac already has
Python 3; the first time it is used, the Mac may ask to install the "command line tools": accept. Windows is not
supported yet.

1. Download [**athos.mcpb**](https://github.com/athos-agent/athos/releases/latest/download/athos.mcpb) from the latest
   Athos release.
2. **Double-click** it. Claude Desktop opens and shows the extension: press **Install**. (You can also drag the file
   into Claude Desktop → **Settings → Extensions**.)
3. **Quit Claude Desktop** (⌘Q on a Mac) and open it again. Check that **Athos** is enabled in **Settings →
   Extensions**, and open a **new chat**: chats that were already open don't see the extension.
4. Optional, recommended: download
   [**athos-skill.zip**](https://github.com/athos-agent/athos/releases/latest/download/athos-skill.zip) from the same
   release and upload it in **Customize → Skills**. Without it, Claude uses Athos only when you name it; the skill
   tells it what your tasks are. Upload it again when you have saved new ways of working.

**What you will see.** While Claude works on a request, one short line in the conversation:

```
■ Athos is learning                           (red)
■ Athos is collaborating                      (green)
```

Red while Athos notes a new way of working, green while Claude follows one of yours. When nothing applies, or the task
is done, nothing is shown.

**It saves on its own.** When a task of several steps followed none of your ways of working, the chat keeps what it
taught as a way of working **of yours**, without asking; when the task followed one of yours and added steps, it
improves that one (the old version is kept). Before saving, Athos refuses what looks private (emails, links, ID
numbers, folders of your computer, your projects' names). To see what was saved, ask *"what ways of working do I
have?"*. To turn it off, put this in `~/.athos/config.json` (create the file if it isn't there):

```json
{ "autolearn": { "chat": "off" } }
```

**Permissions.** The first time each Athos tool runs, Claude Desktop asks for your permission. Choose **Always
allow**, or set it once in **Settings → Extensions** (or **Connectors**) → **Athos** → tool permissions. The names may
differ slightly by version.

Step by step, with a first example: [the Claude Desktop guide](guides/claude-desktop-en.md).

## 2. Claude Code, or Claude Desktop's Code tab

In Claude Code (in a terminal, or in Claude Desktop's **Code** tab), type:

```
/plugin install athos --marketplace athos-agent/athos
```

Restart Claude Code (or Claude Desktop) when it asks. Then ask Claude to run `athos start`: it asks your language and
profession and adds example ways of working.

**What you will see:** a small square at the right of the prompt's footer, a red ■ "Athos is learning" or a green ■
"Athos is collaborating", and nothing while Athos is idle. Details: [REFERENCE](REFERENCE.md#what-you-see-one-small-square).

## 3. The `athos` command (terminal, OpenCode, delegate)

The command is needed for OpenCode, for working from a terminal, and for `athos delegate` (handing a task to a smaller
or local model). It needs Python 3.11 or newer and nothing else:

```sh
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos start          # language, profession, example ways of working
```

The installer puts Athos in `~/.athos/app` and the command in `~/.local/bin/athos`; if that folder is not on your
`PATH`, it prints the line to add. It never touches your know-how in `~/.athos/know-how`.

## 4. Codex, Muse Code, OpenCode

**Codex:**

```
codex plugin marketplace add athos-agent/athos
codex plugin add athos@athos
```

In the Codex desktop app the plugin brings Athos's hooks; in the Codex CLI add them once with `athos codex install`,
then type `/hooks` in Codex and approve the Athos entries.

**Muse Code:**

```
muse plugins marketplace add athos https://github.com/athos-agent/athos
muse plugins install athos@athos
muse plugins approve athos
```

**OpenCode**, with the `athos` command from step 3:

```
athos opencode install       then restart OpenCode
```

More on each agent: [REFERENCE, Install](REFERENCE.md#install).

## 5. Update

Update the `athos` command and the plugins together: an older Athos reads only the recent part of a history a newer
one has archived. `athos doctor` says which agent is behind and what to do.

| Where | How to update |
|---|---|
| Claude Desktop's chat | download the newest [athos.mcpb](https://github.com/athos-agent/athos/releases/latest/download/athos.mcpb) and install it as in step 1; upload the newest `athos-skill.zip` too |
| Claude Code | `/plugin`, then update athos |
| The `athos` command | run the `curl … install.sh \| sh` line again |
| Codex | `athos codex install` again |
| OpenCode | `athos opencode install` again, then restart OpenCode |
| Muse Code | the three `muse plugins` lines of step 4 again |

## 6. Uninstall

Removing Athos from an agent never deletes your know-how: it stays in `~/.athos`.

| What | How to remove it |
|---|---|
| Claude Desktop's extension | disable or remove **Athos** in **Settings → Extensions**; remove the skill in **Customize → Skills** |
| Claude Code plugin | `/plugin`, then remove athos |
| OpenCode | `athos opencode uninstall`, then restart OpenCode |
| Codex hooks | `athos codex uninstall`; remove the plugin from Codex's plugins too |
| Muse Code | remove the athos plugin from Muse Code's plugins |
| Trajectory subagents in a repository | `athos wiki agents --uninstall` |
| A project's own copy (`.athos/`) | `athos project remove` |
| The `athos` command | `rm -rf ~/.athos/app ~/.local/bin/athos` |

To delete everything, your know-how included, delete the `~/.athos` folder. Copy it out first if you may want it
back: `athos export <folder>`.

## 7. Privacy

Your ways of working, the log of what Athos decided and its settings stay in `~/.athos`, on your computer, as files you
can read and edit. Athos has no server and no account, has no telemetry, and sends nothing off your machine unless you
ask (sharing with the gallery, a hosted model you choose for `athos delegate` or `athos bench`). The AI you work with
still sees what you show it. In a repository others can read, run `athos public on`: Athos then loads and names only
that project's own pieces there and keeps no words of your requests.
