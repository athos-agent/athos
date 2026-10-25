"""The `athos` command.

    athos list                         the pieces, with what is enabled
    athos show <id>                    one piece
    athos save                         save a piece from stdin (creates it, or improves the one named by `id:`)
    athos load [all | project [name] | pieces <id>... | none]   what may load; no argument shows the current choice
    athos export <dir>                 copy the whole store to a folder
    athos revert <id>                  put back a piece's previous version
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
def hook(event_name: str) -> int:
    """Never breaks the user's session: any error is reported on stderr and the hook exits 0."""
    try:
        event = json.loads(sys.stdin.read() or "{}")
        _remember_session(event)
        if event_name == "session-start":
            text = load.on_session_start(event, _cmd())
            if text:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        elif event_name == "prompt":
            ev.task_start(event)
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
    n = store.export(Path(args.dir).expanduser())
    print(f"exported {n} piece(s) to {Path(args.dir).expanduser()}")
    return 0


def cmd_revert(args) -> int:
    try:
        p = store.revert(args.id)
    except (KeyError, FileNotFoundError) as e:
        print(f"cannot revert: {e}", file=sys.stderr)
        return 1
    print(f"reverted {p.id} (now v{p.version})")
    return 0


def cmd_mark(args) -> int:
    cur = _current_session(os.getcwd())
    try:
        tid, res = ev.mark(args.result, args.task, cur.get("session_id"))
    except (ValueError, LookupError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"task {tid} marked {res}")
    return 0


def cmd_report(args) -> int:
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
    s.add_argument("dir")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("revert")
    s.add_argument("id")
    s.set_defaults(fn=cmd_revert)
    s = sub.add_parser("mark")
    s.add_argument("result", help="g (good), c (corrected) or f (failed)")
    s.add_argument("task", nargs="?")
    s.set_defaults(fn=cmd_mark)
    s = sub.add_parser("report")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("hook")
    s.add_argument("event", choices=["session-start", "prompt", "tool", "stop"])
    s.set_defaults(fn=lambda a: hook(a.event))
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
