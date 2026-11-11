"""Athos's parts as contracts, so each can be swapped without touching the rest.

Five services, each a small Protocol with the default implementation Athos ships:

- `store`        where the know-how lives (markdown pages in ~/.athos/know-how)
- `recorder`     the append-only event log (~/.athos/events.jsonl), the source of truth for learning
- `router`       which pages a request loads
- `consolidator` the overnight review: reads the log, proposes what to keep in permanent memory (never writes)
- `runner`       a model that runs a task with a way of working (athos delegate's backends)

`get(name)` gives the one in use; `use(name, impl)` replaces it (a test, another store, another consolidator), and
`ATHOS_SERVICES="consolidator=pkg.mod:Thing,..."` does the same from the environment. Nothing here changes what Athos
does by default: the defaults are the modules that already did the work.
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Callable, Iterable, Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    def get(self, piece_id: str): ...
    def all_pieces(self) -> list: ...


@runtime_checkable
class Recorder(Protocol):
    def append(self, event: dict) -> None: ...
    def events(self) -> list[dict]: ...


@runtime_checkable
class Router(Protocol):
    def relevant(self, request: str, pieces: list) -> list: ...


@runtime_checkable
class Consolidator(Protocol):
    def review(self, events: Iterable[dict], pieces: list) -> dict: ...


@runtime_checkable
class Runner(Protocol):
    def chat(self, model: str, messages: list[dict]) -> dict: ...


class _Module:
    """A module that already does the job, seen through a service's methods."""

    def __init__(self, path: str, **names: str):
        self._path, self._names = path, names

    def __getattr__(self, attr: str) -> Any:
        return getattr(importlib.import_module(self._path), self._names.get(attr, attr))


def _default_router():
    class _Router:
        def relevant(self, request: str, pieces: list) -> list:
            from athos import load
            return load.relevant(request, pieces)
    return _Router()


def _default_consolidator():
    from athos import consolidate
    return consolidate.Review()


def _default_runner():
    class _Runner:
        def chat(self, model: str, messages: list[dict]) -> dict:
            from athos.adapters import meta
            return meta.chat(model, messages)
    return _Runner()


DEFAULTS: dict[str, Callable[[], Any]] = {
    "store": lambda: _Module("athos.store"),
    "recorder": lambda: _Module("athos.eval"),
    "router": _default_router,
    "consolidator": _default_consolidator,
    "runner": _default_runner,
}
CONTRACTS = {"store": Store, "recorder": Recorder, "router": Router, "consolidator": Consolidator, "runner": Runner}
_IN_USE: dict[str, Any] = {}


def _from_env(name: str):
    for item in (os.environ.get("ATHOS_SERVICES") or "").split(","):
        key, _, target = item.strip().partition("=")
        if key == name and ":" in target:
            mod, _, attr = target.partition(":")
            obj = getattr(importlib.import_module(mod), attr)
            return obj() if isinstance(obj, type) else obj
    return None


def get(name: str):
    """The service in use: one set with `use`, else one named in ATHOS_SERVICES, else Athos's own."""
    if name not in DEFAULTS:
        raise KeyError(f"no service {name!r}: {', '.join(DEFAULTS)}")
    if name not in _IN_USE:
        _IN_USE[name] = _from_env(name) or DEFAULTS[name]()
    return _IN_USE[name]


def use(name: str, impl) -> None:
    """Replace a service (None goes back to the default). It must keep the contract's methods."""
    if name not in DEFAULTS:
        raise KeyError(f"no service {name!r}")
    if impl is None:
        _IN_USE.pop(name, None)
        return
    missing = [m for m in CONTRACTS[name].__annotations__ or {} if not hasattr(impl, m)]
    missing += [m for m in dir(CONTRACTS[name]) if not m.startswith("_") and not hasattr(impl, m)]
    if missing:
        raise TypeError(f"{name} needs {', '.join(sorted(set(missing)))}")
    _IN_USE[name] = impl
