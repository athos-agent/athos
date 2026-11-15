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
import re

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


# ------------------------------------------------------------------------------------------------ risk lanes
# What makes a step risky: it publishes, merges, deploys, deletes, force-pushes or touches production. Conservative on
# purpose: in doubt a step is high risk, which only asks for stricter promotion and, on an apply model, for the
# person's yes before the step runs.
RISKY = [
    ("force_push", re.compile(r"\bpush\b[^\n`]*(?:--force\b|-f\b|--force-with-lease\b)|\bforce[- ]push", re.I)),
    ("publish", re.compile(r"\b(?:npm|pnpm|yarn|cargo|gem|twine|poetry|flit|dotnet\s+nuget)\s+(?:publish|push|upload)\b"
                           r"|\bdocker\s+push\b|\bgh\s+release\s+create\b|\bgit\s+push\b|\bgit\s+tag\s+-[as]\b"
                           r"|\bpublish(?:es|ed|ing)?\b|\bpublic(?:a|ar|ás|á|amos|ado)\b|\breleases?\s+(?:to|on)\b",
                           re.I)),
    ("merge", re.compile(r"\bgh\s+pr\s+merge\b|\bgit\s+merge\b|\bmerg(?:e|es|ed|ing)\b|\bmergea\w*\b", re.I)),
    ("deploy", re.compile(r"\bdeploy\w*|\bdesplieg\w*|\bdespleg\w*|\bkubectl\s+(?:apply|delete|rollout|scale)\b"
                          r"|\bterraform\s+(?:apply|destroy)\b|\bhelm\s+(?:install|upgrade|uninstall|rollback)\b"
                          r"|\b(?:vercel|netlify|fly|flyctl)\b[^\n]*\b(?:--prod|deploy)\b|\bheroku\b", re.I)),
    ("delete", re.compile(r"\brm\s+-\w*[rf]|\bdelet(?:e|es|ed|ing)\b|\bborr(?:a|ar|á|ás)\b|\belimin(?:a|ar|á)\b"
                          r"|\bdrop\s+(?:table|database|schema)\b|\btruncate\s+table\b|\bgit\s+branch\s+-D\b"
                          r"|\bpush\b[^\n`]*--delete\b|\bgit\s+clean\s+-\w*f", re.I)),
    ("production", re.compile(r"\bprod(?:uction)?\b|\bproducci[oó]n\b|--prod\b", re.I)),
]


def risks_in(text: str) -> list[str]:
    """The kinds of risk a text names (publish, merge, deploy, delete, force_push, production), in a fixed order."""
    return [kind for kind, rx in RISKY if rx.search(text or "")]


def risky_steps(piece) -> dict[str, list[str]]:
    """Per statement id, the kinds of risk its When and Do name (a page without statements is one step, `steps`)."""
    from athos import wiki
    out = {}
    for st in wiki.statements(piece):
        found = risks_in(f"{st.when}\n{st.do}")
        if found:
            out[st.id] = found
    return out


def risk_of(piece) -> str:
    """`high` when any step publishes, merges, deploys, deletes, force-pushes or touches production; else `normal`. A
    piece's own `risk: high` is kept even when the detector finds nothing; `risk: normal` is not trusted over it."""
    if getattr(piece, "risk", "") == "high":
        return "high"
    return "high" if risky_steps(piece) else "normal"


# ------------------------------------------------------------------------------------------------ learn events
def _project(state: dict, cwd: str | None = None) -> str | None:
    from athos import paths
    return state.get("project") or (paths.project_of(cwd) if cwd else None)


def note(sid: str | None, state: dict, decision: str, reason: str, items: list[dict] | None = None,
         cwd: str | None = None, **more) -> None:
    """The `learn` audit event: what autonomous learning decided for a task (asked, saved, skipped), why, and the
    evidence it decided on (counts by strength and polarity, and the short summary a piece keeps)."""
    from athos import eval as ev, evidence, load, store, tiers
    items = items if items is not None else evidence.of_task(state.get("task_id"))
    project = _project(state, cwd)
    piece_id = more.get("piece")
    named = ""
    if piece_id:
        p = store.get(piece_id)
        named = " " + (load.loggable([p], project, bool(state.get("public"))) if p else piece_id)
    model = state.get("model")
    ev.audit({"type": "learn", "session_id": sid, "task_id": state.get("task_id"), "decision": decision,
              "reason": reason, "model": model, **tiers.describe(model), "mode": mode_for(model),
              "project": project, **evidence.counts(items), "evidence": evidence.summary(items), **more},
             line=f"{decision}{named} · {reason} · {evidence.counts(items)['strong']} strong item(s)", project=project)


def note_skipped(sid: str, state: dict, reason: str, grounds: str = "") -> None:
    note(sid, state, "skipped", reason, grounds=grounds)


# ------------------------------------------------------------------------------------------------ the Stop hook
# The one line the person sees (Claude Code shows it as "Stop hook feedback"), in their language.
ASK = {"en": "Athos: if this task taught something reusable, keep it as one piece with Check lines (`{cmd} save "
             "--auto`, as the session guide says); otherwise just stop.",
       "es": "Athos: si esta tarea enseñó algo reutilizable, guardalo como una pieza con líneas Check (`{cmd} save "
             "--auto`, como dice la guía de la sesión); si no, terminá."}


def stop_decision(sid: str, state: dict, grounds: str, cmd: str = "athos") -> dict | None:
    """The Stop hook on a frontier model with autonomous learning: a task with grounds (real work, or a checklist
    followed: capture._grounds_to_ask) and strong evidence (evidence.qualifies) gets one short line asking the model to
    write what is reusable with `athos save --auto`; anything else ends quietly. Every decision is a `learn` event."""
    from athos import capture, evidence, start
    if not grounds:
        return None
    items = evidence.of_task(state.get("task_id"))
    ok, reason = evidence.qualifies(items)
    if not ok:
        note(sid, state, "skipped", reason, items, grounds=grounds)
        session.update(sid, tools_since_capture=0, work_since_capture=0, edits_since_capture=0, checklist=False,
                       checklist_typed=False)
        return None
    session.update(sid, tools_since_capture=0, work_since_capture=0, edits_since_capture=0, checklist=False,
                   checklist_typed=False, asked=state.get("asked", 0) + 1,
                   auto_ask={"task_id": state.get("task_id"), "answered": False})
    note(sid, state, "asked", reason, items, grounds=grounds)
    lang = "es" if start.lang() == "es" else "en"
    text = ASK[lang].format(cmd=cmd)
    if not state.get("guide"):           # no session guide in context: the format comes along
        text += "\n\n" + capture.AUTO_FORMAT.format(cmd=cmd)
    return {"decision": "block", "reason": text}


def on_next_request(sid: str | None) -> None:
    """The person's next request: a task asked to keep what it taught and that saved nothing is recorded as skipped
    (the model found nothing reusable)."""
    if not sid:
        return
    state = session.load(sid)
    asked = state.get("auto_ask") or {}
    if asked and not asked.get("answered") and asked.get("task_id") == state.get("task_id"):
        note(sid, state, "skipped", "model_saved_nothing")
    if asked:
        session.update(sid, auto_ask=None)


# ------------------------------------------------------------------------------------------------ the save
def _other_projects(project: str | None) -> list[str]:
    from athos import store
    return sorted({q for p in store.all_pieces() for q in p.projects if q != project})


def private_findings(text: str, project: str | None) -> list[str]:
    """The kinds of private-looking data in a piece (share.findings): emails, phone and ID numbers, links, folders of
    this computer, another project's name, the person's name. The piece's own project may be named."""
    from athos import share, trail
    try:
        name = trail.person_name()
    except Exception:  # noqa: BLE001
        name = ""
    return sorted({kind for kind, _ in share.findings(text, _other_projects(project), name)})


def runnable_checks(piece) -> int:
    from athos import evidence
    return len(evidence.checks_of(piece))


INITIAL_CONFIDENCE = "0.3"


def save_auto(text: str, sid: str, cwd: str | None, transcript_path: str | None = None):
    """`athos save --auto`: keep what a frontier task taught as a new candidate piece of this project, on the task's
    strong evidence, after the private-data check. Returns (piece or None, the line to print, refused). Every outcome
    is a `learn` event."""
    from athos import capture, evidence, paths, store
    state = session.load(sid)
    mode = mode_for(state.get("model"))
    project = paths.project_of(cwd) if cwd else None
    task_id = state.get("task_id")
    items = evidence.of_task(task_id)
    if (state.get("auto_ask") or {}).get("task_id") == task_id:
        session.update(sid, auto_ask={**state["auto_ask"], "answered": True})

    def refuse(reason: str, message: str, **more):
        note(sid, state, "skipped", reason, items, cwd, **more)
        return None, f"not saved: {message}", True

    if mode != LEARN:
        model = state.get("model") or "unknown"
        return refuse("apply_model" if mode == APPLY else "model_unknown",
                      f"autonomous learning runs only on a frontier model, and this session's model ({model}) is "
                      f"{'an apply model' if mode == APPLY else 'not known'}. Apply models never create or change a "
                      f"piece; `athos tiers` lists which models learn.")
    if settings().get("on") is False:
        return refuse("off", "autonomous learning is off (`autolearn.on` in config.json)")
    if not project:
        return refuse("no_project", "a learned piece belongs to the project it was learned in, and this folder has "
                                    "none")
    ok, reason = evidence.qualifies(items)
    if not ok:
        return refuse(reason, "this task has no objective evidence that the work was right (a verification that "
                              "passed, a commit); the model's own word is not enough")
    found = private_findings(text, project)
    if found:
        return refuse("private_data", "it looks like it carries private data (" + ", ".join(found) + "). Rewrite "
                      "it without them (paths relative to the repository, no links or emails, no other project's "
                      "name) and save again, or stop.", private=found)
    meta, _body = store.parse_frontmatter(text.strip())
    if meta.get("evidence"):
        evidence.add(task_id, {"type": "model_claim", "strength": "weak", "polarity": "neutral"})
        items = evidence.of_task(task_id)
    draft = store.Piece(id="draft", title="", when="", body=_body)
    learning = {"status": "candidate", "learned_by": state.get("model") or "", "confidence": INITIAL_CONFIDENCE,
                "evidence": evidence.summary(items, task_id), "risk": risk_of(draft), "visibility": "project",
                "note": f"learned on its own ({state.get('model')}), a candidate"}
    try:
        piece, _ = capture.save_text(text, sid, cwd, transcript_path, learning=learning)
    except ValueError as problem:
        return refuse("invalid", str(problem))
    checks = runnable_checks(piece)
    note(sid, state, "saved", reason, items, cwd, piece=piece.id, version=piece.version, risk=piece.risk,
         checks=checks, confidence=float(INITIAL_CONFIDENCE))
    after = "" if checks else " It has no runnable Check, so it stays a candidate."
    return piece, (f"saved {piece.id} as a candidate of {project} ({piece.path}).{after}"), False


def refuse_apply_save(sid: str | None) -> str | None:
    """The plain `athos save` on an apply model: refused, with a `learn` event. None when the save may go on."""
    if not sid or session_mode(sid) != APPLY:
        return None
    state = session.load(sid)
    note(sid, state, "skipped", "apply_model")
    return (f"not saved: this session runs on {state.get('model')}, an apply model. Apply models never create or "
            f"change a piece; Athos learns only on frontier models (`athos tiers` lists them).")
