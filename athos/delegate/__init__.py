"""Delegation: hand a task you already know how to do to a small model running on this machine (Ollama).

    athos delegate <piece> "<request>"              the piece is the know-how; the model works in the current folder
    athos delegate <piece> "<request>" --by-step    one statement at a time, each on the model its `**Model:**` names

What the model gets: the piece as its instructions, and four tools confined to the current folder (run a shell command,
read a file, edit part of a file, write a whole file). Each command, edit and write is put to the person first unless
`--yes` was given, and nothing is delegated unless the person runs `athos delegate`. The run is recorded like any other
task, with platform `local`, the model, the time and the tokens, so `athos mark g|c|f` and the report work on it.
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
MAX_STEPS = 20           # model turns before a run is cut off
OUTPUT_LIMIT = 4000      # characters of a tool result the model sees
REPEATS = 3              # identical consecutive turns that count as a model going round in circles
COMMAND_TIMEOUT = 120    # seconds a delegated shell command may take


def _tool_schema(name: str, description: str, *params: str) -> dict:
    """An Ollama / OpenAI-style function declaration whose parameters are all required strings."""
    properties = {param: {"type": "string"} for param in params}
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": list(params)}}}


# The tools the model may call; athos/adapters/meta sends the same list to Meta's API.
TOOLS = [
    _tool_schema("run", "Run a shell command in the project folder and get its output and exit code.", "command"),
    _tool_schema("read_file", "Read a file of the project.", "path"),
    _tool_schema("edit_file", "Replace one exact piece of text in a file of the project, keeping the rest of the "
                              "file. Use it to change or add to an existing file.", "path", "old", "new"),
    _tool_schema("write_file", "Write a whole new file of the project (replaces it if it exists).", "path", "content"),
]

_RULES = (
    "You do one task in the project folder {cwd}, using the tools.",
    "Today is {today}.",
    "Follow the user's know-how below exactly: it is how this person does this kind of task.",
    "Look at the files before changing them.",
    "Change only what the task needs.",
    "Never install or uninstall software, and never touch anything outside the project folder; if something is "
    "missing, say so and stop.",
    "When the task is done, reply with a short summary of what you did and no tool call.",
)
SYSTEM = " ".join(_RULES) + "\n\n# Know-how: {title}\n\n{body}"


def host() -> str:
    """Ollama's base URL: OLLAMA_HOST when set (a bare host:port gets http://), else the local default."""
    configured = os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    return configured if configured.startswith("http") else "http://" + configured


def chat(model: str, messages: list[dict], timeout: float = 600, tools: bool = True) -> dict:
    """One Ollama chat call. `tools=False` sends none: a plain answer, for replaying a case (`athos test`, `athos
    shadow`), where the model only writes."""
    # Thinking is switched off: a small reasoning model would spend its turn on it, and Ollama keeps it out of the
    # content anyway.
    req_body = {"model": model, "messages": messages, "stream": False, "think": False,
                "options": {"temperature": 0, "num_ctx": 16384}}
    if tools:
        req_body["tools"] = TOOLS
    request = urllib.request.Request(f"{host()}/api/chat", data=json.dumps(req_body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _within_project(cwd: Path, rel: str) -> Path:
    """`rel` resolved against the project folder; PermissionError when it lands outside it (`..`, symlinks)."""
    root = cwd.resolve()
    target = (root / rel).resolve()
    if target == root or root in target.parents:
        return target
    raise PermissionError(f"{rel} lies outside the project folder")


def _trimmed(text: str) -> str:
    """Tool output trimmed to OUTPUT_LIMIT, saying how much was left out."""
    overflow = len(text) - OUTPUT_LIMIT
    return text[:OUTPUT_LIMIT] + f"\n… ({overflow} more chars)" if overflow > 0 else text


def _refused(action: str) -> str:
    return f"The user did not allow this {action}."


def _run_command(args: dict, root: Path, confirm) -> str:
    command = str(args.get("command", ""))
    if not confirm(f"run: {command}"):
        return _refused("command")
    done = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    return _trimmed(f"exit code {done.returncode}\n{done.stdout}{done.stderr}")


def _read_file(args: dict, root: Path, confirm) -> str:
    return _trimmed(_within_project(root, str(args.get("path", ""))).read_text())


def _edit_file(args: dict, root: Path, confirm) -> str:
    """Swap one exact, unique snippet; the rest of the file stays as it was."""
    target = _within_project(root, str(args.get("path", "")))
    shown = target.relative_to(root)
    old, new = (str(args.get(key, "")) for key in ("old", "new"))
    current = target.read_text()
    found = current.count(old) if old else 0
    if found != 1:
        return f"error: the old text must appear exactly once in {shown}; it appears {found} times"
    if not confirm(f"edit: {shown}"):
        return _refused("edit")
    target.write_text(current.replace(old, new, 1))
    return f"edited {shown}"


def _write_file(args: dict, root: Path, confirm) -> str:
    target = _within_project(root, str(args.get("path", "")))
    shown = target.relative_to(root)
    content = str(args.get("content", ""))
    if not confirm(f"write: {shown} ({len(content)} chars)"):
        return _refused("write")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"wrote {shown}"


_HANDLERS = {"run": _run_command, "read_file": _read_file, "edit_file": _edit_file, "write_file": _write_file}


def call_tool(name: str, args: dict, cwd: Path, confirm) -> str:
    """Carry out one tool call and describe the outcome for the model. Failures are described too, never raised:
    a single bad call should not end the run."""
    root = cwd.resolve()
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"unknown tool {name} (the tools are {', '.join(_HANDLERS)})"
    try:
        return handler(args, root, confirm)
    except Exception as failure:  # noqa: BLE001 - whatever went wrong, the model reads it and carries on
        return f"error: {failure}"


def _ask_at_terminal(what: str) -> bool:
    """Ask the person at the terminal; with no terminal to ask, the answer is no."""
    if not sys.stdin.isatty():
        return False
    reply = input(f"  allow {what}? [y/N] ")
    return reply.strip().lower() in {"y", "yes"}


def _arguments(function: dict):
    """A tool call's arguments: some servers send a dict, others a JSON string (unreadable JSON counts as none)."""
    raw = function.get("arguments") or {}
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _answer_calls(calls: list[dict], messages: list[dict], cwd: Path, confirm, out) -> None:
    """Run each requested call, show a one-line trace of it, and add its result to the conversation."""
    for requested in calls:
        function = requested.get("function") or {}
        args = _arguments(function)
        out(f"· {function.get('name')} {args.get('command') or args.get('path') or ''}")
        messages.append({"role": "tool", "tool_name": function.get("name", ""),
                         "content": call_tool(function.get("name", ""), args, cwd, confirm)})


def _loop(chat_fn, model: str, messages: list[dict], cwd: Path, confirm, max_steps: int, out) -> tuple[str, int, dict]:
    """Converse with `model` until it replies without calling a tool, growing `messages` as it goes. Returns its final
    words (or why the run was cut short), how many turns it took, and the input/output tokens spent."""
    used = {"input": 0, "output": 0}
    previous, streak = None, 0
    for turn in range(1, max_steps + 1):
        reply = chat_fn(model, messages)
        used["input"] += int(reply.get("prompt_eval_count") or 0)
        used["output"] += int(reply.get("eval_count") or 0)
        said = reply.get("message") or {}
        calls = said.get("tool_calls") or []
        messages.append({"role": "assistant", "content": said.get("content", ""), "tool_calls": calls})
        if calls:
            # Small models sometimes loop on one call; the same calls REPEATS turns running end the run.
            fingerprint = json.dumps([c.get("function") for c in calls], sort_keys=True)
            streak = streak + 1 if fingerprint == previous else 1
            previous = fingerprint
            if streak >= REPEATS:
                verdict = f"(stopped: the model repeated the same step {REPEATS} times)"
                # Calls left unanswered would break the next turn of a shared conversation (--by-step).
                messages[-1] = {"role": "assistant", "content": verdict}
                return verdict, turn, used
            _answer_calls(calls, messages, cwd, confirm, out)
            continue
        return said.get("content", ""), turn, used          # a reply with no tool call: the model is done
    return f"(stopped after {max_steps} steps)", max(max_steps, 0), used


def _system(piece: store.Piece, cwd: Path) -> dict:
    """The opening system message: the working rules, then the piece itself."""
    today = _dt.date.today().isoformat()
    return {"role": "system", "content": SYSTEM.format(cwd=cwd, today=today, title=piece.title, body=piece.body)}


def _confirmer(yes: bool):
    return (lambda _what: True) if yes else _ask_at_terminal


def _with_totals(tokens: dict) -> dict:
    """Token counts in the shape the task log uses (no prompt cache on these backends)."""
    return {**tokens, "cache_read": 0, "cache_write": 0, "total": tokens["input"] + tokens["output"]}


def _piece_or_fail(piece_id: str) -> store.Piece:
    found = store.get(piece_id)
    if found is None:
        raise LookupError(f"no piece {piece_id}")
    return found


def delegate(piece_id: str, request: str, model: str = DEFAULT_MODEL, cwd: Path | None = None, yes: bool = False,
             max_steps: int = MAX_STEPS, out=print, chat_fn=chat, platform: str = "local") -> dict:
    """Run the task and record it. Returns the task id, the model's last message, the steps, the time and the tokens."""
    piece = _piece_or_fail(piece_id)
    folder = (cwd or Path.cwd()).resolve()
    conversation = [_system(piece, folder), {"role": "user", "content": request}]
    started = time.monotonic()
    summary, turns, spent = _loop(chat_fn, model, conversation, folder, _confirmer(yes), max_steps, out)
    elapsed = time.monotonic() - started
    tokens = _with_totals(spent)
    task_id = _log_run(piece.id, platform, model, elapsed, tokens, request, folder)
    return {"task_id": task_id, "summary": summary, "steps": turns, "duration_s": round(elapsed, 1),
            "tokens": tokens}


def _log_run(piece_id: str, platform: str, model: str, elapsed: float, tokens: dict, request: str,
             folder: Path) -> str:
    """Count the piece as used and add the run to the task log, as a task like any other; returns its id."""
    store.touch(piece_id)
    return ev.record_external(platform, model, [piece_id], elapsed, tokens, request=request,
                              project=paths.project_of(folder))


# ------------------------------------------------------------------------------------------------ one model per step
def parse_spec(spec: str) -> tuple[str, str] | None:
    """A `**Model:**` line as (platform, model): `local`, `meta`, `baseten`, `ollama:<model>`, `meta:<model>`,
    `baseten:<model>`. None when it is none of these, so a typo never sends a step somewhere unexpected."""
    from athos.adapters import meta
    spec = spec.strip().strip("`")
    if spec == "local":
        return "local", DEFAULT_MODEL
    if spec == "meta":
        return "meta", meta.DEFAULT_MODEL
    if spec == "baseten":
        from athos.adapters import baseten
        return "baseten", baseten.DEFAULT_MODEL
    backend, _, model = spec.partition(":")
    if model and backend in ("ollama", "local"):
        return "local", model
    if model and backend in ("meta", "baseten"):
        return backend, model
    return None


def spec_of(platform: str, model: str) -> str:
    """The `**Model:**` line for a (platform, model), short when it is the default one."""
    from athos.adapters import meta
    if platform == "meta":
        return "meta" if model == meta.DEFAULT_MODEL else f"meta:{model}"
    if platform == "baseten":
        from athos.adapters import baseten
        return "baseten" if model == baseten.DEFAULT_MODEL else f"baseten:{model}"
    return "local" if model == DEFAULT_MODEL else f"ollama:{model}"


def plan(piece: store.Piece, default: tuple[str, str]) -> list[tuple[object, str, str]]:
    """Each statement with the (platform, model) it runs on: its own `**Model:**`, else the task's."""
    from athos import wiki
    out = []
    for s in wiki.statements(piece):
        if s.model and parse_spec(s.model) is None:
            raise ValueError(f"#{s.id}: unknown model {s.model!r} (use local, meta, baseten, ollama:<model>, "
                             f"meta:<model> or baseten:<model>)")
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
    piece = _piece_or_fail(piece_id)
    steps = plan(piece, default)
    hosted = [f"#{s.id}" for s, platform, _ in steps if platform != "local"]
    if hosted and not allow_hosted:
        raise PermissionError(f"{', '.join(hosted)} would run on a hosted model (Meta Model API / Baseten), which "
                              f"sends the request and the files it reads off this machine. Add --allow-meta to allow "
                              f"that.")
    from athos.adapters import baseten
    chat_fns = {"local": chat, "meta": meta.chat, "baseten": baseten.chat, **(chat_fns or {})}
    cwd = (cwd or Path.cwd()).resolve()
    confirm = _confirmer(yes)
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
    tokens = _with_totals({k: sum(d["tokens"][k] for d in done) for k in ("input", "output")})
    elapsed = time.monotonic() - t0
    platforms = {d["platform"] for d in done} or {default[0]}
    models = list(dict.fromkeys(d["model"] for d in done)) or [default[1]]
    store.touch(piece.id)
    ev.record_external(platforms.pop() if len(platforms) == 1 else "mixed", "+".join(models), [piece.id], elapsed,
                       tokens, request=request, project=paths.project_of(cwd), task_id=tid, steps=done)
    return {"task_id": tid, "summary": final, "steps": done, "duration_s": round(elapsed, 1), "tokens": tokens}
