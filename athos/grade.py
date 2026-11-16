"""Grading: where each learned piece stands (candidate, verified, retired), on what basis, and how it moves.

    candidate → verified    the independent verifier passed on the piece as it is now (athos/verify.py), it has at
                            least one runnable Check, and since it became a candidate either two clean reuses on a
                            frontier model or one pass on an apply model (a replay, or a real use whose Checks the
                            hooks saw pass). A `risk: high` piece needs the verifier and at least one clean reuse:
                            a replay alone is not enough for it.
                            A reuse made while the verifier's verdict on that text was a fail never counts.
    candidate (set aside)   the verifier rejected MAX_FAILED_VERSIONS texts in a row: the model is no longer asked to
                            rewrite it, the automatic save refuses to, and a review mark puts it before the person.
    verified → candidate    a reuse that was corrected or failed: strong evidence tied to that piece. A legacy
                            piece (no status) never moves; grading records an event and a review mark instead.
    → retired               RETIRE_NEGATIVES corrected or failed reuses among its last RETIRE_WINDOW, counted from
                            its last status change, revert or improvement (each a new version). Retiring
                            supersedes; `athos revert` restores, with no outcome against it.
    verified → candidate    ageing: no use and no re-verification in `age_days` (90). Using a piece moves its
                            last-used date, so use slows ageing. Legacy pieces do not age.

A reuse is judged when the task ends (the Stop hook), when its objective evidence is final (`finish_task`); the person's
next request may amend it with their reaction (words: confidence only) or their edits (strong, tied evidence); a task
that ended without being graded is caught up at the next session start in its project (`catch_up`). One piece of work
counts once (the latest judgement of a task), never in the session that wrote or improved the piece:

    frontier   clean: the task's evidence has a strong positive item and nothing against the work; corrected: strong
               evidence tied to the piece (a change of the person's credited to it, one of its Checks failing last);
               unverified, not counted: nothing proved the work, or something was against the work without naming
               this piece (a revert, a change credited to another piece or to none, a failed verification), or the
               person's words read as a correction (that lowers confidence, nothing more)
    apply      clean: at least one of its Checks seen passing and none failing last, and nothing against; failed: tied
               strong evidence as above; unverified: none of its Checks ran, or untied evidence, or words

Every move, and every decision not to move, is a `grade` event with its basis. Nothing is deleted: a status change is a
new version of the piece (store.set_status). Confidence (0 to 1) follows the evidence and feeds the router a little.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re

from athos import eval as ev, evidence, paths, session, store

VERIFIER_PASS = 0.2
VERIFIER_FAIL = -0.1
CLEAN_REUSE = 0.1
NEGATIVE_REUSE = -0.2
WEAK_NEGATIVE = -0.1     # a reaction read from the person's words that the task went wrong
STALE_REFS = -0.1
VERIFIED_FLOOR = 0.7       # a verified piece starts at least this confident
FRONTIER_REUSES = 2        # clean frontier reuses that, with the verifier, verify a normal piece
HIGH_RISK_REUSES = 1       # ...and a high-risk one (the verifier is required for both)
RETIRE_NEGATIVES = 3       # corrected or failed reuses...
RETIRE_WINDOW = 5          # ...among this many latest ones retire a piece
STRONG_NEGATIVE = {"person_edit", "revert", "check_failed"}
MAX_FAILED_VERSIONS = 3    # versions of a learned candidate the verifier may reject in a row before it is set aside


def body_sha(p: store.Piece) -> str:
    """What the verifier's verdict is about: the piece's title, when and body (a status change does not alter it),
    without the blank lines around them, which writing a piece to its file and reading it back may change."""
    return hashlib.sha256(f"{p.title.strip()}\n{p.when.strip()}\n{p.body.strip()}".encode()).hexdigest()[:16]


def note(piece_id: str, was: str, now: str, basis: str, **more) -> None:
    """The `grade` audit event: a piece's status before and after (the same when it did not move) and why."""
    from athos import load
    p = store.get(piece_id)
    project = p.projects[0] if p and p.projects else None
    named = load.loggable([p], project) if p else piece_id
    ev.audit({"type": "grade", "piece": piece_id, "version": p.version if p else None, "from": was, "to": now,
              "basis": basis, "project": project, **more},
             line=f"{named}: {was} → {now} · {basis}" if was != now else f"{named}: stays {now} · {basis}",
             project=project)


def _confidence(p: store.Piece, delta: float, floor: float | None = None) -> str | None:
    """The new confidence, or None for a legacy piece (never scored, so its file stays as it is)."""
    if not p.status:
        return None
    base = store.confidence(p)
    value = max(0.05, min(1.0, (0.5 if base is None else base) + delta))
    if floor is not None:
        value = max(value, floor)
    return f"{value:.2f}"


def _set_confidence(p: store.Piece, delta: float, floor: float | None = None) -> None:
    value = _confidence(p, delta, floor)
    if value is not None:
        store.set_meta(p.id, confidence=value)


def _add_evidence(p: store.Piece, token: str) -> list[str]:
    head = token.split(":", 1)[0] + ":"
    return [e for e in p.evidence if not (e == token or e.startswith(head) and head in ("verifier:",))][-7:] + [token]


# ------------------------------------------------------------------------------------------------ the verifier
def on_verdict(piece_id: str, out: dict) -> None:
    """The verifier's outcome for a candidate: a verdict moves its confidence and its evidence and may promote it
    (`evaluate`); an error, a refusal or a timeout leaves it a candidate and says why. A `learn` event records it."""
    p = store.get(piece_id)
    if p is None:
        return
    outcome = out.get("outcome")
    was = store.status(p)
    if outcome in ("pass", "fail"):
        token = f"verifier:{outcome}" + (":same-model" if out.get("same_model_fallback") else "")
        store.set_meta(piece_id, evidence=_add_evidence(p, token),
                       **({"last_verified": store.today()} if outcome == "pass" else {}))
        _set_confidence(store.get(piece_id), VERIFIER_PASS if outcome == "pass" else VERIFIER_FAIL)
        failed = sorted(c for c, ok in (out.get("verdict") or {}).items() if not ok)
        basis = "verifier_passed" if outcome == "pass" else "verifier_failed: " + ", ".join(failed)
    else:
        basis = f"verifier_{outcome}: {out.get('error')}"
    if outcome == "fail":
        _maybe_set_aside(piece_id)
    elif outcome == "pass" and (reviews().get(piece_id) or {}).get("kind") == "set_aside":
        clear_review(piece_id)                 # a text passed: the run of failures is over
    moved = evaluate(piece_id, trigger=basis)
    if not moved:
        note(piece_id, was, store.status(store.get(piece_id)), basis + (_waiting(piece_id) if outcome == "pass" else ""),
             verifier=outcome, verifier_model=out.get("model"), same_model_fallback=out.get("same_model_fallback"))
    _learn(p, outcome, basis, out)


def _waiting(piece_id: str) -> str:
    p = store.get(piece_id)
    if p is None or p.status != "candidate":
        return ""
    need = "1 clean reuse" if risk(p) == "high" else f"{FRONTIER_REUSES} clean frontier reuses or a pass on an apply model"
    if not evidence.checks_of(p):
        return "; no runnable Check, so it cannot be verified"
    return f"; waiting for {need}"


def _learn(p: store.Piece, outcome: str, basis: str, out: dict) -> None:
    project = p.projects[0] if p.projects else None
    ev.audit({"type": "learn", "task_id": out.get("task_id"), "decision": "graded", "reason": basis,
              "piece": p.id, "version": p.version, "verifier": outcome, "verifier_model": out.get("model"),
              "worker_model": out.get("worker_model"), "same_model_fallback": out.get("same_model_fallback"),
              "project": project, **evidence.counts(evidence.of_task(out.get("task_id")))})


# ------------------------------------------------------------------------------------------------ reading the log
def risk(p: store.Piece) -> str:
    from athos import autolearn
    return autolearn.risk_of(p)


def _events(piece_id: str) -> list[dict]:
    return [e for e in ev.events() if e.get("piece") == piece_id and e.get("type") in ("verify", "reuse", "grade",
                                                                                         "learn")]


def _since(evs: list[dict]) -> str:
    """When the piece last became a candidate: its autonomous save, or its latest move to candidate."""
    marks = [e.get("at") or "" for e in evs if (e.get("type") == "grade" and e.get("to") == "candidate"
                                                and e.get("from") != "candidate")
             or (e.get("type") == "learn" and e.get("decision") == "saved")]
    return max(marks, default="")


def verifier_passed(p: store.Piece, evs: list[dict] | None = None) -> dict | None:
    """The verifier's latest verdict on the piece as it is now (same title, when and body: a verdict is about the text
    it read, never about a version number) when that verdict is a pass from a bundle that held paths only and no
    narrative, or None. A later verdict on the same text replaces an earlier one: a re-verification that fails takes
    back an earlier pass, and one that passes replaces an earlier failure."""
    evs = _events(p.id) if evs is None else evs
    mine = body_sha(p)
    verdicts = [e for e in evs if e.get("type") == "verify" and e.get("outcome") in ("pass", "fail")
                and e.get("body_sha") == mine]
    last = verdicts[-1] if verdicts else None
    if last and last.get("outcome") == "pass" and last.get("paths_only") is not False \
            and last.get("bundle_clean") is not False:
        return last
    return None


def latest_verdict(p: store.Piece, evs: list[dict] | None = None) -> dict | None:
    """The verifier's latest verdict (pass or fail) on the piece's text as it is now, or None."""
    evs = _events(p.id) if evs is None else evs
    mine = body_sha(p)
    verdicts = [e for e in evs if e.get("type") == "verify" and e.get("outcome") in ("pass", "fail")
                and e.get("body_sha") == mine]
    return verdicts[-1] if verdicts else None


def failed_versions(p: store.Piece, evs: list[dict] | None = None) -> int:
    """How many texts of the piece the verifier rejected since it last passed one: each text counted once, by its
    latest verdict."""
    evs = _events(p.id) if evs is None else evs
    verdicts = [e for e in evs if e.get("type") == "verify" and e.get("outcome") in ("pass", "fail")]
    passes = [n for n, e in enumerate(verdicts) if e.get("outcome") == "pass"]
    after = verdicts[passes[-1] + 1:] if passes else verdicts
    last: dict[str, str] = {}
    for e in after:
        last[e.get("body_sha") or f"v{e.get('version')}"] = e.get("outcome")
    return sum(1 for o in last.values() if o == "fail")


def rejection(p: store.Piece | None, evs: list[dict] | None = None) -> dict | None:
    """A candidate Athos itself learned (it has a status and a learning model) whose latest verdict on its current text
    is a fail: {"why": the verifier's reason per criterion, "failed": the criteria that failed, "version", "attempts":
    texts rejected in a row (`failed_versions`), "set_aside": attempts reached MAX_FAILED_VERSIONS}. None otherwise
    (a pass, no verdict yet, a verdict about an older text, a piece the person owns, a verified or retired one)."""
    if p is None or p.status != "candidate" or not p.learned_by:
        return None
    evs = _events(p.id) if evs is None else evs
    last = latest_verdict(p, evs)
    if not last or last.get("outcome") != "fail":
        return None
    verdict = last.get("verdict") or {}
    failed = [c for c, ok in verdict.items() if not ok] or sorted(last.get("why") or {})
    attempts = failed_versions(p, evs)
    return {"why": {c: str((last.get("why") or {}).get(c) or "") for c in failed}, "failed": failed,
            "version": last.get("version"), "attempts": attempts, "set_aside": attempts >= MAX_FAILED_VERSIONS}


FEEDBACK = """Athos (for you, not the person): this piece, `{id}`, was not accepted. An independent verifier rejected its \
current text (attempt {attempts} of {limit}), for these reasons:
{reasons}
If this task shows how to fix that, save an improved version of this same piece before your final answer: run \
`{cmd} save --auto` with the whole piece rewritten (title, when, every step with its **Check:**), adding `id: {id}` \
and a `note:` that says what changed to its frontmatter. It stays a candidate and is checked again; nothing you \
write about your work reaches the verifier. If this task does not show how, leave the piece as it is. Don't mention \
this to the person."""


def feedback_text(p: store.Piece | None, cmd: str = "athos") -> str:
    """What a frontier model is told, out of the person's sight, about a candidate the verifier rejected (`rejection`):
    the failing criteria with the verifier's reasons, and the one way to improve it. "" when there is nothing to say,
    or the piece was set aside for the person (the loop stops asking)."""
    found = rejection(p)
    if not found or found["set_aside"]:
        return ""
    reasons = "\n".join(f"- {c}: {' '.join(found['why'].get(c, '').split()) or 'no reason given'}"
                        for c in found["failed"])
    return FEEDBACK.format(id=p.id, attempts=found["attempts"], limit=MAX_FAILED_VERSIONS, reasons=reasons, cmd=cmd)


def _maybe_set_aside(piece_id: str) -> None:
    """A learned candidate rejected for the MAX_FAILED_VERSIONS-th text in a row: the model is no longer asked to
    rewrite it, the automatic save refuses to, and a review mark puts it before the person (`athos report`, `athos
    audit`), with a `grade` event saying why. Once per run of failures."""
    p = store.get(piece_id)
    found = rejection(p)
    if not found or not found["set_aside"]:
        return
    if (reviews().get(piece_id) or {}).get("kind") == "set_aside":
        return
    why = (f"set aside: the verifier rejected {found['attempts']} versions in a row (last: "
           f"{', '.join(found['failed'])}); the model no longer rewrites it")
    mark_review(piece_id, why, kind="set_aside")
    note(piece_id, "candidate", "candidate", why.replace("set aside:", "set_aside:", 1), attempts=found["attempts"],
         failed=found["failed"])


def _reuses(evs: list[dict], since: str = "", version: int | None = None) -> list[dict]:
    """The reuse events at or after `since`, and of `version` only when one is given: a status change, a revert and an
    improvement each make a new version, so outcomes counted by version start again from the piece's last change."""
    return [e for e in counted_reuses(evs) if (e.get("at") or "") >= since
            and (version is None or e.get("version") == version)]


def standing(p: store.Piece) -> dict:
    """What the rules see for a piece: the verifier's pass, runnable Checks, clean and negative reuses since it
    became a candidate and since its last change (a revert brings back a piece with no outcomes against it), and
    its risk."""
    evs = _events(p.id)
    since = _since(evs)
    # A reuse made while the verifier's verdict on that text stood as a fail never counts towards promotion, even if
    # the same text passes later.
    recent = [e for e in _reuses(evs, since, p.version) if e.get("verdict") != "fail"]
    current = _reuses(evs, version=p.version)
    return {"verifier": verifier_passed(p, evs), "checks": len(evidence.checks_of(p)), "risk": risk(p),
            "frontier_clean": sum(1 for e in recent if e.get("outcome") == "clean" and e.get("tier") == "frontier"),
            "apply_pass": sum(1 for e in recent if e.get("tier") == "apply" and e.get("outcome") in ("clean",
                                                                                                    "replay_pass")),
            "apply_clean": sum(1 for e in recent if e.get("tier") == "apply" and e.get("outcome") == "clean"),
            "outcomes": [e.get("outcome") for e in current if e.get("outcome") != "unverified"],
            "strong_negatives": sum(1 for e in current if e.get("outcome") in ("corrected", "failed", "replay_fail")
                                    and set(e.get("basis") or []) & STRONG_NEGATIVE)}


# ------------------------------------------------------------------------------------------------ the rules
def evaluate(piece_id: str, trigger: str = "") -> bool:
    """Apply the promotion and retirement rules to one piece; True when it moved (and a `grade` event says why)."""
    p = store.get(piece_id)
    if p is None or store.status(p) == "retired":
        return False
    s = standing(p)
    status = store.status(p)
    if _retire_due(p, s):
        negatives = sum(1 for o in s["outcomes"][-RETIRE_WINDOW:] if o in ("corrected", "failed", "replay_fail"))
        return _move(p, "retired", f"{negatives} corrected or failed of its last {min(len(s['outcomes']), RETIRE_WINDOW)} "
                                   f"reuses", trigger, s)
    if status != "candidate":
        return False
    if not s["verifier"]:
        return False
    if not s["checks"]:
        return False
    clean = s["frontier_clean"] + s["apply_clean"]
    if s["risk"] == "high":
        if clean >= HIGH_RISK_REUSES:
            return _move(p, "verified", f"verifier passed, {clean} clean reuse(s) (high risk)", trigger, s)
        return False
    if s["frontier_clean"] >= FRONTIER_REUSES:
        return _move(p, "verified", f"verifier passed, {s['frontier_clean']} clean frontier reuses", trigger, s)
    if s["apply_pass"] >= 1:
        return _move(p, "verified", "verifier passed, a pass on an apply model", trigger, s)
    return False


def _retire_due(p: store.Piece, s: dict) -> bool:
    last = s["outcomes"][-RETIRE_WINDOW:]
    negatives = sum(1 for o in last if o in ("corrected", "failed", "replay_fail"))
    if negatives < RETIRE_NEGATIVES:
        return False
    return bool(p.status) or s["strong_negatives"] >= RETIRE_NEGATIVES      # legacy: strong evidence only


def _legacy_noted(p: store.Piece, would: str, basis: str) -> bool:
    """Grading would move a legacy piece: its file stays as it is; a `grade` event and a review mark say what was
    seen, for the person to decide. Always False (nothing moved)."""
    note(p.id, store.LEGACY, store.LEGACY, f"not moved to {would}: {basis} (a legacy piece is never rewritten by "
                                           f"grading; marked for review)")
    mark_review(p.id, f"would have moved to {would}: {basis}")
    return False


def _move(p: store.Piece, new: str, basis: str, trigger: str, s: dict) -> bool:
    was = store.status(p)
    if store.legacy(p):
        return _legacy_noted(p, new, basis)
    moved = store.set_status(p.id, new, basis)
    if new == "verified":
        store.set_meta(p.id, last_verified=store.today(), confidence=_confidence(moved, 0.0, VERIFIED_FLOOR) or None)
        clear_review(p.id)
    elif new == "retired":
        store.set_meta(p.id, confidence="0.05")
    verdict = s.get("verifier") or {}
    note(p.id, was, new, basis, trigger=trigger, verifier_model=verdict.get("model"),
         verifier_pass=bool(verdict), frontier_clean=s.get("frontier_clean"), apply_pass=s.get("apply_pass"),
         risk=s.get("risk"), checks=s.get("checks"))
    return True


def demote(piece_id: str, basis: str, strong: bool) -> bool:
    """A verified (or legacy) piece back to candidate after a corrected or failed reuse; a legacy piece only on strong
    evidence. True when it moved."""
    p = store.get(piece_id)
    if p is None or store.status(p) not in ("verified", store.LEGACY):
        return False
    if store.status(p) == store.LEGACY:
        if not strong:
            note(piece_id, store.LEGACY, store.LEGACY, f"not demoted: {basis} (a legacy piece moves only on strong "
                                                       f"evidence)")
            return False
        return _legacy_noted(p, "candidate", basis)
    was = store.status(p)
    store.set_status(piece_id, "candidate", basis)
    note(piece_id, was, "candidate", basis)
    return True


# ------------------------------------------------------------------------------------------------ a finished reuse
def _outcome(pid: str, tier: str, items: list[dict]) -> tuple[str, list[str]]:
    """How a task went for one piece it used, and on what basis (see the module's notes). Only strong evidence tied to
    this piece (a change of the person's credited to it, one of its own Checks failing last) makes a reuse corrected
    or failed. Strong evidence against the work that names no piece (a revert, a change credited to another piece or
    to none, a failed verification that is not one of its Checks) makes it unverified: the work was not clean, but
    nothing says this piece was wrong. A reaction read from the person's words is weak: it keeps a reuse from
    counting as clean and lowers confidence, never more."""
    tied: list[str] = []
    untied: list[str] = []
    weak: list[str] = []
    mine = [i for i in items if i.get("type") == "verify" and (i.get("check_of") or "").startswith(pid + "#")]
    strong_mine = [i for i in mine if i.get("strength") == "strong"]
    if strong_mine and strong_mine[-1].get("ok") is False:
        tied.append("check_failed")
    for i in items:
        if i.get("type") == "person_edit":
            (tied if i.get("piece") == pid else untied).append("person_edit" if i.get("piece") == pid
                                                               else "person_edit_not_this_piece")
        elif i.get("type") == "revert":
            untied.append("revert")
        elif i.get("type") == "reaction" and i.get("result") == "corrected":
            weak.append("reaction_corrected")
    verifies = [i for i in items if i.get("type") == "verify" and i.get("strength") == "strong"]
    if verifies and verifies[-1].get("ok") is False and "check_failed" not in tied:
        untied.append("last_verification_failed")
    tied, untied, weak = (list(dict.fromkeys(x)) for x in (tied, untied, weak))
    if tied:
        return ("failed" if tier == "apply" else "corrected"), tied
    if untied:
        return "unverified", untied + weak
    if tier == "apply":
        if strong_mine and strong_mine[-1].get("ok"):
            return ("unverified", ["check_passed"] + weak) if weak else ("clean", ["check_passed"])
        return "unverified", ["no_check_ran"] + weak
    if any(i.get("strength") == "strong" and i.get("polarity") == "positive" for i in items):
        return ("unverified", ["strong_positive"] + weak) if weak else ("clean", ["strong_positive", "no_correction"])
    return "unverified", ["nothing_proved_the_work"] + weak


def _delta(outcome: str, basis: list[str]) -> float:
    """What a graded reuse does to confidence: a clean one raises it, a corrected or failed one lowers it, and words
    that read as a correction lower it a little when nothing stronger did."""
    if outcome == "clean":
        return CLEAN_REUSE
    if outcome in ("corrected", "failed"):
        return NEGATIVE_REUSE
    return WEAK_NEGATIVE if "reaction_corrected" in (basis or []) else 0.0


def counted_reuses(evs: list[dict]) -> list[dict]:
    """The reuse events that count, in log order: for each piece and task only the latest one (a task is graded when
    it ends and amended when the person's next request brings their words or their edits), so one piece of work
    never yields two reuses. An event without a task (a replay) counts on its own."""
    last: dict[tuple, int] = {}
    for n, e in enumerate(evs):
        if e.get("type") == "reuse" and e.get("task_id"):
            last[(e.get("piece"), e.get("task_id"))] = n
    return [e for n, e in enumerate(evs) if e.get("type") == "reuse"
            and (not e.get("task_id") or last.get((e.get("piece"), e.get("task_id"))) == n)]


def finish_task(sid: str | None, task_id: str | None, state: dict, stage: str = "stop") -> list[dict]:
    """Grade the pieces a task used: one `reuse` event per piece (not one it saved), then each piece is graded.

    Called when the task ends (`stage` "stop": the objective evidence is final then), again when the person's next
    request brings their reaction and their edits ("next_request"), and for a task that ended without being graded
    ("catch_up", at the next session start in the project). The task is judged afresh each time; a new event is
    written only when the outcome or its basis changed, and it `amends` the earlier one, which stops counting
    (`counted_reuses`). Confidence moves by the difference. An apply model's failure marks the piece for review at the
    next frontier session. Returns the events written."""
    from athos import autolearn
    if not task_id:
        return []
    # The session that wrote (or improved) a piece does not count its reuse: the same model, the same context, often
    # the same work seen twice. A reuse graded before the piece was improved in the same session stops counting.
    written = set(state.get("task_saved") or []) | set(state.get("saved") or [])
    loaded = list(dict.fromkeys(state.get("task_loaded") or []))
    model = state.get("model")
    mode = autolearn.mode_for(model)
    if mode == autolearn.UNKNOWN or not session.observed(state):
        return []                                # a reuse is credited to a tier only when the model was seen
    tier = "frontier" if mode == autolearn.LEARN else "apply"
    evs = [e for e in ev.events() if e.get("type") == "reuse" and e.get("task_id") == task_id]
    items = evidence.of_task(task_id)
    out = []
    for pid in loaded:
        before = next((e for e in reversed(evs) if e.get("piece") == pid), None)
        if pid in written and not before:
            continue
        p = store.get(pid)
        if p is None:
            continue
        if pid in written:
            outcome, basis = "unverified", ["written_in_session"]
        else:
            outcome, basis = _outcome(pid, tier, items)
        if before and (before.get("outcome"), list(before.get("basis") or [])) == (outcome, basis):
            continue                             # nothing new about this task
        verdict = latest_verdict(p) if p.status == "candidate" else None
        event = {"type": "reuse", "piece": pid, "version": before.get("version") if before else p.version,
                 "task_id": task_id, "verdict": before.get("verdict") if before else (verdict or {}).get("outcome"),
                 "session_id": sid, "tier": tier, "model": model, "outcome": outcome, "basis": basis,
                 "status": store.status(p), "project": p.projects[0] if p.projects else None, "stage": stage,
                 **({"amends": before.get("outcome")} if before else {})}
        ev.audit(event)
        out.append(event)
        change = _delta(outcome, basis) - (_delta(before.get("outcome"), before.get("basis")) if before else 0.0)
        if change:
            _set_confidence(p, change)
        if outcome in ("corrected", "failed"):
            strong = bool(set(basis) & STRONG_NEGATIVE)
            if tier == "apply":
                mark_review(pid, f"{outcome} on {model}: {', '.join(basis)}")
            if not evaluate(pid, trigger=f"reuse {outcome}"):
                demote(pid, f"{outcome} reuse on {tier} ({', '.join(basis)})", strong)
            continue
        evaluate(pid, trigger=f"reuse {outcome}")
    return out


def catch_up(project: str | None, days: int = 14, limit: int = 50) -> list[dict]:
    """Grade the tasks of a project that ended (a `task_end`) without being graded: a session killed before its next
    request, or one run by a version that graded only at the next request. Read from the log: the pieces the task
    used, the pieces its session saved, its model and whether the model was seen. The same rules as at the end of a
    task (`finish_task`), at the next session start in the project. Returns the events written."""
    if not project:
        return []
    evs = ev.events()
    since = ev._iso(ev.now() - _dt.timedelta(days=days))
    starts = {e.get("task_id"): e for e in evs if e.get("type") == "task_start" and e.get("task_id")}
    graded = {(e.get("piece"), e.get("task_id")) for e in evs if e.get("type") == "reuse"}
    wrong = {(e.get("task_id"), e.get("piece")) for e in evs if e.get("type") == "correction"
             and e.get("target") == "task_pieces"}
    saved_by: dict[str, set] = {}
    for e in evs:
        if e.get("session_id") and (e.get("type") == "task_end" or (e.get("type") == "learn"
                                                                    and e.get("decision") == "saved")):
            saved_by.setdefault(e["session_id"], set()).update(e.get("saved") or [])
            if e.get("piece") and e.get("type") == "learn":
                saved_by[e["session_id"]].add(e["piece"])
    ends: dict[str, dict] = {}
    for e in evs:
        if e.get("type") != "task_end" or not e.get("task_id") or (e.get("at") or "") < since:
            continue
        start = starts.get(e["task_id"]) or {}
        if start.get("project") != project:
            continue
        held = ends.setdefault(e["task_id"], {"pieces": [], "saved": [], "session_id": e.get("session_id")})
        held["pieces"] = list(dict.fromkeys([*held["pieces"], *(e.get("pieces") or [])]))
        held["saved"] = list(dict.fromkeys([*held["saved"], *(e.get("saved") or [])]))
        if e.get("model") not in (None, "", session.UNKNOWN_MODEL):
            held["model"], held["observed"] = e["model"], e.get("model_observed") is not False
    out = []
    for task_id, held in list(ends.items())[-limit:]:
        pieces = [p for p in held["pieces"] if (p, task_id) not in graded and (task_id, p) not in wrong]
        if not pieces or not held.get("model"):
            continue
        state = {"task_loaded": pieces, "task_saved": held["saved"],
                 "saved": sorted(saved_by.get(held.get("session_id") or "", set())), "model": held["model"],
                 "model_observed": held.get("observed", False)}
        out += finish_task(held.get("session_id"), task_id, state, stage="catch_up")
    return out


# ------------------------------------------------------------------------------------------------ review marks
def _review_file():
    return paths.home() / "autolearn" / "review.json"


def reviews(strict: bool = False) -> dict:
    """The review marks. One that cannot be read is {} to a reader and, with `strict` (before a change is written
    back), paths.StateUnreadable."""
    try:
        data = paths.read_state(_review_file())
    except paths.StateUnreadable:
        if strict:
            raise
        return {}
    return data if isinstance(data, dict) else {}


def mark_review(piece_id: str, why: str, kind: str = "") -> None:
    """A piece needs a look: it failed on an apply model (the next frontier session's index says so), or, with
    `kind="set_aside"`, the verifier kept rejecting it and only the person can decide (`athos report`, `athos audit`)."""
    with paths.locked(_review_file()):
        data = reviews(strict=True)
        data[piece_id] = {"why": why, "at": ev._iso(ev.now()), **({"kind": kind} if kind else {})}
        paths.write_atomic(_review_file(), json.dumps(data, indent=1))


def clear_review(piece_id: str) -> None:
    with paths.locked(_review_file()):
        data = reviews(strict=True)
        if data.pop(piece_id, None) is not None:
            paths.write_atomic(_review_file(), json.dumps(data, indent=1))


# ------------------------------------------------------------------------------------------------ ageing
def age_all(today: _dt.date | None = None, days: int | None = None) -> list[str]:
    """Verified pieces with no use and no re-verification in `days` (autolearn `age_days`) go back to candidate. Using
    a piece moves its last-used date, so use slows ageing. Legacy pieces never age. Returns the ids moved."""
    from athos import autolearn
    today = today or _dt.date.today()
    days = int(days if days is not None else autolearn.settings().get("age_days") or 90)
    moved = []
    for p in store.all_pieces():
        if p.status != "verified":
            continue
        dates = [d for d in (p.last_used, p.last_verified, p.created) if d]
        try:
            idle = (today - max(_dt.date.fromisoformat(d) for d in dates)).days
        except ValueError:
            continue
        if idle > days:
            store.set_status(p.id, "candidate", f"aged: {idle} days without use or re-verification")
            note(p.id, "verified", "candidate", f"aged: {idle} days without use or re-verification (limit {days})")
            moved.append(p.id)
    return moved


# ------------------------------------------------------------------------------------------------ the router
def router_factor(p: store.Piece) -> float:
    """How much a piece's confidence moves its router score: 1 for a piece without confidence (every legacy piece),
    from 0.92 (confidence 0.3) to 1.06 (confidence 1). Modest on purpose: the words decide, confidence breaks near
    ties."""
    c = store.confidence(p)
    return 1.0 if c is None else 1.0 + 0.2 * (c - 0.7)


# ------------------------------------------------------------------------------------------------ the environment
_SPAN = re.compile(r"`([^`\n]+)`")
_FILE_END = re.compile(r"\.(?:py|md|json|jsonl|js|mjs|cjs|ts|tsx|jsx|sh|toml|ya?ml|txt|cfg|ini|lock|html|css|sql|"
                       r"rb|go|rs|java|kt|swift|c|h|cpp|tsx)$")
_NOT_A_COMMAND = {"cd", "export", "echo", "source", "set", "unset", "for", "if", "then", "do", "done", "while", "env",
                  "time", "true", "false", "test", "[", "sudo", "athos", "nice", "timeout", "exec", "eval", "read",
                  "printf", "return", "exit", "case", "esac", "fi", "else", "elif", "local", "alias", "type",
                  "which", "command", "builtin", "wait", "kill", "trap", "shift", "pushd", "popd", "ulimit", "umask"}


def refs(p: store.Piece) -> dict[str, list[str]]:
    """What a piece names that can be checked without running anything: files relative to the repository, the
    commands its command lines start with, `npm run` scripts and `make` targets. Absolute paths, globs and
    placeholders are skipped; flags of other commands cannot be checked statically and are not."""
    out: dict[str, list[str]] = {"files": [], "commands": [], "scripts": [], "targets": []}
    for span in _SPAN.findall(p.body):
        s = span.strip()
        if not s or any(c in s for c in "<>*${}?|") or s.startswith(("/", "~", "http", "-", "#")):
            continue
        words = [w for w in s.split() if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]
        if not words:
            continue
        if len(words) == 1 and ("/" in s or _FILE_END.search(s)) and not s.endswith("/"):
            out["files"].append(s.lstrip("./") if s.startswith("./") else s)
            continue
        if len(words) < 2:
            continue
        head = words[0]
        if head.startswith("./") or "/" in head:
            out["files"].append(head[2:] if head.startswith("./") else head)
        elif re.fullmatch(r"[a-z][a-z0-9._+-]*", head) and head not in _NOT_A_COMMAND:
            out["commands"].append(head)
        if head in ("npm", "pnpm", "yarn", "bun") and len(words) >= 3 and words[1] == "run":
            out["scripts"].append(words[2])
        elif head == "make" and not words[1].startswith("-"):
            out["targets"].append(words[1])
    return {k: list(dict.fromkeys(v))[:20] for k, v in out.items()}


def reverify(p: store.Piece, cwd: str | None) -> dict:
    """Check, without running anything, that what the piece names still exists here: its files under the repository,
    its commands on PATH, its `npm run` scripts in package.json, its `make` targets in the Makefile. Returns how many
    of each were checked and missing."""
    import os
    import shutil
    root = paths.repo_root(cwd) if cwd else None
    found = refs(p)
    missing = {"files": 0, "commands": 0, "scripts": 0, "targets": 0}
    checked = 0
    if root is not None:
        for f in found["files"]:
            checked += 1
            missing["files"] += not (root / f).exists()
        package = root / "package.json"
        if found["scripts"] and package.is_file():
            try:
                scripts = (json.loads(package.read_text()).get("scripts") or {})
            except (OSError, ValueError):
                scripts = None
            if isinstance(scripts, dict):
                for name in found["scripts"]:
                    checked += 1
                    missing["scripts"] += name not in scripts
        makefile = root / "Makefile"
        if found["targets"] and makefile.is_file():
            text = makefile.read_text(errors="ignore")
            for t in found["targets"]:
                checked += 1
                missing["targets"] += re.search(rf"^{re.escape(t)}\s*:", text, re.M) is None
    for c in found["commands"]:
        checked += 1
        missing["commands"] += shutil.which(c, path=os.environ.get("PATH")) is None
    return {"checked": checked, "missing": missing}


def _stale_words(missing: dict) -> str:
    names = {"files": "named file(s)", "commands": "command(s)", "scripts": "npm script(s)", "targets": "make target(s)"}
    parts = [f"{n} {names[k]}" for k, n in missing.items() if n]
    return (", ".join(parts) + " not found here") if parts else ""


def reverify_cached(p: store.Piece, sid: str | None, cwd: str | None) -> str:
    """Before a frontier model is offered an old piece (none used or verified in `reverify_days`), check it against
    the environment once per session: what is missing is said in the index line, recorded as a `reverify` event,
    and lowers a learned piece's confidence (a legacy piece's file is not touched). Returns the words for the index
    ("" when nothing is missing or the piece is not old)."""
    from athos import autolearn, session
    days = int(autolearn.settings().get("reverify_days") or 14)
    dates = [d for d in (p.last_verified, p.created) if d]
    try:
        age = (_dt.date.today() - max(_dt.date.fromisoformat(d) for d in dates)).days if dates else 0
    except ValueError:
        age = 0
    if age < days:
        return ""
    key = f"{p.id}@{p.version}"
    state = session.load(sid) if sid else {}
    seen = dict(state.get("reverified") or {})
    if key in seen:
        return seen[key]
    result = reverify(p, cwd)
    words = _stale_words(result["missing"])
    project = p.projects[0] if p.projects else None
    if result["checked"]:
        ev.audit({"type": "reverify", "session_id": sid, "piece": p.id, "version": p.version, "age_days": age,
                  "checked": result["checked"], "missing": result["missing"], "stale": bool(words),
                  "project": project})
    if words:
        _set_confidence(p, STALE_REFS)
    if sid:
        seen[key] = words
        session.update(sid, reverified=seen)
    return words
