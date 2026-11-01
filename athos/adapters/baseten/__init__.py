"""Baseten Model APIs as a backend for `athos delegate`: Meta's open-weights Muse Spark Open, hosted by Baseten, in the
same small loop and with the same tools as `--backend meta`.

    athos delegate <piece> "<request>" --backend baseten                  meta-models/muse-spark-open-1026
    athos delegate <piece> "<request>" --backend baseten --model meta-models/muse-spark-open

Baseten documents an OpenAI-compatible Chat Completions endpoint at https://inference.baseten.co/v1, authenticated with
`Authorization: Bearer <BASETEN_API_KEY>`, with model slugs as `organization/model`, tool calling on every model, and
`reasoning_effort` (low | medium | high | xhigh, default xhigh) for Muse Spark Open, which always reasons. The key is
`BASETEN_API_KEY`, from the environment or from a `BASETEN_API_KEY=...` line in `~/.athos/.env` (or the store's own
`.env`), read the way the Meta adapter reads its key; it is never printed. The task is recorded as platform `baseten`.
"""

from __future__ import annotations

import urllib.request

from athos import paths
from athos.adapters import meta

BASE = "https://inference.baseten.co/v1"
# The slug the Meta hackathon names; Baseten's own model page lists `meta-models/muse-spark-open` (--model).
DEFAULT_MODEL = "meta-models/muse-spark-open-1026"
KEY = "BASETEN_API_KEY"
MAX_TOKENS = meta.MAX_TOKENS     # a reasoning model: the cap covers its thinking and its answer
REASONING = "low"                # Baseten's default for this model is xhigh: slow and costly for a mastered task
LABEL = "Baseten Model APIs"


def api_key() -> str | None:
    return meta.env_key(KEY)


def chat(model: str, messages: list[dict], timeout: float = 300, urlopen=None, tools: bool = True) -> dict:
    """One Chat Completions call to Baseten. `tools=False` sends none: a plain answer, for replaying a case."""
    key = api_key()
    if not key:
        raise PermissionError(f"no Baseten API key: set {KEY}, or put a {KEY}=... line in {paths.home() / '.env'}")
    return meta.post_chat(BASE, key, model, messages, timeout, urlopen or urllib.request.urlopen, tools,
                          {"max_tokens": MAX_TOKENS, "reasoning_effort": REASONING})
