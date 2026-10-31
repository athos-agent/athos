"""Load by meaning too: optional local embeddings (Ollama `/api/embed`), off by default (`athos embed on`).

Only a piece's title, "when" and its statements' `When:` lines are embedded (what the piece is for, not its steps),
cached under `<home>/index/` by piece id and a hash of that text and the model, so an edited piece is embedded
again and nothing else is. On the prompt hook the request is embedded once, under a time cap: with Ollama down,
slow or the model not loaded, the router stays lexical, exactly as without this. Pieces missing from the index are
filled by a detached `athos embed --refresh`, never on the hot path. Nothing leaves the machine.
"""

from __future__ import annotations

import array
import base64
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from athos import paths, store

DEFAULT_MODEL = "embeddinggemma"
BUDGET_S = 0.3             # the request's embedding, on the prompt hook; past it the router stays lexical
KEEP_ALIVE = "30m"         # Ollama keeps the model loaded this long after a call, so the next prompt is warm
# Per model: the prefixes it was trained with (query, document) and how many leading dimensions to keep. Both
# models are trained to keep their meaning in the first dimensions (Matryoshka), and 256 makes the dot products on
# the hot path three times cheaper.
MODELS = {"embeddinggemma": ("task: search result | query: ", "title: none | text: ", 256),
          "nomic-embed-text": ("search_query: ", "search_document: ", 256)}
LOCK_S = 600
# Requests that need no know-how: a piece's mean cosine to them is how close it is to anything, taken off its
# cosine to the request. Without it, in `athos bench route`, a few pieces were the closest to most requests that
# need nothing ("what time is it" was nearest the training week). Changing them changes every piece's hash, so the
# index is rebuilt.
PROBES = ("hello", "can you help me with something?", "thanks, that works", "continue", "explain this code",
          "what do you think?", "make it shorter", "hola, ¿me ayudás con algo?", "gracias, anduvo", "seguí",
          "¿qué opinás?", "hacelo más corto")


def _spec(model: str) -> tuple[str, str, int | None]:
    return MODELS.get(model.split(":")[0], ("", "", None))


# ------------------------------------------------------------------------------------------------ the setting
def settings() -> dict:
    from athos import start
    return start.config().get("embed") or {}


def enabled() -> bool:
    return bool(settings().get("on"))


def chosen_model() -> str:
    return settings().get("model") or DEFAULT_MODEL


def set_embed(on: bool, model_name: str | None = None) -> dict:
    """`athos embed on|off`: kept with the person's other choices (`<home>/config.json`)."""
    from athos import start
    c = start.config()
    s = dict(c.get("embed") or {})
    s["on"] = on
    if model_name:
        s["model"] = model_name
    c["embed"] = s
    start.config_file().parent.mkdir(parents=True, exist_ok=True)
    start.config_file().write_text(json.dumps(c, indent=1) + "\n")
    return s


# ------------------------------------------------------------------------------------------------ vectors
def ollama(texts: list[str], model_name: str, timeout: float) -> list[list[float]]:
    """One local Ollama call (the same host `athos delegate` uses)."""
    from athos import delegate
    body = json.dumps({"model": model_name, "input": texts, "keep_alive": KEEP_ALIVE}).encode()
    req = urllib.request.Request(delegate.host() + "/api/embed", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["embeddings"]


def _unit(v, dims: int | None) -> list[float]:
    v = list(v[:dims] if dims else v)
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def text_of(p: store.Piece) -> str:
    """What a piece is for: its title, its "when" and when each of its statements applies."""
    from athos import wiki
    whens = [s.when for s in wiki.statements(p) if s.when and s.when != p.when]
    return ". ".join([p.title, p.when, *whens])


def _hash(p: store.Piece, model_name: str) -> str:
    return hashlib.sha1(f"{model_name}\n{PROBES}\n{text_of(p)}".encode()).hexdigest()[:16]


def index_file(model_name: str) -> Path:
    return paths.home() / "index" / f"embed-{store.slugify(model_name)}.json"


def load_index(model_name: str) -> dict[str, dict]:
    """{piece id: {"h": text hash, "v": unit vector, "b": usual closeness}}; vectors are float32 in base64, so the
    hook reads them fast."""
    try:
        raw = json.loads(index_file(model_name).read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for pid, e in raw.items():
        a = array.array("f")
        a.frombytes(base64.b64decode(e["v"]))
        out[pid] = {"h": e["h"], "v": a.tolist(), "b": e.get("b", 0.0)}
    return out


def _save_index(model_name: str, idx: dict[str, dict]) -> None:
    f = index_file(model_name)
    f.parent.mkdir(parents=True, exist_ok=True)
    raw = {pid: {"h": e["h"], "v": base64.b64encode(array.array("f", e["v"]).tobytes()).decode(), "b": e["b"]}
           for pid, e in idx.items()}
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw))
    tmp.replace(f)                                     # the hook never reads a half-written index


def stale(pieces: list[store.Piece], idx: dict, model_name: str) -> list[store.Piece]:
    return [p for p in pieces if idx.get(p.id, {}).get("h") != _hash(p, model_name)]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def refresh(pieces: list[store.Piece], model: str | None = None, embed_fn=None, write: bool = True,
            batch: int = 32, timeout: float = 120) -> dict[str, dict]:
    """Embed the pieces missing from the index or changed since; drop the ones no longer in the store. Each piece
    also keeps its usual closeness to any request ("b", its mean cosine to PROBES), taken off at prompt time."""
    name = model or chosen_model()
    embed_fn = embed_fn or ollama
    q_prefix, doc, dims = _spec(name)
    idx = {pid: e for pid, e in load_index(name).items() if pid in {p.id for p in pieces}}
    todo = stale(pieces, idx, name)
    probes = [_unit(v, dims) for v in embed_fn([q_prefix + t for t in PROBES], name, timeout)] if todo else []
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        for p, v in zip(chunk, embed_fn([doc + text_of(p) for p in chunk], name, timeout)):
            u = _unit(v, dims)
            idx[p.id] = {"h": _hash(p, name), "v": u, "b": sum(_dot(u, pr) for pr in probes) / len(probes)}
    if write:
        _save_index(name, idx)
    return idx


def _lock() -> Path:
    return paths.home() / "index" / ".refresh.lock"


def spawn_refresh(popen=None) -> bool:
    """A detached, low-priority `athos embed --refresh` (once at a time): it also loads the model in Ollama, so the
    next prompt finds it warm."""
    lock = _lock()
    try:
        if time.time() - lock.stat().st_mtime < LOCK_S:
            return False
    except OSError:
        pass
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))
    me = Path(__file__).resolve().parents[2] / "bin" / "athos"
    argv = [sys.executable, str(me), "embed", "--refresh"]
    if os.name == "posix" and Path("/usr/bin/nice").exists():
        argv = ["/usr/bin/nice", "-n", "19", *argv]
    (popen or subprocess.Popen)(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    return True


def scores(prompt: str, pieces: list[store.Piece], model: str | None = None, embed_fn=None,
           timeout: float = BUDGET_S, index: dict | None = None, spawn: bool = True) -> dict[str, float] | None:
    """How close the request is to each indexed piece (its cosine, less the piece's usual cosine to any request), or
    None when the request can't be embedded in time (the router then stays lexical). Pieces not indexed yet are
    left out, and a background refresh is started."""
    name = model or chosen_model()
    idx = index if index is not None else load_index(name)
    if spawn and stale(pieces, idx, name):
        spawn_refresh()
    q_prefix, _doc, dims = _spec(name)
    try:
        q = _unit((embed_fn or ollama)([q_prefix + prompt], name, timeout)[0], dims)
    except Exception:                    # Ollama down, timed out, model missing: lexical, as before (and warm it)
        if spawn and embed_fn is None:
            spawn_refresh()
        return None
    hashes = {p.id: _hash(p, name) for p in pieces}
    return {pid: _dot(q, e["v"]) - e.get("b", 0.0) for pid, e in idx.items() if hashes.get(pid) == e["h"]}
