"""Entry point of the `athos` command line: argument parsing, the plugin hooks, and one handler per subcommand.

Everyday commands (`athos <command> --help` has the details of each):

    athos start                        first run: language, profession, example ways of working (no programming needed)
    athos list                         every piece in the store; a filled dot marks the ones allowed to load here
    athos show <id>                    print a piece (inside a session, that also counts as loading it)
    athos save                         read a piece on stdin and store it: new, or a new version of the `id:` it names
    athos save --from-audio FILE       a recording of how you do a task, drafted by Meta's models; saved once you confirm
    athos load [all | project [name] | pieces <id>... | none]   choose what may load; bare, it prints the choice
    athos export <dir>                 a plain copy of every piece into a folder
    athos export --codex [dir]         every piece as a skill Codex reads (default ~/.agents/skills)
    athos codex install|uninstall      wire Athos's hooks into Codex, or unwire them (~/.codex/hooks.json)
    athos import codex [--include-tmp] pull Codex's finished tasks from its session logs (`athos report` does it too)
    athos revert <id> [--to N]         put back a piece's previous version (or version N), as a new version
    athos library [--port N]           every way of working at a glance, as a local page (127.0.0.1)
    athos watch                       a live panel: one bar per agent for this project's know-how (for Codex)
    athos watch --web                 the trail panel as a local page, beside Muse Code, Codex or OpenCode
    athos export --muse [<folder>]    the same skills for Muse Code; `athos import muse` records its tasks
    athos delegate <id> "<request>"    hand a task you already master to a small model on this machine (Ollama),
                                       recorded under the `local` platform
    athos delegate <id> "<request>" --backend meta   the same on Meta Model API (muse-spark-1.3), recorded as `meta`
    athos delegate <id> "<request>" --by-step   statement by statement, each on its `**Model:**` (local, meta, …)
    athos route <id> [--apply]         per step, which models ran it and how those tasks ended; --apply writes the
                                       cheapest one that never ended corrected or failed
    athos mark g|c|f [task]            how the last task went, in your words: good, corrected or failed
    athos report [--json]              the value each piece and each model adds to your own work
    athos mcp                          your know-how as an MCP server (stdio), for Claude Desktop's chat
    athos wiki [--json]                rebuild Index.md and check the links between pieces (pages of a wiki)
    athos export --dataset FILE        your statements and marked tasks as JSON lines (evals, training data)
    athos export --guild <folder> [--as NAME] [--piece ID]   pieces + per-statement counts, for colleagues to merge
    athos merge <id> <file-or-folder>... [--apply] [--backend ollama|meta --model M]   one team version of a piece
    athos wiki agents [--install]      the trajectory subagents (a walk across pages); --install puts them in
                                       ~/.claude/agents and keeps them in step with every save
    athos bench <case|all> --agents claude,meta [--runs 5] [--without] [--max-usd 5]   the same task on each agent,
                                       checked by what it left behind; `athos bench --list`, `athos bench report`
    athos bench route [--router lexical,hybrid] [--scale 300] [--from-store]   how well the router picks the know-how
    athos embed [on|off] [--model M]   also load know-how by meaning (local embeddings, Ollama); off by default
    athos test <id> [--backend meta]   re-check a piece against the corrections you made on it before
    athos shadow [--limit N] | on|off  compare a cheaper model with the answers you approved (Ollama by default)
    athos status [--json]              one summary line, or (--json) everything the status line and band draw
    athos doctor [--json]              which Athos each agent runs (Claude Code, Desktop, Codex, OpenCode, Muse Code,
                                       the terminal) and which are behind the newest
    athos gallery build [--out DIR]    gallery.json and index.html from the gallery's pages
    athos add <id|url> [--dry-run]     add a way of working (and the pages it calls) from Athos's public gallery
    athos hook <event>                 called by the agents' hook configuration; the event arrives as JSON on stdin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

from athos import capture, cases, control, edits, eval as ev, load, paths, replay, session, store, trail

ROOT = Path(__file__).resolve().parent.parent      # the Athos installation this module belongs to
ME = ROOT / "bin" / "athos"                         # its launcher: hooks, shims and printed commands point here
STEP_SINCE = (0, 1, 75)                 # the first `athos step` that answers ok inside a sandbox (Muse Code)


def _cmd() -> str:
    """The spelling of the command in every line an agent runs or a person reads.

    Plain `athos` whenever the shell resolves it to this installation (the plugin puts its bin on PATH, the installer
    adds ~/.local/bin) or to one recent enough; otherwise the quoted full path to ME, which works anywhere but also
    puts the person's user name on screen."""
    if not ME.exists():
        return "athos"
    on_path = shutil.which("athos")
    if on_path and _runs_me(on_path):
        return "athos"
    return shlex.quote(str(ME))


def _runs_me(path: str) -> bool:
    """Whether the `athos` on PATH is this installation: the plugin's own bin, or a launcher pointing at it. An older
    install on PATH (~/.local/bin → ~/.athos/app) lacked `athos step`, so Muse Code's model called a command that
    didn't exist (2026-10-30)."""
    if os.path.realpath(path) == os.path.realpath(ME):
        return True
    try:
        with open(path, errors="ignore") as fh:
            head = fh.read(2000)
    except OSError:
        return False
    if str(ME) in head or os.path.realpath(ME) in head:
        return True
    # Another installation with every command the agent runs, as it runs it (`athos step` answers ok in a sandbox
    # since 0.1.75), will do:
    # plain `athos` keeps the person's user name out of every command line on screen, and a plugin update no longer
    # brings the full path back while the terminal's athos is one version behind (2026-10-30).
    target = re.search(r'"([^"]+/bin/athos)"', head)
    root = Path(target.group(1)).parents[1] if target else Path(os.path.realpath(path)).parents[1]
    return _version(root) >= STEP_SINCE


def _version(root: Path) -> tuple:
    try:
        v = json.loads((root / ".claude-plugin" / "plugin.json").read_text())["version"]
        return tuple(int(x) for x in v.split("."))
    except (OSError, ValueError, KeyError):
        return (0,)


def _fail(message: object) -> int:
    """Report a command's failure on stderr and give back its exit status."""
    print(message, file=sys.stderr)
    return 1


# ==================================================================== which session a working folder belongs to
#
# A hook knows its session; a command typed later (`athos save`, `athos mark`) only knows the folder it runs in. The
# hooks therefore leave, per folder, a small note naming the session that is working there.

def _folder_note(cwd: str) -> Path:
    """Where the note for a folder lives: sessions/by-cwd/<first 16 hex digits of the sha1 of its real path>.json."""
    digest = hashlib.sha1(os.path.realpath(cwd).encode()).hexdigest()
    return paths.sessions() / "by-cwd" / f"{digest[:16]}.json"


def _remember_session(event: dict) -> None:
    """Point the event's folder at the event's session (and transcript), when the event names both."""
    folder, sid = event.get("cwd"), event.get("session_id")
    if not (folder and sid):
        return
    note = _folder_note(folder)
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({"session_id": sid, "transcript_path": event.get("transcript_path")}))


def _current_session(cwd: str) -> dict:
    """The session last noted for this folder ({} when there is no readable note)."""
    try:
        found = json.loads(_folder_note(cwd).read_text())
    except (OSError, json.JSONDecodeError):
        found = None
    return found if isinstance(found, dict) else {}


def _folder_session_id(event: dict, sid: str | None) -> str | None:
    """The session of the request running in the event's folder, falling back to `sid`. Muse Code gives every hook
    call a fresh session id, so a tool or stop event must find its task through the folder."""
    if not event.get("cwd"):
        return sid
    return _current_session(event["cwd"]).get("session_id") or sid


# ==================================================================== hooks
def _quietly(fn, *args):
    """Cases and shadowing are extras: their failure must not cost the person the capture or the load."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        print(f"athos: {fn.__module__}.{fn.__name__}: {e}", file=sys.stderr)
        return None


def _add_context(hook_event: str, text: str) -> None:
    """Answer the hook with extra context for the model, in the shape Claude Code (and the agents copying it) read."""
    answer = {"hookSpecificOutput": {"hookEventName": hook_event, "additionalContext": text}}
    print(json.dumps(answer))


def _on_session_start(event: dict, platform: str) -> None:
    """A session opens: the know-how that may load for it goes in as context (nothing at all on an empty store)."""
    intro = load.on_session_start(event, _cmd())
    if intro:
        _add_context("SessionStart", intro)


def _on_prompt(event: dict, platform: str) -> None:
    """The person sent a request. A button's request is answered on its own; any other one starts a task, and the
    pieces it calls for (plus a rule learned from the person's hand edits) go in as context."""
    prompt, sid = event.get("prompt", ""), event.get("session_id")
    if capture.is_save_prompt(prompt):
        # The person pressed [Save]: the save belongs to the task that just ended, so no new task starts
        # and nothing loads; the offer is spent.
        if sid:
            session.update(sid, offer=None)
        _add_context("UserPromptSubmit", capture.SAVE_CONTEXT.format(cmd=_cmd()))
        return
    from athos import gallery
    if ref := gallery.requested(prompt):
        # The person pasted [Use in Athos] from the gallery: the agent adds it, in sight, with one command.
        _add_context("UserPromptSubmit", (
            f"The person asked to add {ref!r} from Athos's gallery: run `{_cmd()} add {shlex.quote(ref)}` "
            "now (it downloads only from the athos-agent/athos repository and never overwrites a page they "
            "have), then tell them in one short line, in their language, what was added."))
        return
    if capture.is_adjust_prompt(prompt):
        # The person pressed [Adjust] on a step of the pane and wrote the change: it improves that piece.
        # [Keep this rule] is an adjust too: the edit it names is kept, and its button goes away.
        if sid:
            _quietly(edits.kept, sid, prompt)
        _add_context("UserPromptSubmit", capture.ADJUST_CONTEXT.format(cmd=_cmd()))
        return
    from athos import start
    start.note_language(prompt)
    if sid:
        # After `athos mark c`, these words are the correction the last task needed (athos/cases.py).
        _quietly(cases.note_prompt, sid, prompt)
        ev.infer_mark(sid, prompt)     # before the new task replaces it
    ev.task_start(event, platform)
    capture.note_request(event)
    context = load.on_prompt(event, _cmd())
    if capture.enabled():
        # The person's hand edits of files the agent wrote: a rule of their way of working, offered once.
        learned = edits.on_prompt(event, _cmd())
        context = (context + "\n" + learned) if context and learned else (context or learned)
    if context:
        _add_context("UserPromptSubmit", context)


def _on_tool(event: dict, platform: str) -> None:
    """A tool call ended: it is counted, drawn on the trail, and checked for files the person may edit later."""
    capture.count_tool(event)
    trail.on_tool(event)
    sid = event.get("session_id", "default")
    if not session.load(sid).get("task_id"):     # Muse Code: this folder's task
        sid = _folder_session_id(event, sid)
    if capture.enabled():
        edits.on_tool(event, sid)


def _on_stop(event: dict, platform: str) -> None:
    """The agent finished its turn: close the task, then offer (or ask the model) to save what it learned."""
    rec = ev.task_end(event)
    _quietly(cases.on_task_end, event, rec)
    _quietly(replay.maybe_spawn, ME)          # background shadowing, when the person turned it on
    sid = event.get("session_id")
    if sid and not session.load(sid).get("trail"):
        sid = _folder_session_id(event, sid)
    if sid:
        trail.finish(sid)
    # A person at an interactive Claude Code session gets a [Save] button above the prompt instead of a
    # line asking the model; a `claude -p` run (CLAUDE_CODE_ENTRYPOINT=sdk-…) has no band, so it is asked.
    interactive = platform == "claude-code" and not os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk")
    decision = capture.stop_decision(event, _cmd(), offer=interactive and os.environ.get("ATHOS_ASK") != "model")
    if not decision:
        return
    if platform == "claude-code":
        # Claude Code labels a Stop block "Stop hook error"; the same request as context reads as feedback.
        _add_context("Stop", decision["reason"])
    else:
        print(json.dumps(decision))


_HOOK_HANDLERS = {"session-start": _on_session_start, "prompt": _on_prompt, "tool": _on_tool, "stop": _on_stop}


def hook(event_name: str, platform: str = "claude-code") -> int:
    """Handle one hook event read from stdin. It always exits 0: a failure is written to stderr and the person's
    session carries on untouched."""
    try:
        if platform == "claude-code" and os.environ.get("MUSE_PLUGIN_ID"):
            platform = "muse-code"                  # Muse Code runs the Claude Code plugin as it is, and says so
        event = json.loads(sys.stdin.read() or "{}")
        # The folder remembers the session of the request: Muse Code gives each hook call its own session id, so a
        # tool hook would point the folder at a session with no task, and `athos step` lost its task (2026-10-30).
        if event_name in ("session-start", "prompt"):
            _remember_session(event)
        if event.get("session_id"):
            session.update(event["session_id"], platform=platform)
        _HOOK_HANDLERS[event_name](event, platform)
    except Exception as problem:  # noqa: BLE001 — whatever it is, the session must not see it
        print(f"athos hook {event_name}: {problem}", file=sys.stderr)
    return 0


# ==================================================================== commands
#
# Each `cmd_*` handler receives the parsed arguments. A handler returns an exit status when it has one to give (1 on
# failure, through `_fail`); one that simply runs to its end has succeeded, and `main` turns that into 0.

def _here() -> tuple[str, dict]:
    """The folder a command runs in, and the session the hooks last noted for it."""
    folder = os.getcwd()
    return folder, _current_session(folder)


def cmd_list(args: argparse.Namespace) -> int | None:
    """Every piece, most recently used first; ● marks the pieces allowed to load in this folder, ○ the others."""
    from athos import start
    pieces = sorted(store.all_pieces(), key=lambda p: p.last_used, reverse=True)
    enabled = {p.id for p in load.enabled(os.getcwd())}
    where, choice = paths.know_how(), control.describe()
    if start.lang() == "es":
        print(f"{len(pieces)} forma(s) de trabajar en {where} · se cargan: {choice}")
    else:
        print(f"{len(pieces)} piece(s) in {where} · loading: {choice}")
    for p in pieces:
        dot = "●" if p.id in enabled else "○"
        print(f"{dot} {p.id}  v{p.version}  {p.title}")
        print(f"    when: {p.when}  · last used {p.last_used}")


def cmd_show(args: argparse.Namespace) -> int | None:
    """Print one piece as stored. Run inside a session, reading it counts as loading it there."""
    piece = store.get(args.id)
    if piece is None:
        return _fail(f"no piece {args.id}")
    sid = _here()[1].get("session_id")
    if sid:
        load.mark_loaded(sid, [piece.id])
    sys.stdout.write(store.render(piece))


def _unwritable_store_hint() -> str:
    """Why a save failed inside a sandbox, and the Codex setting that lets the store be written."""
    home = paths.home()
    return (f"not saved: {home} is read-only for this session. Codex's workspace-write sandbox can be told to allow "
            f"it with `-c 'sandbox_workspace_write.writable_roots=[\"{home}\"]'`, or with the same key in "
            "~/.codex/config.toml.")


def cmd_save(args: argparse.Namespace) -> int | None:
    """Store the piece written on stdin: a new page, or a new version of the page its `id:` names. The lines printed
    afterwards are read by the model, which reports them and fixes what the save broke in the wiki. With
    `--from-audio`, the piece is a recording the person dictated, drafted by Meta's models (athos/adapters/meta/voice)."""
    if getattr(args, "from_audio", None):
        return _save_from_audio(args)
    return _save(sys.stdin.read())


def _save_from_audio(args: argparse.Namespace) -> int | None:
    """Transcribe the recording, draft it as a piece, show the draft, and save it only once the person says yes."""
    from athos.adapters.meta import voice
    try:
        print(f"transcribing {Path(args.from_audio).name} with {voice.TRANSCRIBE_MODEL}…", file=sys.stderr)
        transcript = voice.transcribe(Path(args.from_audio), args.lang)
        print(f"drafting the way of working with {voice.DRAFT_MODEL}…", file=sys.stderr)
        draft = voice.draft(transcript, args.lang)
    except (voice.VoiceError, PermissionError, OSError) as refused:
        return _fail(f"not saved: {refused}")
    if not args.yes and not sys.stdin.isatty():      # nobody to ask: show the draft and how to keep it
        print(f"Draft, not saved yet. To save it, run:\n\n{_cmd()} save <<'EOF'\n{draft.rstrip()}\nEOF")
        return None
    print(draft.rstrip() + "\n")
    if not args.yes:
        try:
            answer = input("Save this way of working? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes", "s", "si", "sí"):
            print("not saved.")
            return None
    return _save(draft)


def _save(text: str) -> int | None:
    folder, noted = _here()
    sid = noted.get("session_id", "default")
    try:
        piece, diff = capture.save_text(text, sid, folder, noted.get("transcript_path"))
    except (PermissionError, ValueError) as refused:          # a sandboxed store, or a page that doesn't parse
        return _fail(_unwritable_store_hint() if isinstance(refused, PermissionError) else f"not saved: {refused}")
    if not diff:
        print(f"saved {piece.id} ({piece.path})")
    else:
        n = capture.recheck(piece.id)
        print(f"improved {piece.id} → v{piece.version} ({piece.path})"
              + (f" · {capture.recheck_words(n)}" if n else "") + f"\n\n{diff}")
        if n:                                      # the model reads this: it offers the re-check in the person's words
            print(f"\nThe person corrected this piece {n} time(s) before. Offer them, in one line and in their "
                  f"language, to re-check that the new version respects those corrections: `{_cmd()} test {piece.id}` "
                  f"(a local model; nothing leaves the machine).")
    wiki = session.load(sid).get("wiki") or {}        # what the save left in the wiki, read after it
    broken = wiki.get("broken") or []
    if broken:                                     # the wiki improves in the same turn: the model fixes what it broke
        print("\nwiki: links that lead nowhere; fix them with another `athos save` (id: of the page):\n  "
              + "\n  ".join(broken[:10]))
    same = wiki.get("overlaps") or []
    if same:                                       # possible contradictions: the model checks them now
        print("\nwiki: other pages say what to do at the same moment. Check they agree; if one is wrong or "
              "outdated, fix it with `athos save` (id: of that page), or link them if they apply together:\n  "
              + "\n  ".join(same[:10]))


def cmd_wiki(args) -> int:
    from athos import wiki
    if args.action == "agents":
        target = Path(args.dir).expanduser() if args.dir else Path.home() / ".claude" / "agents"
        flag = paths.home() / "agents-install"
        if args.uninstall:
            for f in target.glob(f"{wiki.AGENT_PREFIX}*.md"):
                if "Generated by Athos" in f.read_text():
                    f.unlink()
            flag.unlink(missing_ok=True)
            print(f"trajectory agents removed from {target}")
            return 0
        r = wiki.rebuild()
        if args.install:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(str(target))
            n = wiki.install_agents(target)
            print(f"{n} trajectory agent(s) in {target}; Athos keeps them in step with your know-how from now on "
                  f"(`athos wiki agents --uninstall` to stop)")
            return 0
        for name in r["agents"]:
            print(f"{wiki.agents_dir() / name}")
        if not r["agents"]:
            print("no trajectories yet: pages become one when their statements link to another page")
        return 0
    r = wiki.rebuild()
    lint = r["lint"]
    if args.json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
        return 0
    print(f"{lint['pages']} pages · {lint['statements']} statements · {lint['links']} links between pages · "
          f"{len(r['agents'])} trajectory agent(s)\nindex: {paths.know_how() / wiki.INDEX}")
    for label, key in (("links that lead nowhere", "broken"), ("statement ids used twice", "duplicate_ids"),
                       ("pages still in the old numbered format", "old_format")):
        if lint[key]:
            print(f"\n{label} ({len(lint[key])}):\n  " + "\n  ".join(lint[key][:20]))
    if r.get("stale"):
        print(f"\ncandidates to retire, from your recorded tasks (review them; nothing is removed) "
              f"({len(r['stale'])}):\n  " + "\n  ".join(r["stale"][:20]))
    return 0 if not (lint["broken"] or lint["duplicate_ids"]) else 1


def cmd_load(args: argparse.Namespace) -> int | None:
    """With no words, say what may load; otherwise set it: `all`, `project [name]`, `pieces <id>...` or `none`."""
    if args.what:
        mode, *values = args.what
        try:
            chosen = control.set_selection(mode, values)
        except ValueError as refused:
            return _fail(refused)
        enabled = len(load.enabled(os.getcwd()))
        print(f"loading: {control.describe(chosen)} ({enabled} piece(s) enabled)")
    else:
        print(f"loading: {control.describe()}")


def _export_guild(args: argparse.Namespace) -> int | None:
    from athos import guild
    dest = Path(args.guild).expanduser()
    try:
        ids = guild.export(dest, args.piece, args.owner)
    except LookupError as e:
        return _fail(e)
    print(f"{len(ids)} piece(s) with their stats to {dest}, for your colleagues' `athos merge`. The stats are "
          "counts only (how many of your tasks walked each step, and how you marked them): no request, no client.")


def _export_dataset(args: argparse.Namespace) -> int | None:
    from athos import wiki
    rows = wiki.dataset()
    dest = Path(args.dataset).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    n_st = sum(r["kind"] == "statement" for r in rows)
    print(f"{n_st} statements and {len(rows) - n_st} marked tasks to {dest} (JSON lines). It holds your requests "
          "as you typed them: it stays on this machine unless you move it.")


def _export_skills(args: argparse.Namespace) -> int | None:
    """Each piece as an agent skill. Muse Code reads the same ~/.agents/skills folder Codex does."""
    from athos.adapters import codex
    target = codex.skills_dir() if not args.dir else Path(args.dir).expanduser()
    count, stale = codex.export_skills(target)
    who = "Codex and Muse Code" if args.muse else "Codex"
    print(f"exported {count} piece(s) as skills for {who} to {target}" + (f" (removed {stale} stale)" if stale else ""))


def _export_folder(folder: str | None) -> int | None:
    """A plain copy of every piece file, for a backup or to read elsewhere."""
    if folder:
        target = Path(folder).expanduser()
        print(f"exported {store.export(target)} piece(s) to {target}")
        return None
    return _fail("name a folder to export to")


def cmd_export(args: argparse.Namespace) -> int | None:
    """Take the know-how out of the store, in the form the flags ask for (a plain folder copy without any)."""
    if args.guild:
        return _export_guild(args)
    if args.dataset:
        return _export_dataset(args)
    if args.codex or args.muse:
        return _export_skills(args)
    return _export_folder(args.dir)


def cmd_merge(args) -> int:
    from athos import guild
    import urllib.error
    chat_fn, model = None, None
    if args.model or args.backend:                # a model only when asked for; meta sends the texts to Meta Model API
        from athos import delegate
        if args.backend == "meta":
            from athos.adapters import meta
            chat_fn, model = meta.chat, args.model or meta.DEFAULT_MODEL
        else:
            chat_fn, model = delegate.chat, args.model or delegate.DEFAULT_MODEL
    try:
        variants = guild.find_variants(args.sources, args.as_id or args.id)
        if not variants:
            print(f"no {args.as_id or args.id}.md in {', '.join(args.sources)} (a colleague's copy with another id: "
                  "--as-id <their id>)", file=sys.stderr)
            return 1
        r = guild.merge(args.id, variants, model=model, chat_fn=chat_fn)
    except (LookupError, FileNotFoundError, PermissionError) as e:
        print(e, file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"cannot reach the model ({getattr(e, 'reason', e)}); without --model the merge needs none.",
              file=sys.stderr)
        return 1
    print(guild.summary(r))
    if not r["changed"]:
        return 0
    if args.apply:
        piece, _ = guild.apply(r)
        print(f"\nsaved as {piece.id} v{piece.version}; v{r['version']} stays in its history (`athos revert "
              f"{piece.id}` puts it back).")
    else:
        dest = guild.write_proposal(r, Path(args.out).expanduser() if args.out else None)
        print(f"\nproposal in {dest} (nothing changed yet). Apply it with the same command and --apply.")
    return 0


def cmd_codex(args: argparse.Namespace) -> int | None:
    """Wire Athos's hooks into Codex (keeping a backup of the hooks file it replaces), or take them out."""
    from athos.adapters import codex
    if args.action == "uninstall":
        print("Athos hooks removed from Codex" if codex.uninstall() else "no Codex hooks file")
        return None
    hooks_file, backup = codex.install(ROOT)
    home = paths.home()
    note = f" (the previous one is kept as {backup.name})" if backup else ""
    print(f"Athos hooks added to {hooks_file}{note}")
    print("Codex trusts new hooks only once you approve them: type /hooks inside Codex and accept the Athos entries.")
    print(f"Codex's workspace-write sandbox also needs {home} among its writable roots for saves to reach the "
          "store; in ~/.codex/config.toml:\n\n"
          f"  [sandbox_workspace_write]\n  writable_roots = [\"{home}\"]")


def cmd_opencode(args) -> int:
    from athos.adapters import opencode
    if args.action == "install":
        from athos.adapters import codex
        # The shim Codex's hooks use: it runs the newest Claude Code plugin at each call and falls back to this copy.
        # Baking in the `athos` on PATH left OpenCode on install.sh's 0.1.60 while the plugin was at 0.1.73, so none of
        # the newer features reached it (2026-10-31).
        f = opencode.install(codex.write_shim(ME.parents[1]))
        print(f"Athos plugin written to {f}; restart OpenCode to load it.")
        return 0
    print("Athos plugin removed from OpenCode" if opencode.uninstall() else "no Athos plugin in OpenCode")
    return 0


def cmd_project(args) -> int:
    from athos import project
    root = Path.cwd()
    if args.action == "remove":
        gone = project.remove(root)
        print("removed " + ", ".join(gone) if gone else "no Athos know-how in this project")
        return 0
    try:
        r = project.sync(root, ids=args.piece, everything=args.all, commit=args.commit)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{len(r['pieces'])} page(s), {len(r['agents'])} subagent(s) and {len(r['skills'])} skill(s) in "
          f"{r['root']}; Claude Code, Codex, Muse Code and OpenCode read them from this project"
          + (" (kept out of git: --commit to share it)" if r["ignored"] else "") + ".")
    return 0


def cmd_dismiss(args) -> int:
    """[Didn't apply]: the piece loaded for the current task did not fit; its words won't load it again."""
    state = session.load(_current_session(os.getcwd()).get("session_id") or "default")
    shared = (state.get("task_why") or {}).get(args.id)
    if shared is None:
        print(f"{args.id} was not loaded for the last task here", file=sys.stderr)
        return 1
    load.dismiss(args.id, shared)
    ev.append({"type": "misfire", "task_id": state.get("task_id"), "piece": args.id, "words": shared,
               "at": ev._iso(ev.now())})
    from athos import start
    print(f"«{args.id}» no se cargará más por: {', '.join(shared)}" if start.lang() == "es" else
          f"{args.id} won't load again on: {', '.join(shared)}")
    return 0


def cmd_revert(args: argparse.Namespace) -> int | None:
    """Bring back an earlier version of a piece. The history only grows: the old text returns as a new version."""
    try:
        piece = store.revert(args.id, args.to)
    except (KeyError, FileNotFoundError) as missing:
        return _fail(f"cannot revert: {missing}")
    print(f"reverted {piece.id} (now v{piece.version})")


def _delegation_backend(args):
    """(platform, model, chat function) for a delegation: Ollama on this machine, recorded as `local`, unless
    --backend meta sends it to Meta Model API."""
    from athos import delegate
    if args.backend != "meta":
        return "local", args.model or delegate.DEFAULT_MODEL, delegate.chat
    from athos.adapters import meta
    return "meta", args.model or meta.DEFAULT_MODEL, meta.chat


def _unreachable(platform: str, model: str, reason: object) -> str:
    """What to say when the model's server did not answer at all, with the way to start it when it is local."""
    if platform == "meta":
        return f"cannot reach Meta Model API ({reason})."
    from athos import delegate
    return (f"cannot reach Ollama at {delegate.host()} ({reason}). Start it (`ollama serve`) and pull the "
            f"model (`ollama pull {model}`).")


def _delegation_lines(args, r: dict, platform: str, model: str) -> str:
    """The result the person (or the calling agent) reads: the model's summary, its cost, and how to mark the task."""
    tokens = f"{r['tokens']['total']:,} tokens"
    if not args.by_step:
        return (f"\n{r['summary'].strip()}\n\n{platform} / {model}: {r['duration_s']} s, {r['steps']} step(s), "
                f"{tokens} · task {r['task_id']}. Mark it with `athos mark g|c|f`.")
    steps = "\n".join(f"  #{d['id']:24} {d['platform']} / {d['model']}: {d['duration_s']} s, "
                      f"{d['tokens']['total']:,} tokens" for d in r["steps"])
    return (f"\n{r['summary'].strip()}\n\n{steps}\n{r['duration_s']} s, {tokens} · task "
            f"{r['task_id']}. Mark it with `athos mark g|c|f`; `athos route {args.id}` learns from the marks.")


def cmd_delegate(args: argparse.Namespace) -> int | None:
    """Run a task the person already masters on a smaller model, following one piece, and record it as a task."""
    from athos import delegate
    import urllib.error
    platform, model, chat_fn = _delegation_backend(args)
    try:
        if args.by_step:
            r = delegate.by_step(args.id, args.request, (platform, model), yes=args.yes, max_steps=args.max_steps,
                                 allow_hosted=platform == "meta" or args.allow_meta)
        else:
            r = delegate.delegate(args.id, args.request, model, yes=args.yes, max_steps=args.max_steps,
                                  chat_fn=chat_fn, platform=platform)
    except (LookupError, PermissionError, ValueError) as refused:
        return _fail(refused)
    except urllib.error.HTTPError as answered:            # the server answered, with an error
        return _fail(_model_error(answered, platform, model))
    except urllib.error.URLError as silent:               # nothing answered
        return _fail(_unreachable(platform, model, silent.reason))
    print(_delegation_lines(args, r, platform, model))


def cmd_route(args) -> int:
    from athos.delegate import route
    try:
        if args.apply:
            p, r = route.apply(args.id)
        else:
            p, r = None, route.table(args.id)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(route.render(r))
    if args.apply:
        print(f"\nwrote the suggested models into {p.id} (now v{p.version}; `athos revert {p.id}` undoes it)" if p
              else "\nnothing to write: no suggestion differs from the piece.")
    return 0


def import_other_agents() -> list[str]:
    """Record the tasks Codex and Muse Code ran since the last look, from their own session logs. Returns what failed,
    so a broken log never stops a mark or a report."""
    from athos.adapters import codex, muse
    failed = []
    for name, mod in (("Codex", codex), ("Muse Code", muse)):
        try:
            mod.import_sessions()
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}: {e}")
    return failed


_VERDICT_ES = {"ok": "salió bien", "corrected": "lo corregí", "failed": "falló"}


def cmd_mark(args: argparse.Namespace) -> int | None:
    """Record the person's verdict (g good, c corrected, f failed) on a task: the one named, else the last one here."""
    folder, noted = _here()
    named = args.task or None                          # an empty id means the last task, as no id does
    if named is None:
        import_other_agents()                          # a Codex or Muse Code task just finished here may be the one meant
    try:
        task_id, result = ev.mark(args.result, named, noted.get("session_id"), paths.project_of(folder))
    except (ValueError, LookupError) as refused:
        return _fail(refused)
    from athos import start
    spanish = start.lang() == "es"
    # The plugin's pane shows the English line as it is (hooks/ui.tsx): keep its wording.
    print(f"tarea marcada: {_VERDICT_ES.get(result, result)}" if spanish else f"task {task_id} marked {result}")


def cmd_import(args: argparse.Namespace) -> int | None:
    """Record the tasks Codex or Muse Code ran, from that agent's own session logs."""
    from athos.adapters import codex, muse
    name, adapter = ("Muse Code", muse) if args.platform == "muse" else ("Codex", codex)
    folder = Path(args.sessions).expanduser() if args.sessions else None
    got = adapter.import_sessions(folder, args.include_tmp)
    print(f"{name}: {got['imported']} task(s) imported from {got['files']} session file(s) ({got['skipped']} skipped)")


def cmd_report(args: argparse.Namespace) -> int | None:
    """What each piece and each model adds to the person's work, as text or (--json) as the numbers themselves."""
    for failed in import_other_agents():              # Codex's and Muse Code's tasks are always in the report
        print(f"(sessions not imported: {failed})", file=sys.stderr)
    numbers = ev.report()
    print(json.dumps(numbers, indent=1, ensure_ascii=False) if args.json else ev.render(numbers))


def cmd_bench(args) -> int:
    from athos import bench
    all_cases = bench.cases()
    if args.list or not args.target:
        for name, c in all_cases.items():
            print(f"{name:<15} {c['domain']:<8} {c['title']}: \"{c['request']}\"")
        return 0
    if args.target in ("transfer", "transfer-report"):
        return _bench_transfer(args, all_cases)
    if args.target == "route":
        return _bench_route(args)
    if args.target == "report":
        r = bench.report()
        print(json.dumps(r, indent=1, ensure_ascii=False) if args.json else bench.render(r))
        return 0
    names = list(all_cases) if args.target == "all" else args.target.split(",")
    agents = args.agents.split(",")
    bad = [n for n in names if n not in all_cases] + [a for a in agents if a not in bench.AGENTS]
    if bad:
        print(f"unknown: {', '.join(bad)}. Cases: {', '.join(all_cases)}. Agents: {', '.join(bench.AGENTS)}.",
              file=sys.stderr)
        return 1
    models = dict(m.split("=", 1) for m in args.model or [])
    bench.run(names, agents, args.runs, with_piece=not args.only_without, without_piece=args.without or
              args.only_without, models=models, max_usd=args.max_usd, keep=args.keep)
    print(f"\n{bench.render(bench.report([r for r in bench.load_results() if r['case'] in names]))}")
    return 0


def _ollama_host() -> str:
    from athos import delegate
    return delegate.host()


def _bench_route(args) -> int:
    """The router's own bench: synthetic cases on throwaway stores, or the person's good tasks (read-only)."""
    from athos.bench import route
    from athos.load import embed
    routers = args.router.split(",")
    if set(routers) - {"lexical", "hybrid"}:
        print("--router: lexical, hybrid (comma-separated)", file=sys.stderr)
        return 1
    model = args.embed_model or embed.chosen_model()
    if "hybrid" in routers:
        try:
            embed.ollama(["ping"], model, timeout=60)
        except Exception as e:
            print(f"hybrid needs {model} in Ollama at {_ollama_host()} ({e}): `ollama pull {model}`",
                  file=sys.stderr)
            return 1
    if args.from_store:
        out = {}
        for r in routers:
            meaning = False
            if r == "hybrid":                    # the index in memory: nothing is written to the person's home
                idx = embed.refresh(load.enabled(), model=model, write=False)
                meaning = lambda p, ps, idx=idx: embed.scores(p, ps, model=model, index=idx, spawn=False)
            out[r] = route.from_store(meaning)
            out[f"{r}, per project"] = route.from_store(meaning, scoped=True)
        print(json.dumps(out, indent=1) if args.json else
              "\n\n".join(f"[{r}] {route.render_store(x)}" for r, x in out.items()))
        return 0
    rows = route.run(routers, scale=args.scale, model=model)
    print(json.dumps(rows, indent=1) if args.json else route.render(rows) +
          (f"\nhybrid: {model} through Ollama, request embedded under {embed.BUDGET_S * 1000:.0f} ms."
           if "hybrid" in routers else ""))
    return 0


def cmd_embed(args) -> int:
    """`athos embed on|off`: also load know-how by meaning, with a local embedding model (Ollama)."""
    from athos.load import embed
    if args.refresh:                              # the background job the prompt hook starts: quiet, then unlocked
        try:
            embed.refresh(load.enabled(), model=embed.chosen_model())
        except Exception as e:
            print(e, file=sys.stderr)
            return 1
        finally:
            embed._lock().unlink(missing_ok=True)
        return 0
    if args.action in ("on", "off"):
        s = embed.set_embed(args.action == "on", args.model)
        if not s["on"]:
            print("Loading by meaning is off: Athos loads know-how by the request's words only.")
            return 0
        model = embed.chosen_model()
        try:
            t0 = time.time()
            embed.ollama(["hello"], model, timeout=60)   # the model answers (and is loaded) even with no piece yet
            idx = embed.refresh(load.enabled(), model=model)
            print(f"Loading by meaning is on ({model}, local Ollama): {len(idx)} pieces indexed in "
                  f"{time.time() - t0:.1f} s. Nothing leaves this machine.")
        except Exception as e:
            print(f"Loading by meaning is on, but {model} doesn't answer at {_ollama_host()} ({e}). Until it "
                  f"does, Athos loads by words only, as before. `ollama pull {model}` gets the model.")
        return 0
    s, model = embed.settings(), embed.chosen_model()
    pieces = load.enabled()
    fresh = len(pieces) - len(embed.stale(pieces, embed.load_index(model), model))
    print(f"Loading by meaning: {'on' if s.get('on') else 'off'} · {model} · {fresh}/{len(pieces)} pieces indexed"
          f" · `athos embed on|off`")
    return 0


def _bench_transfer(args, all_cases: dict) -> int:
    from athos import bench
    from athos.bench import transfer
    if not args.case or "teach" not in all_cases.get(args.case, {}):
        names = [n for n, c in all_cases.items() if "teach" in c]
        print(f"name a transfer case: {', '.join(names)}", file=sys.stderr)
        return 1
    if args.target == "transfer":
        agents, arms = args.agents.split(","), args.arms.split(",")
        bad = [a for a in agents if a not in bench.AGENTS] + [a for a in arms if a not in transfer.ARMS]
        if bad:
            print(f"unknown: {', '.join(bad)}", file=sys.stderr)
            return 1
        try:
            transfer.run(args.case, agents, arms, args.runs,
                         teach_home=Path(args.teach_home).expanduser() if args.teach_home else None,
                         max_usd=args.max_usd)
        except (RuntimeError, ValueError) as e:
            print(e, file=sys.stderr)
            return 1
    if args.target == "transfer-report" and args.rescore:
        teach = args.teach or transfer.report(args.case)["teach"]
        if teach:
            print(f"{transfer.rescore(args.case, teach)} run(s) scored again", file=sys.stderr)
    rep = transfer.report(args.case, args.teach)
    text = transfer.render(rep)
    if rep["lines"]:
        f = transfer.teach_root() / f"{rep['teach']}" / "REPORT.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        text += f"\n(written to {f})"
    print(json.dumps(rep, indent=1) if args.json else text)
    return 0


def following(state: dict) -> list[dict]:
    """The know-how the current task follows: each piece loaded for it, its size in steps and where it is ready."""
    from athos import wiki
    from athos.adapters import codex
    out = []
    for pid in (state.get("task_loaded") or [])[:3]:
        p = store.get(pid)
        if p is None:
            continue
        exported = (codex.skills_dir() / f"{codex.SKILL_PREFIX}{pid}").is_dir()
        ready = ["Claude Code"] + (["Codex"] if exported or codex.installed() else []) + \
            [label for plat, label in ev.AGENTS if plat in ev.OPTIONAL_AGENTS and (ev.installed(plat) or
                                                                                 (exported and plat == "muse-code"))]
        st = wiki.statements(p)
        out.append({"id": pid, "title": p.title, "version": p.version, "steps": len(st), "wiki": wiki.is_wiki(p),
                    "step_names": [s.id for s in st][:6] if wiki.is_wiki(p) else [], "platforms": ready,
                    "tests": len(cases.tests(pid))})
    return out


def learned_from_edit(state: dict, lang: str = "en") -> list[dict] | None:
    """Files the person edited after the agent wrote them, told to the model with this request ("You edited
    report.md: a rule to keep?"), each with the start of the [Adjust] request that would keep the rule in its step."""
    seen = state.get("learned_from_edit") or {}
    if not seen.get("files") or seen.get("task_id") != state.get("task_id"):
        return None
    prefix = capture.ADJUST_PREFIX["es" if lang == "es" else "en"]
    # A file written before any step was reported has no statement: the request names the piece alone ("…#: " broke
    # the reference, 2026-10-31).
    return [{**f, "adjust_prompt": f"{prefix} {f['piece']}" + (f"#{f['statement']}" if f["statement"] else "") + ": "}
            for f in seen["files"]]


def _session_task(sid: str | None, state: dict, tasks: list[dict]) -> dict | None:
    """The newest recorded task whose id is the session's current one (None outside a session)."""
    if not sid:
        return None
    wanted = state.get("task_id")
    return next((t for t in reversed(tasks) if t.get("task_id") == wanted), None)


def _task_summary(task: dict | None) -> dict | None:
    """The last task as the band shows it, with the pieces it saved split into new ones and improved ones."""
    if not task:
        return None
    saved = task.get("saved", [])
    improved = [pid for pid in saved if (piece := store.get(pid)) and piece.version > 1]
    return {"task_id": task["task_id"], "result": task["result"], "pieces": task.get("pieces", []),
            "saved": [pid for pid in saved if pid not in improved], "improved": improved}


def status() -> dict:
    """Everything the plugin's status line and band draw: the store, what this folder's session loaded and is
    following, and how its last task went. Its keys are read by hooks/ui.tsx and the other panels."""
    from athos import start
    cwd, noted = _here()
    sid = noted.get("session_id")
    state, tasks, lang = (session.load(sid) if sid else {}), ev.tasks(), start.lang()
    current_offer = state.get("offer") if (state.get("offer") or {}).get("task_id") == state.get("task_id") else None
    return {"pieces": len(store.all_pieces()), "lang": lang, "enabled": len(load.enabled(cwd)),
            "bars": ev.bars(paths.project_of(cwd)),
            "loading": control.describe(),
            "loaded": state.get("loaded", []),
            "last_saved": state.get("last_saved"),
            "offer": current_offer,
            "save_prompt": capture.SAVE_PROMPT["es" if lang == "es" else "en"],
            "loads": [{"id": pid, "title": (store.get(pid).title if store.get(pid) else pid), "why": words,
                       "record": ev.record(pid, tasks), "tests": len(cases.tests(pid))}
                      for pid, words in (state.get("task_why") or {}).items()],
            "following": following(state),
            # A cheaper model that matched the person's approved answers on a piece (`athos shadow`).
            "handoff": replay.handoffs(), "shadow": bool(replay.settings().get("on")),
            "embed": bool((start.config().get("embed") or {}).get("on")),     # loads by meaning too (`athos embed on`)
            "learned_from_edit": learned_from_edit(state, lang),
            "trail": trail.view(state), "greeting": trail.greeting(lang),
            # One line when an agent runs an older Athos (`athos doctor`); file reads only, no command is run.
            "behind": _behind(lang),
            # Only recent tasks wait for a mark: an old backlog reads as debt, not help.
            "to_mark": sum(1 for t in tasks if t["result"] == "unevaluated" and ev.recent(t)),
            "last": _task_summary(_session_task(sid, state, tasks))}


def _behind(lang: str) -> str:
    from athos import connect
    try:
        return connect.behind_line(connect.versions(ask_muse=False), lang)
    except Exception:  # noqa: BLE001 — the status line never fails on another agent's config
        return ""


def cmd_doctor(args) -> int:
    from athos import connect, start
    v = connect.versions()
    print(json.dumps(v, ensure_ascii=False) if args.json else connect.report(v, start.lang()))
    return 1 if v["behind"] else 0


def cmd_gallery(args) -> int:
    from athos import gallery
    for f in gallery.build(Path(args.out) if args.out else None):
        print(f)
    return 0


def cmd_add(args) -> int:
    from athos import gallery, start
    try:
        r = gallery.add(args.ref, dry_run=args.dry_run)
    except (ValueError, LookupError, OSError) as e:
        print(f"athos add: {e}", file=sys.stderr)
        return 1
    print(gallery.summary(r, start.lang()))
    return 0


def cmd_status(args: argparse.Namespace) -> int | None:
    """A one-line summary for a terminal; with --json, the whole `status()` the panels draw from."""
    snapshot = status()
    print(json.dumps(snapshot, ensure_ascii=False) if args.json else _status_line(snapshot))


def _status_line(s: dict) -> str:
    if s["lang"] == "es":
        return f"athos · {s['pieces']} formas de trabajar · {len(s['loaded'])} en uso · {s['to_mark']} por marcar"
    return f"athos · {s['pieces']} ways of working · {len(s['loaded'])} in use · {s['to_mark']} to mark"


def _model_error(e: Exception, platform: str, model: str) -> str | None:
    """What to tell the person when the model could not be reached; None for any other error."""
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        # Ollama answers 404 for a model it hasn't pulled; this said "Meta Model API" for it (2026-10-31).
        if platform != "meta" and e.code == 404:
            return f"Ollama has no model {model}: `ollama pull {model}`, or choose one you have with --model."
        who = "Meta Model API" if platform == "meta" else "Ollama"
        return f"{who} refused the request (HTTP {e.code}): {e.read().decode(errors='ignore')[:300]}"
    if isinstance(e, urllib.error.URLError):
        if platform == "meta":
            return f"cannot reach Meta Model API ({e.reason})."
        from athos import delegate
        return (f"cannot reach Ollama at {delegate.host()} ({e.reason}). Start it (`ollama serve`) and pull the "
                f"model (`ollama pull {model}`).")
    return None


def cmd_test(args) -> int:
    """Re-check a piece against the corrections the person made on it before (athos/replay.py)."""
    from athos import start
    platform, model, ask = replay.backend(args.backend, args.model)
    try:
        r = replay.run_tests(args.id, model, ask, platform)
    except (LookupError, PermissionError) as e:
        print(e, file=sys.stderr)
        return 1
    except OSError as e:
        msg = _model_error(e, platform, model)
        if msg is None:
            raise
        print(msg, file=sys.stderr)
        return 1
    print(replay.render_tests(r, start.lang()))
    return 0 if r["passed"] == r["total"] else 1


def cmd_shadow(args) -> int:
    """Compare a cheaper model with the answers the person approved; `on`/`off` runs it after tasks by itself."""
    from athos import start
    lang = start.lang()
    if args.action in ("on", "off"):
        s = replay.set_shadow(args.action == "on", args.backend, args.model)
        where = "Meta Model API" if s["backend"] == "meta" else "Ollama (local)"
        if lang == "es":
            print(f"comparación en segundo plano: {'activada' if s['on'] else 'desactivada'} · {where}")
        else:
            print(f"background shadowing {'on' if s['on'] else 'off'} · {where}")
        return 0
    s = replay.settings()
    # Meta only when the person chose it, here or with `athos shadow on --backend meta`; else a local model.
    platform, model, ask = replay.backend(args.backend or s.get("backend", "ollama"),
                                          args.model or (s.get("model") if not args.backend else None))
    if args.quiet and not replay.take_lock():
        return 0                                   # another background run is at it
    try:
        rs = replay.run_shadow(model, ask, platform, args.limit)
    except (LookupError, PermissionError) as e:
        if not args.quiet:
            print(e, file=sys.stderr)
        return 1
    except OSError as e:
        msg = _model_error(e, platform, model)
        if msg is None:
            raise
        if not args.quiet:
            print(msg, file=sys.stderr)
        return 1
    finally:
        if args.quiet:
            replay.release_lock()
    if not args.quiet:
        print(replay.render_shadow(rs, lang))
        for h in replay.handoffs():
            if not h["told"]:
                print("\n" + replay.sentence(h, lang))
    return 0


def cmd_step(args) -> int:
    """Run by the agent, not the person: the step of the person's know-how it is on now, or a step it did that the
    know-how lacks. The pane and `athos watch` show it."""
    sid = _current_session(os.getcwd()).get("session_id") or os.environ.get("ATHOS_SESSION_ID")
    if not sid:
        print("athos step: no session in this folder", file=sys.stderr)
        return 0
    try:
        print(trail.step(sid, args.ref, args.new))
    except OSError:
        # A sandbox (Muse Code, Codex) may not let the command write to ~/.athos. The tool hook, which runs outside
        # it, already noted the step from the command line; a failure here made Muse Code ask the person to approve
        # every step outside the sandbox (2026-10-31).
        print("ok")
    return 0


def cmd_journal(args) -> int:
    """What happened lately in this project (or another one): the short-term memory a session starts with."""
    from athos import journal
    project = args.project or paths.project_of(os.getcwd())
    print(journal.text(project) or f"Nothing yet in {project}.")
    return 0


def cmd_curate(args) -> int:
    """Tidy the memory as it grows: proposals, applied only when the person names them."""
    from athos import curate
    if args.action == "restore":
        try:
            print(curate.restore(args.which[0]))
        except (IndexError, KeyError, FileExistsError) as e:
            print(f"athos curate restore <id>: {e}", file=sys.stderr)
            return 1
        return 0
    if args.action == "ignore":
        for project in args.which:
            curate.ignore(project)
            print(f"{project}: a test or a rehearsal from now on; it proposes nothing")
        return 0
    props = curate.proposals()
    if args.action in ("apply", "dismiss"):
        for n in args.which:
            try:
                p = props[int(n) - 1]
                if args.action == "dismiss":
                    curate.dismiss(p)
                    print(f"{n}. dismissed: it won't be proposed again")
                else:
                    print(f"{n}. " + curate.apply(p))
            except (ValueError, IndexError, KeyError) as e:
                print(f"{n}. {e}", file=sys.stderr)
        return 0
    if not props:
        print("Nothing to tidy.")
        curate.mark_pass([])
        return 0
    marks = {"tag": "tag", "rule": "rule from corrections", "review": "review", "archive": "archive",
             "similar": "look alike", "link": "broken link", "new": "no page yet"}
    for i, p in enumerate(props, 1):
        print(f"{i:>3}. [{marks[p['kind']]}]{' (new)' if p.get('new') else ''} {p['why']}")
        if p.get("request"):
            print(f"       to do it, send: {p['request']}")
    curate.mark_pass(props)
    print("\n`athos curate apply <n>...` tags or archives (a new version, or a move you can undo); "
          "`athos curate dismiss <n>...` hides a proposal for good; `athos curate ignore <project>` for a test or "
          "demo folder. The others are for you to act on.")
    return 0


def cmd_connector(args) -> int:
    """Connectors a way of working can ask for ([[connector:<name>]]): list them, add one from a template, check it,
    or print how to wire an agent through it. Athos never starts a service: the person runs it."""
    from athos import connectors
    if args.action == "add":
        f = connectors.add(args.name)
        c = connectors.parse(f.read_text())
        print(f"{f}\nStart it in its own terminal:\n  {c.start}")
        return 0
    if args.action == "check":
        c = connectors.get(args.name)
        if not c:
            print(f"no connector {args.name} (athos connector add {args.name})")
            return 1
        ok = connectors.active(c)
        print(f"{c.name}: {'active' if ok else 'not running'}" + ("" if ok else f"\nStart it: {c.start}"))
        return 0 if ok else 1
    if args.action == "wire":
        c = connectors.get(args.name)
        if not c or args.agent not in c.wire:
            known = ", ".join(c.wire) if c else ""
            print(f"no wiring for {args.agent} in {args.name}" + (f" (known: {known})" if known else ""))
            return 1
        print(c.wire[args.agent])
        return 0
    for c in connectors.all_connectors():
        print(f"{c.name:<14} {c.kind:<8} {'active' if connectors.active(c) else 'not running':<12} {c.what}")
    if not connectors.all_connectors():
        print(f"no connectors yet; available templates: {', '.join(connectors.TEMPLATES)} (athos connector add <name>)")
    return 0


def cmd_desktop(args) -> int:
    from athos import desktop
    out = desktop.pack(Path(args.out) if args.out else desktop.ROOT / "dist" / "athos.mcpb")
    carry = [i for c in (args.carry or []) for i in c.split(",") if i]
    skill = desktop.pack_skill(out.with_name("athos-skill.zip"), carry)
    from athos import start
    if start.lang() == "es":
        print(f"{out}\n{skill}\n1. Abrí {out.name} con doble clic (o arrastralo a Claude Desktop → Configuración → "
              f"Extensiones).\n2. Subí {skill.name} en Claude Desktop → Personalizar → Skills, para que Claude use tus "
              f"formas de trabajar sin que se lo pidas. Volvé a subirla cuando guardes formas de trabajar nuevas.")
    else:
        print(f"{out}\n{skill}\n1. Double-click {out.name} (or drag it into Claude Desktop → Settings → Extensions)."
              f"\n2. Upload {skill.name} in Claude Desktop → Customize → Skills, so Claude uses your ways of working "
              f"without being asked. Upload it again when you save new ways of working.")
    return 0


def cmd_start(args) -> int:
    from athos import start
    def pick(prompt: str, options: tuple, default: str) -> str:
        if not sys.stdin.isatty():
            return default
        try:
            ans = input(prompt).strip()
        except EOFError:
            return default
        return options[int(ans) - 1] if ans.isdigit() and 1 <= int(ans) <= len(options) else default
    language = args.lang or pick(start.TEXT["en"]["ask_lang"], start.LANGS, start.lang() if start.config() else "es")
    profile = args.profile or pick(start.TEXT[language]["ask_profile"], start.PROFILES, "other")
    start.save_choice(language, profile)
    added, skipped = start.install(language, profile)
    print("\n" + start.welcome(language, profile, added, skipped))
    return 0


def cmd_library(args) -> int:
    from athos import library
    return library.serve(port=args.port, open_browser=not args.no_open)


def cmd_mcp(_args) -> int:
    from athos import mcp
    return mcp.serve()


def cmd_watch(args) -> int:
    """The trail as a page (--web), as text beside the agent (--trail), or the per-agent bars (the default)."""
    if args.web:
        from athos import watch_web
        return watch_web.serve(port=args.port, open_browser=not args.no_open)
    from athos import watch
    return watch.run_trail() if args.trail else watch.run(once=args.once)


def cmd_hook(args) -> int:
    return hook(args.event, args.platform)


def _parser() -> argparse.ArgumentParser:
    """Every subcommand and its arguments. Which function runs each one is `_HANDLERS`, below."""
    ap = argparse.ArgumentParser(prog="athos", description="Your AI know-how: yours to move between agents, and quick "
                                                           "to run on small models.")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<command>")
    s = sub.add_parser("start", help="first run: your language, your profession, example ways of working")
    s.add_argument("--lang", choices=["es", "en"])
    s.add_argument("--profile", choices=["law", "ops", "journalism", "science", "finance", "other"])
    sub.add_parser("list", help="every piece in the store; ● marks the ones allowed to load here")
    s = sub.add_parser("show", help="print one piece")
    s.add_argument("id", help="the piece's id (its file name without .md)")
    s = sub.add_parser("save", help="store the piece written on stdin (a new version when its id: already exists)")
    s.add_argument("--from-audio", metavar="FILE", help="a recording of how you do a task: Meta's Muse Voice "
                   "Transcribe and Muse Spark draft it as a way of working, saved once you confirm")
    s.add_argument("--lang", choices=["es", "en"], help="with --from-audio: the language spoken and of the draft")
    s.add_argument("--yes", action="store_true", help="with --from-audio: save the draft without asking")
    s = sub.add_parser("curate", help="tidy your ways of working: tag pages with the projects they are used in, "
                       "archive unused ones, spot near-duplicates, broken links and work with no page yet")
    s.add_argument("action", nargs="?", choices=["list", "apply", "dismiss", "ignore", "restore"], default="list")
    s.add_argument("which", nargs="*", help="apply/dismiss: proposal numbers; ignore: a project; restore: a page id")
    s = sub.add_parser("journal", help="what happened lately in this project: its last tasks, what they followed "
                       "or saved, how they went, and what is open")
    s.add_argument("--project", help="another project, by its folder name")
    s = sub.add_parser("load", help="choose which pieces may load; with nothing after it, show the current choice")
    s.add_argument("what", nargs="*", metavar="CHOICE", help="all | project [name] | pieces <id>... | none")
    s = sub.add_parser("export", help="copy your know-how out: a folder, agent skills, a dataset or a guild bundle")
    s.add_argument("dir", nargs="?", help="the folder to write to")
    s.add_argument("--codex", action="store_true", help="each piece as a skill for Codex (default ~/.agents/skills)")
    s.add_argument("--muse", action="store_true", help="the same skills for Muse Code, which reads ~/.agents/skills too")
    s.add_argument("--dataset", metavar="FILE", help="your statements and marked tasks as JSON lines, to evaluate or "
                   "specialise a model on")
    s.add_argument("--guild", metavar="FOLDER", help="each piece and its stats (counts only) for a colleague's "
                   "`athos merge`")
    s.add_argument("--piece", action="append", help="with --guild: only this piece (repeatable)")
    s.add_argument("--as", dest="owner", metavar="NAME", help="with --guild: your name, as colleagues will see it")
    s = sub.add_parser("merge", help="merge colleagues' versions of one of your pieces into one (a dry run unless "
                       "--apply)")
    s.add_argument("id", help="your piece")
    s.add_argument("sources", nargs="+", help="their exported files, or folders holding them")
    s.add_argument("--as-id", help="the id their copies have, when it differs from yours")
    s.add_argument("--apply", action="store_true", help="save the merge as a new version of your piece")
    s.add_argument("--out", metavar="FILE", help="where to write the proposal (default ~/.athos/guild/<id>.merged.md)")
    s.add_argument("--backend", choices=["ollama", "meta"],
                   help="merge differing texts with a model: ollama on this machine, or meta (Meta Model API)")
    s.add_argument("--model", help="the model for --backend (Ollama by default)")
    s = sub.add_parser("codex", help="wire Athos's hooks into Codex (~/.codex/hooks.json), or remove them")
    s.add_argument("action", choices=["install", "uninstall"], help="add the hooks, or take them out")
    s = sub.add_parser("opencode")
    s.add_argument("action", choices=["install", "uninstall"])
    s = sub.add_parser("project", help="this project's own copy of your know-how in .athos/, read by every agent")
    s.add_argument("action", choices=["sync", "remove"])
    s.add_argument("--piece", action="append", help="only this piece (repeatable)")
    s.add_argument("--all", action="store_true", help="every piece, not only the ones this project used")
    s.add_argument("--commit", action="store_true", help="don't add .athos/ to .gitignore (share it with the team)")
    s = sub.add_parser("dismiss", help="the piece loaded for the last task didn't apply: don't load it on those words")
    s.add_argument("id")
    s = sub.add_parser("revert", help="bring back an earlier version of a piece, saved as a new version")
    s.add_argument("id", help="the piece")
    s.add_argument("--to", type=int, help="the version to go back to (default: the previous one)")
    s = sub.add_parser("library", help="every way of working at a glance, as a local page on 127.0.0.1")
    s.add_argument("--port", type=int, default=8712)
    s.add_argument("--no-open", action="store_true", help="don't open the browser")
    s = sub.add_parser("delegate", help="hand a task you master to a smaller model, following one piece")
    s.add_argument("id", help="the piece the task follows")
    s.add_argument("request", help="the request, as you would type it to the agent")
    s.add_argument("--backend", choices=["ollama", "meta"], default="ollama",
                   help="where the model runs: ollama on this machine (default), or meta (Meta Model API)")
    s.add_argument("--model", help="the model: an Ollama one (default gemma4:12b), or with --backend meta "
                                   "muse-spark-1.3 (default) or muse-wonder-1.0")
    s.add_argument("--yes", action="store_true", help="don't ask before each command the model wants to run")
    s.add_argument("--max-steps", type=int, default=20, help="stop after this many model turns (default 20)")
    s.add_argument("--by-step", action="store_true",
                   help="statement by statement, each on the model its **Model:** line names (else this one)")
    s.add_argument("--allow-meta", action="store_true",
                   help="with --by-step: let steps whose **Model:** is meta run on Meta Model API")
    s = sub.add_parser("route", help="which model each step of a piece needs, from your marks on by-step delegations")
    s.add_argument("id")
    s.add_argument("--apply", action="store_true", help="write the suggested **Model:** lines (a new version)")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("mark", help="your verdict on a task: good, corrected or failed")
    s.add_argument("result", help="g for good, c for corrected, f for failed")
    s.add_argument("task", nargs="?", help="the task's id (default: the last task in this folder)")
    s = sub.add_parser("import", help="record the tasks another agent ran, from its session logs")
    s.add_argument("platform", choices=["codex", "muse"])
    s.add_argument("--sessions", help="sessions folder (default ~/.codex/sessions, or ~/.local/share/muse/sessions)")
    s.add_argument("--include-tmp", action="store_true",
                   help="include sessions that ran in temporary folders (as test runs do)")
    s = sub.add_parser("report", help="what each piece and each model adds to your work")
    s.add_argument("--json", action="store_true", help="the numbers as JSON")
    s = sub.add_parser("bench", help="the same tasks on several agents and models, checked by what they leave behind")
    s.add_argument("target", nargs="?", help="a case, several (a,b), all, report, or transfer / transfer-report")
    s.add_argument("case", nargs="?", help="with transfer / transfer-report: the transfer case")
    s.add_argument("--arms", default="A,B", help="with transfer: A no Athos, B .athos/ only, C .athos/ + plugin")
    s.add_argument("--teach-home", help="with transfer: reuse a teaching run's home instead of teaching again")
    s.add_argument("--teach", help="with transfer-report: which teaching run (default the latest)")
    s.add_argument("--rescore", action="store_true",
                   help="with transfer-report: score the kept reviews again with the case's current check")
    s.add_argument("--list", action="store_true", help="the cases")
    s.add_argument("--agents", default="claude,meta",
                   help="claude, codex, muse, opencode, meta, local (comma-separated)")
    s.add_argument("--runs", type=int, default=5)
    s.add_argument("--without", action="store_true", help="also run each agent without the know-how, to compare")
    s.add_argument("--only-without", action="store_true", help="only without the know-how")
    s.add_argument("--model", action="append", help="agent=model, e.g. local=gemma4:12b-mlx (repeatable)")
    s.add_argument("--max-usd", type=float, help="stop once this much has been spent in this call")
    s.add_argument("--keep", action="store_true", help="keep each run's workspace to look at it")
    s.add_argument("--json", action="store_true", help="with report: the numbers as JSON")
    s.add_argument("--router", default="lexical", help="with route: lexical, hybrid (comma-separated)")
    s.add_argument("--scale", type=int, default=0, help="with route: also a store padded to this many pages")
    s.add_argument("--embed-model", help="with route: the Ollama embedding model for hybrid (default your setting)")
    s.add_argument("--from-store", action="store_true",
                   help="with route: your tasks marked good against your store (read-only, counts only)")
    s = sub.add_parser("embed", help="also load know-how by meaning, with a local embedding model (Ollama); on|off")
    s.add_argument("action", nargs="?", choices=["on", "off"])
    s.add_argument("--model", help="the Ollama embedding model (default embeddinggemma)")
    s.add_argument("--refresh", action="store_true", help=argparse.SUPPRESS)
    s = sub.add_parser("wiki", help="your know-how as a wiki: rebuild Index.md, check links, trajectory agents")
    s.add_argument("action", nargs="?", choices=["lint", "agents"], default="lint")
    s.add_argument("--install", action="store_true", help="with agents: put them where Claude Code finds subagents")
    s.add_argument("--uninstall", action="store_true", help="with agents: remove them from there")
    s.add_argument("--dir", help="with agents: where to install (default ~/.claude/agents)")
    s.add_argument("--json", action="store_true")
    sub.add_parser("mcp", help="serve your know-how as an MCP server over stdio (Claude Desktop's chat, any MCP app)")
    s = sub.add_parser("watch", help="a live panel of how each agent applies this project's know-how")
    s.add_argument("--once", action="store_true", help="print the panel once and exit")
    s.add_argument("--web", action="store_true", help="the trail panel as a local page, beside an agent without one")
    s.add_argument("--port", type=int, default=8711)
    s.add_argument("--no-open", action="store_true", help="don't open the browser")
    s.add_argument("--trail", action="store_true", help="the trail panel as text, in a terminal beside the agent")
    s = sub.add_parser("connector", help="services a way of working can ask for, e.g. pii-guard (list, add, check, wire)")
    s.add_argument("action", nargs="?", default="list", choices=["list", "add", "check", "wire"])
    s.add_argument("name", nargs="?")
    s.add_argument("agent", nargs="?", help="for wire: opencode, codex, muse-code, claude-code")
    s = sub.add_parser("desktop", help="build Athos as a Claude Desktop extension (.mcpb): the chat gets your "
                                       "know-how and the trail panel")
    s.add_argument("--out", help="where to write it (default dist/athos.mcpb in the Athos folder)")
    s.add_argument("--carry", action="append", metavar="ID[,ID…]",
                   help="ways of working to put inside the skill, so Claude follows them even without the connector "
                        "(they are then kept in your Claude account too)")
    s = sub.add_parser("step", help="(for the agent) the step of your know-how it is on, shown in Athos's pane")
    s.add_argument("ref", nargs="?", help="<piece>#<statement>")
    s.add_argument("--new", help="a step the task needed that your know-how doesn't have yet")
    s = sub.add_parser("test", help="re-check a piece against the corrections you made on it before")
    s.add_argument("id", help="the piece")
    s.add_argument("--backend", choices=["ollama", "meta"], default="ollama",
                   help="where the model runs: ollama on this machine (default), or meta (Meta Model API)")
    s.add_argument("--model", help="the model (default gemma4:12b, or muse-spark-1.3 with --backend meta)")
    s = sub.add_parser("shadow", help="compare a cheaper model with the answers you approved; on|off after each task")
    s.add_argument("action", nargs="?", choices=["on", "off"])
    s.add_argument("--backend", choices=["ollama", "meta"],
                   help="ollama on this machine (default), or meta (Meta Model API, only if you choose it)")
    s.add_argument("--model", help="the model (default gemma4:12b, or muse-spark-1.3 with --backend meta)")
    s.add_argument("--limit", type=int, help="at most this many approved tasks")
    s.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    s = sub.add_parser("status", help="a one-line summary of the store and this folder's session")
    s.add_argument("--json", action="store_true", help="everything the status line and band draw, as JSON")
    s = sub.add_parser("doctor", help="which Athos each of your agents runs, and which are behind")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("gallery", help="build the gallery's gallery.json and index.html")
    s.add_argument("action", choices=["build"])
    s.add_argument("--out", help="the folder to write to (default: the gallery folder)")
    s = sub.add_parser("add", help="add a way of working from Athos's public gallery")
    s.add_argument("ref", help="the gallery id, or its raw URL in the athos-agent/athos repository")
    s.add_argument("--dry-run", action="store_true", help="only show what would be added")
    s = sub.add_parser("hook", help="(for the agents' hook configuration) handle one event read as JSON on stdin")
    s.add_argument("event", choices=list(_HOOK_HANDLERS), help="which moment of the session the event marks")
    s.add_argument("--platform", default="claude-code", help="the agent sending it (default claude-code)")
    return ap


_HANDLERS = {
    "start": cmd_start, "list": cmd_list, "show": cmd_show, "save": cmd_save, "curate": cmd_curate,
    "journal": cmd_journal, "load": cmd_load, "export": cmd_export, "merge": cmd_merge, "codex": cmd_codex,
    "opencode": cmd_opencode, "project": cmd_project, "dismiss": cmd_dismiss, "revert": cmd_revert,
    "library": cmd_library, "delegate": cmd_delegate, "route": cmd_route, "mark": cmd_mark, "import": cmd_import,
    "report": cmd_report, "bench": cmd_bench, "embed": cmd_embed, "wiki": cmd_wiki, "mcp": cmd_mcp,
    "watch": cmd_watch, "connector": cmd_connector, "desktop": cmd_desktop, "step": cmd_step, "test": cmd_test,
    "shadow": cmd_shadow, "status": cmd_status, "doctor": cmd_doctor, "gallery": cmd_gallery, "add": cmd_add,
    "hook": cmd_hook,
}


def main(argv: list[str] | None = None) -> int:
    """Run the command line. Called by bin/athos, by Codex's hook shim and by the tests with an explicit argv."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:                                   # a bare `athos` greets instead of failing with a usage error
        from athos import start
        print(start.t("hello"))
        return 0
    args = _parser().parse_args(argv)
    return _HANDLERS[args.cmd](args) or 0           # a handler that ran to its end succeeded


if __name__ == "__main__":
    raise SystemExit(main())
