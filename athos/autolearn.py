"""Autonomous learning: on a frontier model Athos keeps what a task taught without asking anyone, and only on objective
evidence; apply models never create or change a piece, they only add evidence.

The settings live in `<home>/config.json` under `"autolearn"`; anything not saved there takes the default below.

    on                  autonomous learning on frontier models (false: the [Save] offer and the model ask, as before)
    verifier.on         the independent verifier runs after an autonomous save
    verifier.models     the models it may use (Claude Code aliases or ids); null: one per frontier family the tiers
                        name, a different one from the model that did the work when there are two
    verifier.timeout_s  a verifier run is stopped after this long
    verifier.max_usd_per_run    the spending cap handed to each run (`claude -p --max-budget-usd`)
    replay.on           replaying a candidate on an apply model to promote it (off by default: it costs money)
    replay.model        the apply model it replays on
    budget.runs_per_day, budget.usd_per_day   the daily cap on every model run Athos starts (verifier and replay
                        together); a run that reports no cost counts budget.usd_estimate_per_run
    apply_candidates    an apply model may also get its project's candidates (off: verified and legacy only)
    age_days            a verified piece with no use and no re-verification in this many days returns to candidate
    reverify_days       a piece older than this is checked against the environment before a frontier model is
                        offered it
"""

from __future__ import annotations

import copy

from athos import session

DEFAULTS = {
    "on": True,
    "verifier": {"on": True, "models": None, "timeout_s": 300, "max_usd_per_run": 0.5},
    "replay": {"on": False, "model": "haiku"},
    "budget": {"runs_per_day": 6, "usd_per_day": 1.0, "usd_estimate_per_run": 0.25},
    "apply_candidates": False,
    "age_days": 90,
    "reverify_days": 14,
}

LEARN, APPLY, UNKNOWN = "learn", "apply", "unknown"


def _merge(base: dict, saved: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (saved or {}).items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def settings() -> dict:
    """The autonomous-learning settings: the saved ones over the defaults."""
    from athos import start
    saved = start.config().get("autolearn")
    return _merge(DEFAULTS, saved if isinstance(saved, dict) else {})


def mode_for(model: str | None) -> str:
    """How a model works for learning: `learn` (a frontier model), `apply` (any other model Athos could name), or
    `unknown` when the model was not resolved at all (no transcript, no hook field). An unknown model never learns
    autonomously; for the person's own [Save] it keeps the behaviour from before tiers existed."""
    from athos import tiers
    if not model or model == session.UNKNOWN_MODEL:
        return UNKNOWN
    return LEARN if tiers.tier_of(model) == tiers.FRONTIER else APPLY


def session_mode(sid: str | None) -> str:
    return mode_for(session.load(sid).get("model")) if sid else UNKNOWN


def autonomous(sid: str | None) -> bool:
    """Whether this session learns on its own: a frontier model, with autonomous learning on and capture not off."""
    from athos import capture
    return capture.enabled() and settings().get("on") is not False and session_mode(sid) == LEARN


def tells_edits(sid: str | None) -> bool:
    """Whether the model is told about the person's edits as a prompt to propose a rule. Not with autonomous learning
    (the edit is evidence of a correction instead) and never on an apply model (it may not change a piece)."""
    mode = session_mode(sid)
    if mode == APPLY:
        return False
    return not (mode == LEARN and settings().get("on") is not False)
