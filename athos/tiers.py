"""Model tiers: which models learn and which apply what was learned.

A model is `frontier` (it may learn new ways of working) or `apply` (it uses what is already known). The tiers are
lists of patterns (`fnmatch`, case-insensitive) kept in `<home>/config.json` under `"tiers"`; with none saved the
defaults below hold. A model no pattern matches counts as `apply`: an unknown model never learns.

Two modes follow from the tier, for the phases that act on them: `learn` (frontier) and `collaborate` (apply). A
frontier session also collaborates when a relevant piece is in reach. The router delivers by tier (load.deliver): a
frontier model gets an index of the pieces in reach and opens what it needs; an apply model gets the pieces.
"""

from __future__ import annotations

import fnmatch
import re

FRONTIER, APPLY = "frontier", "apply"
TIERS = (FRONTIER, APPLY)
DEFAULTS = {FRONTIER: ["claude-fable-*", "claude-mythos-*", "claude-opus-*"],
            APPLY: ["claude-sonnet-*", "claude-haiku-*"]}
LEARN, COLLABORATE = "learn", "collaborate"


def _config() -> dict:
    from athos import start
    return start.config()


def patterns() -> dict[str, list[str]]:
    """The patterns of each tier: the saved ones, or the defaults for a tier with none saved."""
    saved = _config().get("tiers")
    saved = saved if isinstance(saved, dict) else {}
    out = {}
    for tier in TIERS:
        given = saved.get(tier)
        out[tier] = [str(p) for p in given] if isinstance(given, list) else list(DEFAULTS[tier])
    return out


def _bare(model: str) -> str:
    """A model id as matched: lower case, without a context-size suffix such as `[1m]`."""
    return re.sub(r"\[[^\]]*\]$", "", model.strip().lower())


def tier_of(model: str | None) -> str:
    """The tier of a model id. A pattern with no wildcard is an exact id and wins over every pattern; then the
    frontier patterns, then the apply ones; anything else is `apply`."""
    if not model or not isinstance(model, str):
        return APPLY
    name = _bare(model)
    tiers = patterns()
    for tier in TIERS:
        if any(not re.search(r"[*?\[]", p) and _bare(p) == name for p in tiers[tier]):
            return tier
    for tier in TIERS:
        if any(fnmatch.fnmatchcase(name, p.lower()) for p in tiers[tier]):
            return tier
    return APPLY


def mode_of(tier: str) -> str:
    """The mode a tier works in: `learn` for frontier, `collaborate` for apply."""
    return LEARN if tier == FRONTIER else COLLABORATE


def collaborates(tier: str, piece_in_reach: bool) -> bool:
    """Whether Athos collaborates: always with an apply model; with a frontier one when a relevant piece is in reach."""
    return tier != FRONTIER or bool(piece_in_reach)


def describe(model: str | None, piece_in_reach: bool | None = None) -> dict:
    """The fields the `model` and `route` events and `athos status --json` carry: `tier`, `work_mode` (learn or
    collaborate; `mode` in a route event is the loading mode) and, when known, `collaborates`."""
    tier = tier_of(model)
    out = {"tier": tier, "work_mode": mode_of(tier)}
    if piece_in_reach is not None:
        out["collaborates"] = collaborates(tier, piece_in_reach)
    return out


def _save(tiers: dict[str, list[str]] | None) -> None:
    from athos import start

    def change(c: dict) -> None:
        if tiers is None:
            c.pop("tiers", None)
        else:
            c["tiers"] = tiers
    start.change_config(change)


def add(tier: str, items: list[str]) -> dict[str, list[str]]:
    """Put patterns (or exact ids) in a tier, taking them out of the other one."""
    tiers = patterns()
    for p in items:
        for other in TIERS:
            if other != tier and p in tiers[other]:
                tiers[other].remove(p)
        if p not in tiers[tier]:
            tiers[tier].append(p)
    _save(tiers)
    return tiers


def remove(tier: str, items: list[str]) -> dict[str, list[str]]:
    tiers = patterns()
    tiers[tier] = [p for p in tiers[tier] if p not in items]
    _save(tiers)
    return tiers


def reset() -> dict[str, list[str]]:
    _save(None)
    return patterns()
