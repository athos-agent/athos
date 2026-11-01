"""Meta Model API as a backend for `athos delegate`: the same small loop and tools as a local model, with Meta's model
behind it instead of Ollama.

    athos delegate <piece> "<request>" --backend meta                    muse-spark-1.3, fast and low cost
    athos delegate <piece> "<request>" --backend meta --model muse-wonder-1.0

It stands in for a local model when your machine cannot run one fast enough: the task still runs in Athos's own loop,
in the current folder, asking before every command and write. The key is `MODEL_API_KEY`, from the environment or
from a `MODEL_API_KEY=...` line in `~/.athos/.env` (or the store's own `.env`); it is never printed. The task is recorded as platform `meta`.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from athos import paths

BASE = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.3"
MAX_TOKENS = 4000        # a reasoning model: with a small cap it spends it all thinking and never calls a tool
REASONING = "low"


def env_key(name: str) -> str | None:
    """The person's key `name`: from the environment, else from a `NAME=...` line in the store's `.env` or
    `~/.athos/.env`. Never printed. Every hosted backend reads its key this way (Meta's `MODEL_API_KEY`, Baseten's
    `BASETEN_API_KEY`)."""
    if os.environ.get(name):
        return os.environ[name]
    # The key is the person's, not one store's: a store of its own (a demo, ATHOS_HOME) still finds ~/.athos/.env.
    for f in dict.fromkeys([paths.home() / ".env", Path.home() / ".athos" / ".env"]):
        if f.is_file():
            for line in f.read_text().splitlines():
                k, _, v = line.strip().removeprefix("export ").partition("=")
                if k.strip() == name and v.strip():
                    return v.strip().strip("'\"")
    return None


def api_key() -> str | None:
    return env_key("MODEL_API_KEY")


def to_openai(messages: list[dict]) -> list[dict]:
    """The loop's messages (Ollama's shape) in Chat Completions' shape: arguments as JSON text, and each tool result
    tied to the call it answers, in order."""
    out, pending = [], []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = []
            for i, c in enumerate(m["tool_calls"]):
                fn = c.get("function") or {}
                cid = c.get("id") or f"call_{len(out)}_{i}"
                args = fn.get("arguments")
                calls.append({"id": cid, "type": "function", "function": {
                    "name": fn.get("name", ""), "arguments": args if isinstance(args, str) else json.dumps(args or {})}})
                pending.append(cid)
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": calls})
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": pending.pop(0) if pending else "call_0",
                        "content": m.get("content", "")})
        else:
            out.append({"role": m["role"], "content": m.get("content", "")})
    return out


def from_openai(r: dict) -> dict:
    """A Chat Completions reply in the shape the loop reads: the message with its tool calls, and the token counts."""
    msg = ((r.get("choices") or [{}])[0].get("message")) or {}
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        calls.append({"id": c.get("id"), "function": {"name": fn.get("name", ""), "arguments": args}})
    u = r.get("usage") or {}
    return {"message": {"content": msg.get("content") or "", "tool_calls": calls}, "model": r.get("model"),
            "prompt_eval_count": int(u.get("prompt_tokens") or 0), "eval_count": int(u.get("completion_tokens") or 0)}


def chat(model: str, messages: list[dict], timeout: float = 300, urlopen=urllib.request.urlopen,
         tools: bool = True) -> dict:
    """One Chat Completions call to Meta Model API. `tools=False` sends none: a plain answer, for replaying a case."""
    key = api_key()
    if not key:
        raise PermissionError(f"no Meta Model API key: set MODEL_API_KEY, or put a MODEL_API_KEY=... line in "
                              f"{paths.home() / '.env'}")
    return post_chat(BASE, key, model, messages, timeout, urlopen, tools,
                     {"max_tokens": MAX_TOKENS, "reasoning_effort": REASONING})


def post_chat(base: str, key: str, model: str, messages: list[dict], timeout: float = 300,
              urlopen=urllib.request.urlopen, tools: bool = True, extra: dict | None = None) -> dict:
    """One OpenAI-compatible Chat Completions call to `base` (Meta's, Baseten's), taking and returning the loop's
    shape. `extra` adds to the request body (max_tokens, reasoning_effort)."""
    from athos.delegate import TOOLS
    req_body = {"model": model, "messages": to_openai(messages), **(extra or {})}
    if tools:
        req_body["tools"] = TOOLS
    body = json.dumps(req_body).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return from_openai(json.loads(resp.read()))
