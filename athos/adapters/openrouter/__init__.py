"""OpenRouter as a backend for `athos delegate`: Meta's open-weights Muse Spark Open through OpenRouter, which serves it
from several inference providers (BaseTen, Fireworks, Together, Nebius, Modal…), in the same small loop and with the
same tools as `--backend meta`.

    athos delegate <piece> "<request>" --backend openrouter                  meta/muse-spark-open
    athos delegate <piece> "<request>" --backend openrouter --model meta/muse-spark-1.3

OpenRouter's Chat Completions endpoint at https://openrouter.ai/api/v1 is OpenAI-compatible, authenticated with
`Authorization: Bearer <OPENROUTER_API_KEY>`, with tool calling for this model and `reasoning: {"effort": ...}` for
reasoning models. The key is `OPENROUTER_API_KEY`, from the environment or from an `OPENROUTER_API_KEY=...` line in
`~/.athos/.env` (or the store's own `.env`), read the way the Meta adapter reads its key; it is never printed. The task
is recorded as platform `openrouter`.
"""

from __future__ import annotations

import urllib.request

from athos import paths
from athos.adapters import meta

BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "meta/muse-spark-open"
KEY = "OPENROUTER_API_KEY"
MAX_TOKENS = meta.MAX_TOKENS     # a reasoning model: the cap covers its thinking and its answer
REASONING = "low"                # a mastered task needs little thinking; lower effort is faster and cheaper
LABEL = "OpenRouter"
# OpenRouter's list price for meta/muse-spark-open (US$ per 1M tokens, input / output), from its public model list on
# 2026-11-02: the same as Muse Spark on Meta Model API.
PRICE = (1.25, 4.25)


def api_key() -> str | None:
    return meta.env_key(KEY)


def chat(model: str, messages: list[dict], timeout: float = 300, urlopen=None, tools: bool = True) -> dict:
    """One Chat Completions call to OpenRouter. `tools=False` sends none: a plain answer, for replaying a case."""
    key = api_key()
    if not key:
        raise PermissionError(f"no OpenRouter API key: set {KEY}, or put a {KEY}=... line in {paths.home() / '.env'}")
    return meta.post_chat(BASE, key, model, messages, timeout, urlopen or urllib.request.urlopen, tools,
                          {"max_tokens": MAX_TOKENS, "reasoning": {"effort": REASONING}})
