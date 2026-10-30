"""The `athos` command.

    athos start                        first run: language, profession, example ways of working (no programming needed)
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
    athos mcp                          your know-how as an MCP server (stdio), for Claude Desktop's chat
    athos wiki [--json]                rebuild Index.md and check the links between pieces (pages of a wiki)
    athos export --dataset FILE        your statements and marked tasks as JSON lines (evals, training data)
    athos wiki agents [--install]      the trajectory subagents (a walk across pages); --install puts them in
                                       ~/.claude/agents and keeps them in step with every save
    athos bench <case|all> --agents claude,meta [--runs 5] [--without] [--max-usd 5]   the same task on each agent,
                                       checked by what it left behind; `athos bench --list`, `athos bench report`
    athos status --json                what the terminal's status line and band show
    athos hook <event>                 used by the Claude Code plugin's hooks (reads the event JSON on stdin)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from athos import capture, control, eval as ev, load, paths, session, store, trail

ME = Path(__file__).resolve().parents[1] / "bin" / "athos"


def _cmd() -> str:
    """How the agent should call Athos in the lines it and the person read: plain `athos` when the agent's shell finds
    it (the plugin puts its own bin on PATH; the installer adds ~/.local/bin), else the full path. A full path also
    showed the person's user name in every line."""
    return "athos" if shutil.which("athos") or not ME.exists() else shlex.quote(str(ME))


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
        if platform == "claude-code" and os.environ.get("MUSE_PLUGIN_ID"):
            platform = "muse-code"                  # Muse Code runs the Claude Code plugin as it is, and says so
        event = json.loads(sys.stdin.read() or "{}")
        _remember_session(event)
        if event.get("session_id"):
            session.update(event["session_id"], platform=platform)
        if event_name == "session-start":
            text = load.on_session_start(event, _cmd())
            if text:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        elif event_name == "prompt":
            if capture.is_save_prompt(event.get("prompt", "")):
                # The person pressed [Save]: the save belongs to the task that just ended, so no new task starts
                # and nothing loads; the offer is spent.
                if event.get("session_id"):
                    session.update(event["session_id"], offer=None)
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                         "additionalContext": capture.SAVE_CONTEXT.format(cmd=_cmd())}}))
                return 0
            if capture.is_adjust_prompt(event.get("prompt", "")):
                # The person pressed [Adjust] on a step of the pane and wrote the change: it improves that piece.
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                         "additionalContext": capture.ADJUST_CONTEXT.format(cmd=_cmd())}}))
                return 0
            from athos import start
            start.note_language(event.get("prompt", ""))
            if event.get("session_id"):
                ev.infer_mark(event["session_id"], event.get("prompt", ""))     # before the new task replaces it
            ev.task_start(event, platform)
            capture.note_request(event)
            text = load.on_prompt(event)
            if text:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                         "additionalContext": text}}))
        elif event_name == "tool":
            capture.count_tool(event)
            trail.on_tool(event)
        elif event_name == "stop":
            ev.task_end(event)
            if event.get("session_id"):
                trail.finish(event["session_id"])
            # A person at an interactive Claude Code session gets a [Save] button above the prompt instead of a
            # line asking the model; a `claude -p` run (CLAUDE_CODE_ENTRYPOINT=sdk-…) has no band, so it is asked.
            interactive = platform == "claude-code" and not os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk")
            out = capture.stop_decision(event, _cmd(), offer=interactive and os.environ.get("ATHOS_ASK") != "model")
            if out and platform == "claude-code":
                # Claude Code labels a Stop block "Stop hook error"; the same request as context reads as feedback.
                out = {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": out["reason"]}}
            if out:
                print(json.dumps(out))
    except Exception as e:  # noqa: BLE001
        print(f"athos hook {event_name}: {e}", file=sys.stderr)
    return 0


# ------------------------------------------------------------------------------------------------ commands
def cmd_list(_args) -> int:
    pieces = store.all_pieces()
    on = {p.id for p in load.enabled(os.getcwd())}
    from athos import start
    if start.lang() == "es":
        print(f"{len(pieces)} forma(s) de trabajar en {paths.know_how()} · se cargan: {control.describe()}")
    else:
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
    broken = (session.load(cur.get("session_id", "default")).get("wiki") or {}).get("broken") or []
    if broken:                                     # the wiki improves in the same turn: the model fixes what it broke
        print("\nwiki: links that lead nowhere; fix them with another `athos save` (id: of the page):\n  "
              + "\n  ".join(broken[:10]))
    same = (session.load(cur.get("session_id", "default")).get("wiki") or {}).get("overlaps") or []
    if same:                                       # possible contradictions: the model checks them now
        print("\nwiki: other pages say what to do at the same moment. Check they agree; if one is wrong or "
              "outdated, fix it with `athos save` (id: of that page), or link them if they apply together:\n  "
              + "\n  ".join(same[:10]))
    return 0


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
    if args.dataset:
        from athos import wiki
        rows = wiki.dataset()
        dest = Path(args.dataset).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        n_st = sum(r["kind"] == "statement" for r in rows)
        print(f"{n_st} statements and {len(rows) - n_st} marked tasks to {dest} (JSON lines). It holds your requests "
              "as you typed them: it stays on this machine unless you move it.")
        return 0
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


def cmd_opencode(args) -> int:
    from athos.adapters import opencode
    if args.action == "install":
        found = shutil.which("athos")
        # The command install.sh puts on PATH outlives plugin versions; a plugin's own bin (on PATH inside a Claude
        # Code session) is tied to that version, so the running one is used instead.
        f = opencode.install(Path(found) if found and "/plugins/cache/" not in os.path.realpath(found) else ME)
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
    from athos import start
    if start.lang() == "es":
        print(f"tarea marcada: {dict(ok='salió bien', corrected='lo corregí', failed='falló').get(res, res)}")
    else:
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


def cmd_bench(args) -> int:
    from athos import bench
    all_cases = bench.cases()
    if args.list or not args.target:
        for name, c in all_cases.items():
            print(f"{name:<15} {c['domain']:<8} {c['title']}: \"{c['request']}\"")
        return 0
    if args.target in ("transfer", "transfer-report"):
        return _bench_transfer(args, all_cases)
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
                    "step_names": [s.id for s in st][:6] if wiki.is_wiki(p) else [], "platforms": ready})
    return out


def status() -> dict:
    """For the plugin's status line and band: the store, this session's pieces and its last task."""
    cur = _current_session(os.getcwd())
    sid = cur.get("session_id")
    state = session.load(sid) if sid else {}
    tasks = ev.tasks()
    last = next((t for t in reversed(tasks) if sid and t.get("task_id") == state.get("task_id")), None)
    saved = last.get("saved", []) if last else []
    improved = [pid for pid in saved if (store.get(pid) and store.get(pid).version > 1)]
    from athos import start
    return {"pieces": len(store.all_pieces()), "lang": start.lang(), "enabled": len(load.enabled(os.getcwd())),
            "bars": ev.bars(paths.project_of(os.getcwd())),
            "loading": control.describe(), "loaded": state.get("loaded", []),
            "last_saved": state.get("last_saved"),
            "offer": state.get("offer") if (state.get("offer") or {}).get("task_id") == state.get("task_id") else None,
            "save_prompt": capture.SAVE_PROMPT["es" if start.lang() == "es" else "en"],
            "loads": [{"id": pid, "title": (store.get(pid).title if store.get(pid) else pid), "why": words,
                       "record": ev.record(pid, tasks)}
                      for pid, words in (state.get("task_why") or {}).items()],
            "following": following(state),
            "trail": trail.view(state), "greeting": trail.greeting(start.lang()),
            # Only recent tasks wait for a mark: an old backlog reads as debt, not help.
            "to_mark": sum(1 for t in tasks if t["result"] == "unevaluated" and ev.recent(t)),
            "last": {"task_id": last["task_id"], "result": last["result"], "pieces": last.get("pieces", []),
                     "saved": [x for x in saved if x not in improved], "improved": improved} if last else None}


def cmd_status(args) -> int:
    s = status()
    if args.json:
        print(json.dumps(s, ensure_ascii=False))
    else:
        if s["lang"] == "es":
            print(f"athos · {s['pieces']} formas de trabajar · {len(s['loaded'])} en uso · {s['to_mark']} por marcar")
        else:
            print(f"athos · {s['pieces']} ways of working · {len(s['loaded'])} in use · {s['to_mark']} to mark")
    return 0


def cmd_step(args) -> int:
    """Run by the agent, not the person: the step of the person's know-how it is on now, or a step it did that the
    know-how lacks. The pane and `athos watch` show it."""
    sid = _current_session(os.getcwd()).get("session_id") or os.environ.get("ATHOS_SESSION_ID")
    if not sid:
        print("athos step: no session in this folder", file=sys.stderr)
        return 0
    print(trail.step(sid, args.ref, args.new))
    return 0


def cmd_desktop(args) -> int:
    from athos import desktop
    out = desktop.pack(Path(args.out) if args.out else desktop.ROOT / "dist" / "athos.mcpb")
    from athos import start
    if start.lang() == "es":
        print(f"{out}\nAbrilo con doble clic (o arrastralo a Claude Desktop → Configuración → Extensiones). En el chat, "
              f"Athos busca tu know-how para cada pedido y muestra su trayectoria en un panel.")
    else:
        print(f"{out}\nDouble-click it (or drag it into Claude Desktop → Settings → Extensions). In the chat, Athos "
              f"finds your know-how for each request and shows its trail in a panel.")
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:                                   # a bare `athos` greets instead of failing with a usage error
        from athos import start
        print(start.t("hello"))
        return 0
    ap = argparse.ArgumentParser(prog="athos", description="Your AI know-how. Free to move, fast to run.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="first run: your language, your profession, example ways of working")
    s.add_argument("--lang", choices=["es", "en"])
    s.add_argument("--profile", choices=["law", "sports", "other"])
    s.set_defaults(fn=cmd_start)
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
    s.add_argument("--dataset", metavar="FILE", help="your statements and marked tasks as JSON lines, to evaluate or "
                   "specialise a model on")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("codex")
    s.add_argument("action", choices=["install", "uninstall"])
    s.set_defaults(fn=cmd_codex)
    s = sub.add_parser("opencode")
    s.add_argument("action", choices=["install", "uninstall"])
    s.set_defaults(fn=cmd_opencode)
    s = sub.add_parser("project", help="this project's own copy of your know-how in .athos/, read by every agent")
    s.add_argument("action", choices=["sync", "remove"])
    s.add_argument("--piece", action="append", help="only this piece (repeatable)")
    s.add_argument("--all", action="store_true", help="every piece, not only the ones this project used")
    s.add_argument("--commit", action="store_true", help="don't add .athos/ to .gitignore (share it with the team)")
    s.set_defaults(fn=cmd_project)
    s = sub.add_parser("dismiss", help="the piece loaded for the last task didn't apply: don't load it on those words")
    s.add_argument("id")
    s.set_defaults(fn=cmd_dismiss)
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
    s.set_defaults(fn=cmd_bench)
    s = sub.add_parser("wiki", help="your know-how as a wiki: rebuild Index.md, check links, trajectory agents")
    s.add_argument("action", nargs="?", choices=["lint", "agents"], default="lint")
    s.add_argument("--install", action="store_true", help="with agents: put them where Claude Code finds subagents")
    s.add_argument("--uninstall", action="store_true", help="with agents: remove them from there")
    s.add_argument("--dir", help="with agents: where to install (default ~/.claude/agents)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_wiki)
    s = sub.add_parser("mcp", help="serve your know-how as an MCP server over stdio (Claude Desktop's chat, any MCP app)")
    s.set_defaults(fn=lambda a: __import__("athos.mcp", fromlist=["serve"]).serve())
    s = sub.add_parser("watch", help="a live panel of how each agent applies this project's know-how")
    s.add_argument("--once", action="store_true", help="print the panel once and exit")
    s.set_defaults(fn=lambda a: __import__("athos.watch", fromlist=["run"]).run(once=a.once))
    s = sub.add_parser("desktop", help="build Athos as a Claude Desktop extension (.mcpb): the chat gets your "
                                       "know-how and the trail panel")
    s.add_argument("--out", help="where to write it (default dist/athos.mcpb in the Athos folder)")
    s.set_defaults(fn=cmd_desktop)
    s = sub.add_parser("step", help="(for the agent) the step of your know-how it is on, shown in Athos's pane")
    s.add_argument("ref", nargs="?", help="<piece>#<statement>")
    s.add_argument("--new", help="a step the task needed that your know-how doesn't have yet")
    s.set_defaults(fn=cmd_step)
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
