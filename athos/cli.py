"""The `athos` command.

    athos list                         the pieces, with what is enabled
    athos show <id>                    one piece
    athos save                         save a piece from stdin (creates it, or improves the one named by `id:`)
    athos load [all | project [name] | pieces <id>... | none]   what may load; no argument shows the current choice
    athos export <dir>                 copy the whole store to a folder
    athos export --codex [dir]         write each piece as a Codex skill (default ~/.agents/skills)
    athos codex install|uninstall      add or remove Athos's hooks in Codex (~/.codex/hooks.json)
    athos import codex [--include-tmp] record Codex's past tasks from its session files (report does it too)
    athos revert <id>                  put back a piece's previous version
    athos watch                       a live panel: one bar per agent for this project's know-how (for Codex)
    athos export --muse [<folder>]    the same skills for Muse Code; `athos import muse` records its tasks
    athos delegate <id> "<request>"    run a task you have mastered on a small local model (Ollama), recorded as `local`
    athos delegate <id> "<request>" --backend meta   the same on Meta Model API (muse-spark-1.3), recorded as `meta`
    athos mark g|c|f [task]            your verdict on the last task: good, corrected or failed
    athos report [--json]              what each piece and each model brings to your work
    athos status --json                what the terminal's status line and band show
    athos hook <event>                 used by the Claude Code plugin's hooks (reads the event JSON on stdin)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from pathlib import Path

from athos import capture, control, eval as ev, load, paths, session, store

ME = Path(__file__).resolve().parents[1] / "bin" / "athos"


def _cmd() -> str:
    return shlex.quote(str(ME)) if ME.exists() else "athos"


# ------------------------------------------------------------------------------------- which session a shell is in
def _cwd_key(cwd: str) -> Path:
    return paths.sessions() / "by-cwd" / (hashlib.sha1(os.path.realpath(cwd).encode()).hexdigest()[:16] + ".json")


def _remember_session(event: dict) -> None:
    cwd, sid = event.get("cwd"), event.get("session_id")
    if cwd and sid:
        f = _cwd_key(cwd)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"session_id": sid, "transcript_path": event.get("transcript_path")}))


def _current_session(cwd: str) -> dict:
    try:
        return json.loads(_cwd_key(cwd).read_text())
    except (OSError, ValueError):
        return {}


# ------------------------------------------------------------------------------------------------ hooks
def hook(event_name: str, platform: str = "claude-code") -> int:
    """Never breaks the user's session: any error is reported on stderr and the hook exits 0."""
    try:
        event = json.loads(sys.stdin.read() or "{}")
        _remember_session(event)
        if event.get("session_id"):
            session.update(event["session_id"], platform=platform)
        if event_name == "session-start":
            text = load.on_session_start(event, _cmd())
            if text:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        elif event_name == "prompt":
            ev.task_start(event, platform)
            text = load.on_prompt(event)
            if text:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                         "additionalContext": text}}))
        elif event_name == "tool":
            capture.count_tool(event)
        elif event_name == "stop":
            ev.task_end(event)
            out = capture.stop_decision(event, _cmd())
            if out:
                print(json.dumps(out))
    except Exception as e:  # noqa: BLE001
        print(f"athos hook {event_name}: {e}", file=sys.stderr)
    return 0


# ------------------------------------------------------------------------------------------------ commands
def cmd_list(_args) -> int:
    pieces = store.all_pieces()
    on = {p.id for p in load.enabled(os.getcwd())}
    print(f"{len(pieces)} piece(s) in {paths.know_how()} · loading: {control.describe()}")
    for p in sorted(pieces, key=lambda p: p.last_used, reverse=True):
        mark = "●" if p.id in on else "○"
        print(f"{mark} {p.id}  v{p.version}  {p.title}\n    when: {p.when}  · last used {p.last_used}")
    return 0


def cmd_show(args) -> int:
    p = store.get(args.id)
    if p is None:
        print(f"no piece {args.id}", file=sys.stderr)
        return 1
    cur = _current_session(os.getcwd())
    if cur.get("session_id"):
        load.mark_loaded(cur["session_id"], [p.id])
    print(store.render(p), end="")
    return 0


def cmd_save(_args) -> int:
    cwd = os.getcwd()
    cur = _current_session(cwd)
    try:
        piece, diff = capture.save_text(sys.stdin.read(), cur.get("session_id", "default"), cwd,
                                        cur.get("transcript_path"))
    except ValueError as e:
        print(f"not saved: {e}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"not saved: this session may not write to {paths.home()}. In Codex's workspace-write sandbox, allow it "
              f"with `-c 'sandbox_workspace_write.writable_roots=[\"{paths.home()}\"]'` or the same key in "
              "~/.codex/config.toml.", file=sys.stderr)
        return 1
    if diff:
        print(f"improved {piece.id} → v{piece.version} ({piece.path})\n\n{diff}")
    else:
        print(f"saved {piece.id} ({piece.path})")
    return 0


def cmd_load(args) -> int:
    if not args.what:
        print(f"loading: {control.describe()}")
        return 0
    mode, values = args.what[0], args.what[1:]
    try:
        sel = control.set_selection(mode, values)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"loading: {control.describe(sel)} ({len(load.enabled(os.getcwd()))} piece(s) enabled)")
    return 0


def cmd_export(args) -> int:
    if args.codex or args.muse:
        from athos.adapters import codex
        dest = Path(args.dir).expanduser() if args.dir else codex.skills_dir()
        n, removed = codex.export_skills(dest)
        who = "Codex and Muse Code" if args.muse else "Codex"
        print(f"exported {n} piece(s) as skills for {who} to {dest}" + (f" (removed {removed} stale)" if removed else ""))
        return 0
    if not args.dir:
        print("name a folder to export to", file=sys.stderr)
        return 1
    n = store.export(Path(args.dir).expanduser())
    print(f"exported {n} piece(s) to {Path(args.dir).expanduser()}")
    return 0


def cmd_codex(args) -> int:
    from athos.adapters import codex
    if args.action == "install":
        f, backup = codex.install(Path(__file__).resolve().parents[1])
        print(f"Athos hooks added to {f}" + (f" (previous file saved as {backup.name})" if backup else ""))
        print("Codex asks you to trust new hooks once: run /hooks inside Codex and approve the Athos ones.")
        print(f"So that Codex can save know-how from its workspace-write sandbox, add {paths.home()} to "
              "`sandbox_workspace_write.writable_roots` in ~/.codex/config.toml:\n\n"
              f"  [sandbox_workspace_write]\n  writable_roots = [\"{paths.home()}\"]")
        return 0
    removed = codex.uninstall()
    print("Athos hooks removed from Codex" if removed else "no Codex hooks file")
    return 0


def cmd_revert(args) -> int:
    try:
        p = store.revert(args.id)
    except (KeyError, FileNotFoundError) as e:
        print(f"cannot revert: {e}", file=sys.stderr)
        return 1
    print(f"reverted {p.id} (now v{p.version})")
    return 0


def cmd_delegate(args) -> int:
    from athos import delegate
    import urllib.error
    if args.backend == "meta":
        from athos.adapters import meta
        model, platform, chat_fn = args.model or meta.DEFAULT_MODEL, "meta", meta.chat
    else:
        model, platform, chat_fn = args.model or delegate.DEFAULT_MODEL, "local", delegate.chat
    try:
        r = delegate.delegate(args.id, args.request, model, yes=args.yes, max_steps=args.max_steps,
                              chat_fn=chat_fn, platform=platform)
    except (LookupError, PermissionError) as e:
        print(e, file=sys.stderr)
        return 1
    except urllib.error.HTTPError as e:
        print(f"Meta Model API refused the request (HTTP {e.code}): {e.read().decode(errors='ignore')[:300]}",
              file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        if platform == "meta":
            print(f"cannot reach Meta Model API ({e.reason}).", file=sys.stderr)
        else:
            print(f"cannot reach Ollama at {delegate.host()} ({e.reason}). Start it (`ollama serve`) and pull the "
                  f"model (`ollama pull {model}`).", file=sys.stderr)
        return 1
    print(f"\n{r['summary'].strip()}\n\n{platform} / {model}: {r['duration_s']} s, {r['steps']} step(s), "
          f"{r['tokens']['total']:,} tokens · task {r['task_id']}. Mark it with `athos mark g|c|f`.")
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


def cmd_mark(args) -> int:
    cur = _current_session(os.getcwd())
    if not args.task:
        import_other_agents()                          # a Codex or Muse Code task just finished here may be the one meant
    try:
        tid, res = ev.mark(args.result, args.task, cur.get("session_id"), paths.project_of(os.getcwd()))
    except (ValueError, LookupError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"task {tid} marked {res}")
    return 0


def cmd_import(args) -> int:
    from athos.adapters import codex, muse
    mod, name = (muse, "Muse Code") if args.platform == "muse" else (codex, "Codex")
    out = mod.import_sessions(Path(args.sessions).expanduser() if args.sessions else None, args.include_tmp)
    print(f"{name}: {out['imported']} task(s) imported from {out['files']} session file(s) ({out['skipped']} skipped)")
    return 0


def cmd_report(args) -> int:
    for failed in import_other_agents():              # Codex's and Muse Code's tasks are always in the report
        print(f"(sessions not imported: {failed})", file=sys.stderr)
    r = ev.report()
    print(json.dumps(r, indent=1, ensure_ascii=False) if args.json else ev.render(r))
    return 0


def status() -> dict:
    """For the plugin's status line and band: the store, this session's pieces and its last task."""
    cur = _current_session(os.getcwd())
    sid = cur.get("session_id")
    state = session.load(sid) if sid else {}
    tasks = ev.tasks()
    last = next((t for t in reversed(tasks) if sid and t.get("task_id") == state.get("task_id")), None)
    saved = last.get("saved", []) if last else []
    improved = [pid for pid in saved if (store.get(pid) and store.get(pid).version > 1)]
    return {"pieces": len(store.all_pieces()), "enabled": len(load.enabled(os.getcwd())),
            "bars": ev.bars(paths.project_of(os.getcwd())),
            "loading": control.describe(), "loaded": state.get("loaded", []),
            "to_mark": sum(1 for t in tasks if t["result"] == "unevaluated"),
            "last": {"task_id": last["task_id"], "result": last["result"], "pieces": last.get("pieces", []),
                     "saved": [x for x in saved if x not in improved], "improved": improved} if last else None}


def cmd_status(args) -> int:
    s = status()
    if args.json:
        print(json.dumps(s, ensure_ascii=False))
    else:
        print(f"athos · {s['pieces']} piece(s) · {len(s['loaded'])} loaded here · {s['to_mark']} to mark")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="athos", description="Your AI know-how. Free to move, fast to run.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("show")
    s.add_argument("id")
    s.set_defaults(fn=cmd_show)
    sub.add_parser("save").set_defaults(fn=cmd_save)
    s = sub.add_parser("load")
    s.add_argument("what", nargs="*")
    s.set_defaults(fn=cmd_load)
    s = sub.add_parser("export")
    s.add_argument("dir", nargs="?")
    s.add_argument("--codex", action="store_true", help="write each piece as a Codex skill (default ~/.agents/skills)")
    s.add_argument("--muse", action="store_true", help="the same skills for Muse Code, which reads ~/.agents/skills too")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("codex")
    s.add_argument("action", choices=["install", "uninstall"])
    s.set_defaults(fn=cmd_codex)
    s = sub.add_parser("revert")
    s.add_argument("id")
    s.set_defaults(fn=cmd_revert)
    s = sub.add_parser("delegate")
    s.add_argument("id", help="the piece of know-how the task follows")
    s.add_argument("request")
    s.add_argument("--backend", choices=["ollama", "meta"], default="ollama",
                   help="where the model runs: ollama on this machine (default), or meta (Meta Model API)")
    s.add_argument("--model", help="the model: an Ollama one (default gemma4:12b), or with --backend meta "
                                   "muse-spark-1.3 (default) or muse-wonder-1.0")
    s.add_argument("--yes", action="store_true", help="run the model's commands without asking for each")
    s.add_argument("--max-steps", type=int, default=20)
    s.set_defaults(fn=cmd_delegate)
    s = sub.add_parser("mark")
    s.add_argument("result", help="g (good), c (corrected) or f (failed)")
    s.add_argument("task", nargs="?")
    s.set_defaults(fn=cmd_mark)
    s = sub.add_parser("import")
    s.add_argument("platform", choices=["codex", "muse"])
    s.add_argument("--sessions", help="sessions folder (default ~/.codex/sessions, or ~/.local/share/muse/sessions)")
    s.add_argument("--include-tmp", action="store_true", help="also sessions run in temporary folders (tests)")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("report")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("watch", help="a live panel of how each agent applies this project's know-how")
    s.add_argument("--once", action="store_true", help="print the panel once and exit")
    s.set_defaults(fn=lambda a: __import__("athos.watch", fromlist=["run"]).run(once=a.once))
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("hook")
    s.add_argument("event", choices=["session-start", "prompt", "tool", "stop"])
    s.add_argument("--platform", default="claude-code")
    s.set_defaults(fn=lambda a: hook(a.event, a.platform))
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
