"""Meta's models through Meta Model API, inside the agents you already use.

    athos delegate <piece> "<request>" --via claude [--model muse-spark-1.3]   Claude Code, driven by a Meta model
    athos delegate <piece> "<request>" --via codex  [--model muse-wonder-1.0]  Codex, driven by a Meta model

The agent runs once, headless, in the current folder, with the piece as its know-how and a Meta model behind it. The
provider settings exist only in that one process: your own Claude Code and Codex setups are never touched. The agent
gets a throwaway Athos home, so it sees only the piece you delegated and saves nothing; the task is then recorded in
your report with the agent as platform and the Meta model that answered, and is marked like any other.

The key is `MODEL_API_KEY`, from the environment or from `~/.athos/.env` (a `MODEL_API_KEY=...` line). It is never
printed and never written anywhere else.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from athos import eval as ev, paths, store

HOST = "https://api.meta.ai"
DEFAULT_MODEL = "muse-spark-1.3"
VIAS = ("claude", "codex")

KNOW_HOW = """Follow the user's know-how below exactly: it is how this person does this kind of task. Look at the \
files before changing them, change only what the task needs, and never install or uninstall software.

# Know-how: {title}

{body}"""


def api_key() -> str | None:
    if os.environ.get("MODEL_API_KEY"):
        return os.environ["MODEL_API_KEY"]
    f = paths.home() / ".env"
    if f.is_file():
        for line in f.read_text().splitlines():
            k, _, v = line.strip().removeprefix("export ").partition("=")
            if k.strip() == "MODEL_API_KEY" and v.strip():
                return v.strip().strip("'\"")
    return None


def claude_env(key: str, model: str) -> dict:
    """Meta's settings for Claude Code: every model alias on the Meta model, so no path falls back to a Claude model."""
    env = {"ANTHROPIC_BASE_URL": HOST, "ANTHROPIC_AUTH_TOKEN": key, "ENABLE_TOOL_SEARCH": "true"}
    for var in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"):
        env[var] = model
    return env


def codex_config(model: str) -> list[str]:
    """Meta as a Codex provider, passed inline so no config.toml is written."""
    pairs = [("model_provider", "meta"), ("model_providers.meta.name", "Meta Model API"),
             ("model_providers.meta.base_url", HOST + "/v1"), ("model_providers.meta.env_key", "MODEL_API_KEY"),
             ("model_providers.meta.wire_api", "responses")]
    args = ["-m", model]
    for k, v in pairs:
        args += ["-c", f'{k}="{v}"']
    return args


def command(via: str, request: str, know_how: str, model: str, cwd: Path, yes: bool, max_steps: int) -> list[str]:
    if via == "claude":
        cmd = ["claude", "-p", request, "--append-system-prompt", know_how, "--output-format", "json",
               "--permission-mode", "acceptEdits", "--max-turns", str(max_steps)]
        # Without --yes the agent may read and edit files, but no shell command runs: a headless run cannot ask.
        return cmd + ["--allowedTools", "Bash Read Edit Write Glob Grep" if yes else "Read Edit Write Glob Grep"]
    if via == "codex":
        return (["codex", "exec", "-C", str(cwd), "--skip-git-repo-check", "--json", "-s", "workspace-write"]
                + codex_config(model) + [f"{know_how}\n\n# Task\n\n{request}"])
    raise ValueError(f"unknown agent {via}; use one of {', '.join(VIAS)}")


def parse_claude(stdout: str, model: str) -> dict:
    r = json.loads(stdout or "{}")
    u = r.get("usage") or {}
    tokens = {"input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
              "cache_read": int(u.get("cache_read_input_tokens") or 0),
              "cache_write": int(u.get("cache_creation_input_tokens") or 0)}
    used = [m for m in (r.get("modelUsage") or {}) if m]
    return {"summary": r.get("result") or "", "error": bool(r.get("is_error")), "steps": r.get("num_turns"),
            "model": used[0] if len(used) == 1 else model, "tokens": tokens}


def parse_codex(stdout: str, model: str) -> dict:
    summary, tokens, steps, error = "", {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, 0, False
    for line in stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "agent_message":
            summary = item.get("text", "")
        elif e.get("type") == "item.completed" and item.get("type") == "command_execution":
            steps += 1
        elif e.get("type") == "turn.completed":
            u = e.get("usage") or {}
            tokens["input"] += int(u.get("input_tokens") or 0)
            tokens["output"] += int(u.get("output_tokens") or 0)
            tokens["cache_read"] += int(u.get("cached_input_tokens") or 0)
        elif e.get("type") in ("turn.failed", "error"):
            error = True
            summary = summary or str((e.get("error") or {}).get("message") or e.get("message") or "")
    return {"summary": summary, "error": error, "steps": steps, "model": model, "tokens": tokens}


def delegate(piece_id: str, request: str, via: str = "claude", model: str = DEFAULT_MODEL, cwd: Path | None = None,
             yes: bool = False, max_steps: int = 20, run=subprocess.run) -> dict:
    """Run the task in the agent on a Meta model and record it. Returns the task id, the agent's last message, the
    model that answered, the time and the tokens."""
    piece = store.get(piece_id)
    if piece is None:
        raise LookupError(f"no piece {piece_id}")
    key = api_key()
    if not key:
        raise PermissionError("no Meta Model API key: set MODEL_API_KEY, or put a MODEL_API_KEY=... line in "
                              f"{paths.home() / '.env'}")
    cwd = (cwd or Path.cwd()).resolve()
    know_how = KNOW_HOW.format(title=piece.title, body=piece.body)
    with tempfile.TemporaryDirectory(prefix="athos-delegate-") as scratch:
        env = {**os.environ, "ATHOS_HOME": scratch, "ATHOS_CAPTURE": "off", "MODEL_API_KEY": key}
        if via == "claude":
            env.update(claude_env(key, model))
        else:
            env["CODEX_HOME"] = str(Path(scratch) / "codex")       # never the user's ~/.codex, nor their OpenAI login
            Path(env["CODEX_HOME"]).mkdir()
        t0 = time.monotonic()
        p = run(command(via, request, know_how, model, cwd, yes, max_steps), cwd=cwd, env=env, capture_output=True,
                text=True, stdin=subprocess.DEVNULL)
        duration = time.monotonic() - t0
    r = (parse_claude if via == "claude" else parse_codex)(p.stdout, model)
    if p.returncode != 0 and not r["summary"]:
        r["summary"] = (p.stderr or "").strip()[-500:] or f"(the agent exited with code {p.returncode})"
    r["tokens"]["total"] = r["tokens"]["input"] + r["tokens"]["output"]
    if p.returncode != 0 and not r["tokens"]["total"]:
        raise RuntimeError(f"{via} did not run the task: {r['summary']}")   # nothing ran: nothing to record
    store.touch(piece.id)
    platform = "claude-code" if via == "claude" else "codex"
    r["task_id"] = ev.record_external(platform, r["model"], [piece.id], duration, r["tokens"], request=request,
                                      project=paths.project_of(cwd))
    r.update(platform=platform, duration_s=round(duration, 1), exit_code=p.returncode)
    return r
