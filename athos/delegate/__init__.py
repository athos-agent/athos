"""Delegation: run a task you have mastered on a small model on your own machine, through Ollama.

    athos delegate <piece> "<request>"     the piece is the know-how; the model does the work in the current folder
    athos delegate <piece> "<request>" --by-step    statement by statement, each on the model its `**Model:**` names

The model gets the piece and four tools (run a shell command, read, edit and write a file), all inside the current
folder. Every command and write is shown and asked for before it runs, unless `--yes`. Nothing is ever delegated
without an explicit `athos delegate`. The task is recorded in the report as platform `local`, with the model, the time
and the tokens, and is marked like any other (`athos mark g|c|f`).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from athos import eval as ev, paths, store

DEFAULT_MODEL = "gemma4:12b"
MAX_STEPS = 20
OUTPUT_LIMIT = 4000

TOOLS = [
    {"type": "function", "function": {
        "name": "run", "description": "Run a shell command in the project folder and get its output and exit code.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file of the project.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "edit_file", "description": "Replace one exact piece of text in a file of the project, keeping the "
                                            "rest of the file. Use it to change or add to an existing file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                                        "new": {"type": "string"}},
                       "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write a whole new file of the project (replaces it if it exists).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
]

REPEATS = 3

SYSTEM = """You do one task in the project folder {cwd}, using the tools. Today is {today}. Follow the user's know-how \
below exactly: it is how this person does this kind of task. Look at the files before changing them. Change only what \
the task needs. Never install or uninstall software, and never touch anything outside the project folder; if something \
is missing, say so and stop. When the task is done, reply with a short summary of what you did and no tool call.

# Know-how: {title}

{body}"""


def host() -> str:
    h = os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    return h if h.startswith("http") else f"http://{h}"


def chat(model: str, messages: list[dict], timeout: float = 600) -> dict:
    # think=False: small reasoning models otherwise spend the turn thinking, and Ollama returns it apart from content.
    body = json.dumps({"model": model, "messages": messages, "tools": TOOLS, "stream": False, "think": False,
                       "options": {"temperature": 0, "num_ctx": 16384}}).encode()
    req = urllib.request.Request(host() + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _inside(cwd: Path, rel: str) -> Path:
    cwd = cwd.resolve()
    p = (cwd / rel).resolve()
    if p != cwd and cwd not in p.parents:
        raise PermissionError(f"{rel} is outside the project folder")
    return p


def _clip(text: str) -> str:
    return text if len(text) <= OUTPUT_LIMIT else text[:OUTPUT_LIMIT] + f"\n… ({len(text) - OUTPUT_LIMIT} more chars)"


def call_tool(name: str, args: dict, cwd: Path, confirm) -> str:
    """A tool's result as text for the model; errors become text too, so one bad call never ends the task."""
    cwd = cwd.resolve()
    try:
        if name == "run":
            cmd = str(args.get("command", ""))
            if not confirm(f"run: {cmd}"):
                return "The user did not allow this command."
            r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
            return _clip(f"exit code {r.returncode}\n{r.stdout}{r.stderr}")
        if name == "read_file":
            return _clip(_inside(cwd, str(args.get("path", ""))).read_text())
        if name == "edit_file":
            p = _inside(cwd, str(args.get("path", "")))
            old, new = str(args.get("old", "")), str(args.get("new", ""))
            text = p.read_text()
            if not old or text.count(old) != 1:
                return f"error: the old text must appear exactly once in {p.relative_to(cwd)}; it appears " \
                       f"{text.count(old) if old else 0} times"
            if not confirm(f"edit: {p.relative_to(cwd)}"):
                return "The user did not allow this edit."
            p.write_text(text.replace(old, new, 1))
            return f"edited {p.relative_to(cwd)}"
        if name == "write_file":
            p = _inside(cwd, str(args.get("path", "")))
            if not confirm(f"write: {p.relative_to(cwd)} ({len(str(args.get('content', '')))} chars)"):
                return "The user did not allow this write."
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(args.get("content", "")))
            return f"wrote {p.relative_to(cwd)}"
        return f"unknown tool {name}"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def _ask(what: str) -> bool:
    if not sys.stdin.isatty():
        return False
    return input(f"  allow {what}? [y/N] ").strip().lower() in ("y", "yes")


def _loop(chat_fn, model: str, messages: list[dict], cwd: Path, confirm, max_steps: int, out) -> tuple[str, int, dict]:
    """The tool loop on one model, appending to `messages`: until the model answers without a tool call. Returns its
    last message, the turns it took and the tokens."""
    tokens = {"input": 0, "output": 0}
    final, steps, last, same = "", 0, None, 0
    while steps < max_steps:
        steps += 1
        r = chat_fn(model, messages)
        tokens["input"] += int(r.get("prompt_eval_count") or 0)
        tokens["output"] += int(r.get("eval_count") or 0)
        msg = r.get("message") or {}
        calls = msg.get("tool_calls") or []
        messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": calls})
        if not calls:
            final = msg.get("content", "")
            break
        # A small model can repeat one call forever; the same calls several times in a row end the task.
        key = json.dumps([c.get("function") for c in calls], sort_keys=True)
        same = same + 1 if key == last else 1
        last = key
        if same >= REPEATS:
            final = f"(stopped: the model repeated the same step {REPEATS} times)"
            # Calls left unanswered would break the next turn of a shared conversation (--by-step).
            messages[-1] = {"role": "assistant", "content": final}
            break
        for c in calls:
            fn = c.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            out(f"· {fn.get('name')} {args.get('command') or args.get('path') or ''}")
            messages.append({"role": "tool", "tool_name": fn.get("name", ""),
                             "content": call_tool(fn.get("name", ""), args, cwd, confirm)})
    else:
        final = f"(stopped after {max_steps} steps)"
    return final, steps, tokens


def _system(piece: store.Piece, cwd: Path) -> dict:
    return {"role": "system", "content": SYSTEM.format(cwd=cwd, today=_dt.date.today().isoformat(), title=piece.title,
                                                       body=piece.body)}


def delegate(piece_id: str, request: str, model: str = DEFAULT_MODEL, cwd: Path | None = None, yes: bool = False,
             max_steps: int = MAX_STEPS, out=print, chat_fn=chat, platform: str = "local") -> dict:
    """Run the task and record it. Returns the task id, the model's last message, the steps, the time and the tokens."""
    piece = store.get(piece_id)
    if piece is None:
        raise LookupError(f"no piece {piece_id}")
    cwd = (cwd or Path.cwd()).resolve()
    confirm = (lambda _w: True) if yes else _ask
    messages = [_system(piece, cwd), {"role": "user", "content": request}]
    t0 = time.monotonic()
    final, steps, tokens = _loop(chat_fn, model, messages, cwd, confirm, max_steps, out)
    tokens.update(cache_read=0, cache_write=0, total=tokens["input"] + tokens["output"])
    duration = time.monotonic() - t0
    store.touch(piece.id)
    tid = ev.record_external(platform, model, [piece.id], duration, tokens, request=request,
                             project=paths.project_of(cwd))
    return {"task_id": tid, "summary": final, "steps": steps, "duration_s": round(duration, 1), "tokens": tokens}


# ------------------------------------------------------------------------------------------------ one model per step
def parse_spec(spec: str) -> tuple[str, str] | None:
    """A `**Model:**` line as (platform, model): `local`, `meta`, `ollama:<model>`, `meta:<model>`. None when it is
    none of these, so a typo never sends a step somewhere unexpected."""
    from athos.adapters import meta
    spec = spec.strip().strip("`")
    if spec == "local":
        return "local", DEFAULT_MODEL
    if spec == "meta":
        return "meta", meta.DEFAULT_MODEL
    backend, _, model = spec.partition(":")
    if model and backend in ("ollama", "local"):
        return "local", model
    if model and backend == "meta":
        return "meta", model
    return None


def spec_of(platform: str, model: str) -> str:
    """The `**Model:**` line for a (platform, model), short when it is the default one."""
    from athos.adapters import meta
    if platform == "meta":
        return "meta" if model == meta.DEFAULT_MODEL else f"meta:{model}"
    return "local" if model == DEFAULT_MODEL else f"ollama:{model}"


def plan(piece: store.Piece, default: tuple[str, str]) -> list[tuple[object, str, str]]:
    """Each statement with the (platform, model) it runs on: its own `**Model:**`, else the task's."""
    from athos import wiki
    out = []
    for s in wiki.statements(piece):
        if s.model and parse_spec(s.model) is None:
            raise ValueError(f"#{s.id}: unknown model {s.model!r} (use local, meta, ollama:<model> or meta:<model>)")
        out.append((s, *(parse_spec(s.model) if s.model else default)))
    return out


def by_step(piece_id: str, request: str, default: tuple[str, str] = ("local", DEFAULT_MODEL),
            chat_fns: dict | None = None, cwd: Path | None = None, yes: bool = False, max_steps: int = MAX_STEPS,
            out=print, allow_hosted: bool = False) -> dict:
    """Run the piece statement by statement in one conversation, each step on the model its `**Model:**` line names
    (else `default`). `chat_fns` maps a platform (`local`, `meta`) to its chat function. A step on Meta's hosted model
    runs only with `allow_hosted`: the request and the files it reads leave the machine (the privacy rule). Each step
    is reported to the trail, so `athos watch` ticks it, and recorded with its model, time and tokens."""
    from athos import cli, session, trail
    from athos.adapters import meta
    piece = store.get(piece_id)
    if piece is None:
        raise LookupError(f"no piece {piece_id}")
    steps = plan(piece, default)
    hosted = [f"#{s.id}" for s, platform, _ in steps if platform == "meta"]
    if hosted and not allow_hosted:
        raise PermissionError(f"{', '.join(hosted)} would run on Meta Model API, which sends the request and the files "
                              f"it reads off this machine. Add --allow-meta to allow that.")
    chat_fns = {"local": chat, "meta": meta.chat, **(chat_fns or {})}
    cwd = (cwd or Path.cwd()).resolve()
    confirm = (lambda _w: True) if yes else _ask
    # The task's own session, pointed at by this folder, so the trail panels (`athos watch`) follow it step by step.
    tid = ev.new_task_id()
    sid = f"delegate-{tid}"
    session.save(sid, {"task_id": tid, "task_loaded": [piece.id], "task_request": request[:300]})
    cli._remember_session({"cwd": str(cwd), "session_id": sid})
    messages = [_system(piece, cwd), {"role": "user", "content": request}]
    t0, done, final = time.monotonic(), [], ""
    for s, platform, model in steps:
        trail.step(sid, f"{piece.id}#{s.id}", None)
        out(f"▶ #{s.id} on {platform} / {model}")
        messages.append({"role": "user", "content": f"Now do only this step: #{s.id} — {s.do or s.when}"})
        t1 = time.monotonic()
        final, turns, tok = _loop(chat_fns[platform], model, messages, cwd, confirm, max_steps, out)
        done.append({"id": s.id, "platform": platform, "model": model, "duration_s": round(time.monotonic() - t1, 1),
                     "turns": turns, "tokens": {**tok, "total": tok["input"] + tok["output"]}})
    trail.finish(sid)
    tokens = {k: sum(d["tokens"][k] for d in done) for k in ("input", "output")}
    tokens.update(cache_read=0, cache_write=0, total=tokens["input"] + tokens["output"])
    duration = time.monotonic() - t0
    platforms = {d["platform"] for d in done} or {default[0]}
    models = list(dict.fromkeys(d["model"] for d in done)) or [default[1]]
    store.touch(piece.id)
    ev.record_external(platforms.pop() if len(platforms) == 1 else "mixed", "+".join(models), [piece.id], duration,
                       tokens, request=request, project=paths.project_of(cwd), task_id=tid, steps=done)
    return {"task_id": tid, "summary": final, "steps": done, "duration_s": round(duration, 1), "tokens": tokens}
