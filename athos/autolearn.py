"""Autonomous learning: on a frontier model Athos keeps what a task taught without asking anyone, and only on objective
evidence; apply models never create or change a piece, they only add evidence.

The settings live in `<home>/config.json` under `"autolearn"`; anything not saved there takes the default below.

    on                  autonomous learning on frontier models (false: the [Save] offer and the model ask, as before)
    ask                 how the model is told to keep what a task taught: `guide` (the default) says it once, out of
                        the person's sight, in the session guide, and the Stop hook only records; `stop` also has the
                        Stop hook say one short line when a task qualifies, which is more reliable (it arrives right
                        when the task ends) but the person reads it as "Stop hook feedback"
    verifier.on         the independent verifier runs after an autonomous save
    verifier.models     the models it may use (Claude Code aliases or ids); null: one per frontier family the tiers
                        name, a different one from the model that did the work when there are two
    verifier.timeout_s  a verifier run is stopped after this long
    verifier.max_usd_per_run    the spending cap handed to each run (`claude -p --max-budget-usd`); 0 turns runs off
    replay.on           replaying a candidate on an apply model to promote it (off by default: it costs money)
    replay.model        the apply model it replays on
    budget.runs_per_day, budget.usd_per_day   the daily cap on every model run Athos starts (verifier and replay
                        together), reserved before each run; a run that reports no cost counts the whole cap it
                        reserved; 0 turns runs off
    apply_candidates    an apply model may also get its project's candidates (off: verified and legacy only)
    age_days            a verified piece with no use and no re-verification in this many days returns to candidate
    reverify_days       a piece older than this is checked against the environment before a frontier model is
                        offered it
"""

from __future__ import annotations

import copy
import datetime as _dt
import re

from athos import session

DEFAULTS = {
    "on": True,
    "ask": "guide",
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


GUESSED = "guessed"
_REFUSAL = {APPLY: "apply_model", GUESSED: "model_guessed", UNKNOWN: "model_unknown"}


def save_mode(state: dict) -> str:
    """How a session's model may save: `mode_for` its model, except that a frontier model only guessed (from Claude
    Code's settings or its launch flag, session.configured_model) is `guessed` until the model has been observed. A
    guess may choose the delivery and the guide; a save needs the model seen."""
    mode = mode_for(state.get("model"))
    return GUESSED if mode == LEARN and not session.observed(state) else mode


def _refusal_text(state: dict, mode: str) -> str:
    model = state.get("model") or "unknown"
    if mode == GUESSED:
        return (f"this session's model ({model}) is only a guess so far (from {state.get('model_source')}); a model "
                f"saves only once Athos has seen which model answers, at its next tool call or the end of the turn")
    return (f"autonomous learning runs only on a frontier model, and this session's model ({model}) is "
            f"{'an apply model' if mode == APPLY else 'not known'}. Apply models never create or change a piece; "
            f"`athos tiers` lists which models learn.")


def session_mode(sid: str | None) -> str:
    return mode_for(session.load(sid).get("model")) if sid else UNKNOWN


def autonomous(sid: str | None) -> bool:
    """Whether this session learns on its own: a frontier model, with autonomous learning on and capture not off."""
    return autonomous_state(session.load(sid)) if sid else False


def autonomous_state(state: dict) -> bool:
    """`autonomous` for a session state already read."""
    from athos import capture
    return capture.enabled() and settings().get("on") is not False and mode_for(state.get("model")) == LEARN


ASKS = ("guide", "stop")


def ask_mode() -> str:
    """`guide` (the default) or `stop`: where the instruction to keep what a task taught reaches the model."""
    value = str(settings().get("ask") or "guide").strip().lower()
    return value if value in ASKS else "guide"


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
    """The Stop hook on a frontier model with autonomous learning, for a task with grounds (real work, or a checklist
    followed: capture._grounds_to_ask) that did not save. Without strong evidence (evidence.qualifies) it ends quietly
    (`skipped`). With it: under `ask: guide` (the default) nothing is said, since the session guide already told the
    model to save before finishing, and the task is recorded as `qualified`; under `ask: stop` the model gets one
    short line asking it to write what is reusable with `athos save --auto` (`asked`). Either way the next request
    records `model_saved_nothing` if no save came. Every decision is a `learn` event."""
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
    how = ask_mode()
    session.update(sid, tools_since_capture=0, work_since_capture=0, edits_since_capture=0, checklist=False,
                   checklist_typed=False, asked=state.get("asked", 0) + (how == "stop"),
                   auto_ask={"task_id": state.get("task_id"), "answered": False, "ask": how})
    note(sid, state, "asked" if how == "stop" else "qualified", reason, items, grounds=grounds, ask=how,
         guide=bool(state.get("guide") == "auto"))
    if how != "stop":
        return None
    lang = "es" if start.lang() == "es" else "en"
    text = ASK[lang].format(cmd=cmd)
    if state.get("guide") != "auto":     # no autonomous session guide in context: the format comes along
        text += "\n\n" + capture.AUTO_FORMAT.format(cmd=cmd)
    return {"decision": "block", "reason": text}


def on_next_request(sid: str | None) -> None:
    """The person's next request: a task asked to keep what it taught and that saved nothing is recorded as skipped
    (the model found nothing reusable)."""
    if not sid:
        return
    state = session.load(sid)
    asked = state.get("auto_ask") or {}
    if asked and not asked.get("answered") and asked.get("task_id") == state.get("task_id") \
            and asked.get("task_id") not in _settled_tasks():
        note(sid, state, "skipped", "model_saved_nothing", ask=asked.get("ask") or "stop")
    if asked:
        session.update(sid, auto_ask=None)


def _settled_tasks() -> set:
    """Tasks whose ask to keep what they taught was answered: a save, or a `skipped` decision after the ask."""
    from athos import eval as ev
    # A hook asks: the recent window (the session's own task is a recent one), never the archive.
    return {e.get("task_id") for e in ev.live_events() if e.get("type") == "learn"
            and (e.get("decision") == "saved" or e.get("reason") == "model_saved_nothing")}


SETTLE_AFTER_S = 600     # an ask still open this long after its task's last end is over: no hook will answer it


def catch_up(project: str | None) -> list[str]:
    """At a session start: the frontier tasks of this project that qualified to keep what they taught (`qualified`,
    `asked`) and ended without a save, in a session that never sent another request (one request, or killed), are
    recorded as `model_saved_nothing`, as the next request would have. Only once the task's last end is
    SETTLE_AFTER_S old, so a session still at work answers its own. Returns the task ids recorded."""
    from athos import eval as ev
    if not project:
        return []
    # A hook (the session start): the recent window, never the archive. A task's ask and its answer come after its
    # start, so an ask still in the live log has its answer there too.
    evs = ev.live_events()
    settled = {e.get("task_id") for e in evs if e.get("type") == "learn"
               and (e.get("decision") == "saved" or e.get("reason") == "model_saved_nothing")}
    ended = {}
    for e in evs:
        if e.get("type") == "task_end" and e.get("task_id"):
            ended[e["task_id"]] = e.get("at") or ""
    cutoff = ev._iso(ev.now() - _dt.timedelta(seconds=SETTLE_AFTER_S))
    out = []
    for e in evs:
        tid = e.get("task_id")
        if e.get("type") != "learn" or e.get("decision") not in ("qualified", "asked") or e.get("project") != project \
                or not tid or tid in settled or tid in out or not ended.get(tid) or ended[tid] > cutoff:
            continue
        sid = e.get("session_id")
        state = {"task_id": tid, "model": e.get("model"), "project": project}
        note(sid, state, "skipped", "model_saved_nothing", ask=e.get("ask") or "stop", caught_up=True)
        out.append(tid)
    return out


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
    mode = save_mode(state)
    project = paths.project_of(cwd) if cwd else None
    task_id = state.get("task_id")
    items = evidence.of_task(task_id)
    if task_id and (state.get("auto_ask") or {}).get("task_id") == task_id:
        session.update(sid, auto_ask={**state["auto_ask"], "answered": True})

    def refuse(reason: str, message: str, **more):
        note(sid, state, "skipped", reason, items, cwd, **more)
        return None, f"not saved: {message}", True

    if mode != LEARN:
        return refuse(_REFUSAL[mode], _refusal_text(state, mode))
    if settings().get("on") is False:
        return refuse("off", "autonomous learning is off (`autolearn.on` in config.json)")
    if not project:
        return refuse("no_project", "a learned piece belongs to the project it was learned in, and this folder has "
                                    "none")
    ok, reason = evidence.qualifies(items)
    if not ok:
        return refuse(reason, "this task has no objective evidence that the work was right (a verification that "
                              "passed, a commit); the model's own word is not enough")
    twin, owned = same_way_as(text, project, state)
    if twin is not None:
        from athos import grade
        rejected = grade.rejection(twin[1])
        if rejected and rejected["set_aside"]:
            return refuse("duplicate", f"this is the same way of working as `{twin[1].id}` (\"{twin[1].title}\"), "
                                       f"which the verifier rejected version after version; it waits for the person "
                                       f"to decide, so nothing is saved for it now.", overlaps=[twin[1].id],
                          score=twin[0])
        return refuse("duplicate", DUPLICATE.format(id=twin[1].id, title=twin[1].title), overlaps=[twin[1].id],
                      score=twin[0])
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
                "note": f"learned on its own ({state.get('model')}), a candidate"
                        + (f"; the same way of working as {', '.join(p.id for _s, p in owned)}, not changed"
                           if owned else "")}
    try:
        piece, _ = capture.save_text(text, sid, cwd, transcript_path, learning=learning)
    except ValueError as problem:
        return refuse("invalid", str(problem))
    checks = runnable_checks(piece)
    if owned:                                  # a piece the person owns is never changed: the overlap is shown instead
        from athos import grade
        grade.mark_review(piece.id, "same way of working as " + ", ".join(p.id for _s, p in owned)
                          + " (your own piece, not changed)", kind="overlap")
    note(sid, state, "saved", reason, items, cwd, piece=piece.id, version=piece.version, risk=piece.risk,
         checks=checks, confidence=float(INITIAL_CONFIDENCE),
         **({"overlaps": [p.id for _s, p in owned], "score": owned[0][0]} if owned else {}))
    from athos import replay
    try:                                       # with replays on: the task becomes the candidate's case
        replay.keep_candidate_case(piece, session.load(sid), transcript_path)
    except (OSError, ValueError):
        pass
    after = "" if checks else " It has no runnable Check, so it stays a candidate."
    return piece, (f"saved {piece.id} as a candidate of {project} ({piece.path}).{after}"), False


def refuse_model_save(sid: str | None, what: str = "save") -> str | None:
    """A save or change the model started, on a model that may not make one: an apply model, or one Athos could not
    resolve, or a frontier model only guessed so far. Refused with a `learn` event. None when it may go on (a frontier
    model, observed)."""
    if sid:
        # A model only guessed so far is looked for in the transcript now: the save's own tool call has a request row.
        from athos import eval as ev
        ev.refresh_model(sid, None, "save")
    state = session.load(sid) if sid else {}
    mode = save_mode(state)
    if mode == LEARN:
        return None
    note(sid, state, "skipped", _REFUSAL[mode], action=what)
    model = state.get("model") or "unknown"
    if mode == GUESSED:
        return (f"not saved: {_refusal_text(state, mode)}. The person can save it with their [Save] button or an "
                f"`Athos · save:` request.")
    kind = "an apply model" if mode == APPLY else "a model that is not known"
    return (f"not saved: this session runs on {model}, {kind}. Apply models and models Athos could not resolve never "
            f"create or change a piece (`athos tiers` lists which models learn); the person can save it with "
            f"their [Save] button or an `Athos · save:` request.")


DUPLICATE = ("this is the same way of working as `{id}` (\"{title}\"), a piece Athos learned in this project. Improve "
             "that piece instead of creating another: run `athos save --auto` again with the whole piece rewritten "
             "(its steps and what this task added: a step, a Check, a case it did not cover), with `id: {id}` and a "
             "`note:` saying what changed in its frontmatter. If this task taught nothing that piece lacks, save "
             "nothing.")


def same_way_as(text: str, project: str | None, state: dict):
    """Before a new candidate is created, the pieces it would repeat (wiki.same_way, a check that does not rely on
    the model's judgement): those of this project and those the task opened. Returns (the learned piece of this
    project it repeats, as (score, piece), to refuse the save and improve that one instead, or None; the pieces the
    person owns, or of another project, that it repeats: created anyway, never changed, and marked)."""
    from athos import capture, store, wiki
    try:
        _meta, title, when, _pid, body = capture._fields(text)
    except (ValueError, AttributeError):
        return None, []
    draft = store.Piece(id="draft", title=title or "", when=when or "", body=body or "", projects=[project or ""])
    opened = set(state.get("task_opened") or []) | set(state.get("task_loaded") or [])
    pool = [p for p in store.all_pieces() if (project and project in p.projects) or p.id in opened]
    found = wiki.same_way(draft, pool, opened)
    mine = [(sc, p) for sc, p in found if p.status and project in p.projects]
    return (mine[0] if mine else None), [(sc, p) for sc, p in found if not (p.status and project in p.projects)]


def save_model(text: str, sid: str, cwd: str | None, transcript_path: str | None = None):
    """A save the model started, with or without `--auto`: a new piece goes through `save_auto`; an existing one
    through `improve_auto`. (piece or None, the line to print, refused)."""
    from athos import capture, store
    _meta, _title, _when, piece_id, _body = capture._fields(text)
    existing = store.get(piece_id) if piece_id else None
    if existing is not None:
        return improve_auto(text, sid, cwd, transcript_path, existing)
    return save_auto(text, sid, cwd, transcript_path)


def improve_auto(text: str, sid: str, cwd: str | None, transcript_path: str | None, existing):
    """The model improves a piece it may improve: a learned one (candidate or verified) of this project, on this
    task's strong evidence, after the private-data check. The new version is a candidate (a verified piece returns to
    candidate), with the same id and its history, so it gets its own bundle and verifier run; the person's own pieces
    (no status) and retired ones are never changed by a model, nor a candidate the verifier rejected
    grade.MAX_FAILED_VERSIONS times in a row (set aside for the person). This is the one path for improving a
    candidate: `athos save --auto` (or a model's plain `athos save`) with the piece's `id:`."""
    from athos import capture, evidence, paths, store
    state = session.load(sid)
    mode = save_mode(state)
    project = paths.project_of(cwd) if cwd else None
    items = evidence.of_task(state.get("task_id"))

    def refuse(reason: str, message: str, **more):
        note(sid, state, "skipped", reason, items, cwd, piece=existing.id, **more)
        return None, f"not saved: {message}", True

    if mode != LEARN:
        return refuse(_REFUSAL[mode], _refusal_text(state, mode) if mode == GUESSED
                      else "only a frontier model improves a piece")
    if settings().get("on") is False:
        return refuse("off", "autonomous learning is off (`autolearn.on` in config.json)")
    if store.legacy(existing):
        return refuse("persons_piece", "this piece is the person's own: a model changes it only when they ask for "
                                       "it (their [Adjust], [Save] or an `Athos · save:` request)")
    if existing.status == "retired":
        return refuse("retired", "this piece was retired; `athos revert` brings it back first")
    if not project or project not in existing.projects:
        return refuse("other_project", "a learned piece is improved only from its own project")
    from athos import grade
    rejected = grade.rejection(existing)
    if rejected and rejected["set_aside"]:
        return refuse("set_aside", f"the verifier rejected {rejected['attempts']} versions of this piece in a row, so "
                                   f"it was set aside for the person to decide; a model no longer rewrites it")
    ok, reason = evidence.qualifies(items)
    if not ok:
        return refuse(reason, "this task has no objective evidence that the work was right (a verification that "
                              "passed, a commit); the model's own word is not enough")
    found = private_findings(text, project)
    if found:
        return refuse("private_data", "it looks like it carries private data (" + ", ".join(found) + "). Rewrite "
                      "it without them and save again, or stop.", private=found)
    try:
        piece, _diff = capture.save_text(text, sid, cwd, transcript_path)
    except ValueError as problem:
        return refuse("invalid", str(problem))
    if piece.status == "verified":
        piece = store.set_status(piece.id, "candidate", "improved on its own: to be verified again") or piece
    store.set_meta(piece.id, evidence=evidence.summary(items, state.get("task_id")))
    piece = store.get(piece.id)
    note(sid, state, "saved", reason, items, cwd, piece=piece.id, version=piece.version, risk=piece.risk,
         checks=runnable_checks(piece), improved=True)
    return piece, f"improved {piece.id} → v{piece.version}, a candidate of {project} again ({piece.path}).", False
