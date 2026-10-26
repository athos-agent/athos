"""Delegation: run a task you have mastered on a small model on your own machine, through Ollama.

    athos delegate <piece> "<request>"     the piece is the know-how; the model does the work in the current folder

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


def delegate(piece_id: str, request: str, model: str = DEFAULT_MODEL, cwd: Path | None = None, yes: bool = False,
             max_steps: int = MAX_STEPS, out=print, chat_fn=chat) -> dict:
    """Run the task and record it. Returns the task id, the model's last message, the steps, the time and the tokens."""
    piece = store.get(piece_id)
    if piece is None:
        raise LookupError(f"no piece {piece_id}")
    cwd = (cwd or Path.cwd()).resolve()
    confirm = (lambda _w: True) if yes else _ask
    messages = [{"role": "system", "content": SYSTEM.format(cwd=cwd, today=_dt.date.today().isoformat(), title=piece.title, body=piece.body)},
                {"role": "user", "content": request}]
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    t0, final, steps, last, same = time.monotonic(), "", 0, None, 0
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
    tokens["total"] = tokens["input"] + tokens["output"]
    duration = time.monotonic() - t0
    store.touch(piece.id)
    tid = ev.record_external("local", model, [piece.id], duration, tokens, request=request,
                             project=paths.project_of(cwd))
    return {"task_id": tid, "summary": final, "steps": steps, "duration_s": round(duration, 1), "tokens": tokens}
