"""Grading: where each learned piece stands (candidate, verified, retired), on what basis, and how it moves.

    candidate → verified    the independent verifier passed on the piece as it is now (athos/verify.py), it has at
                            least one runnable Check, and since it became a candidate either two clean reuses on a
                            frontier model or one pass on an apply model (a replay, or a real use whose Checks the
                            hooks saw pass). A `risk: high` piece needs the verifier and at least one clean reuse:
                            a replay alone is not enough for it.
    verified → candidate    a reuse that was corrected or failed: strong evidence tied to that piece. A legacy
                            piece (no status) never moves; grading records an event and a review mark instead.
    → retired               RETIRE_NEGATIVES corrected or failed reuses among its last RETIRE_WINDOW, counted from
                            its last status change, revert or improvement (each a new version). Retiring
                            supersedes; `athos revert` restores, with no outcome against it.
    verified → candidate    ageing: no use and no re-verification in `age_days` (90). Using a piece moves its
                            last-used date, so use slows ageing. Legacy pieces do not age.

A reuse is judged when the person's next request arrives, once their reaction and their edits are known (`finish_task`),
never in the session that wrote or improved the piece:

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
    """The verifier's latest pass on the piece as it is now (same title, when and body: a pass is about the text it
    read, never about a version number), from a bundle that held paths only and no narrative, or None."""
    evs = _events(p.id) if evs is None else evs
    mine = body_sha(p)
    passes = [e for e in evs if e.get("type") == "verify" and e.get("outcome") == "pass"
              and e.get("body_sha") == mine and e.get("paths_only") is not False
              and e.get("bundle_clean") is not False]
    return passes[-1] if passes else None


def _reuses(evs: list[dict], since: str = "", version: int | None = None) -> list[dict]:
    """The reuse events at or after `since`, and of `version` only when one is given: a status change, a revert and an
    improvement each make a new version, so outcomes counted by version start again from the piece's last change."""
    return [e for e in evs if e.get("type") == "reuse" and (e.get("at") or "") >= since
            and (version is None or e.get("version") == version)]


def standing(p: store.Piece) -> dict:
    """What the rules see for a piece: the verifier's pass, runnable Checks, clean and negative reuses since it
    became a candidate and since its last change (a revert brings back a piece with no outcomes against it), and
    its risk."""
    evs = _events(p.id)
    since = _since(evs)
    recent = _reuses(evs, since, p.version)
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


def finish_task(sid: str | None, task_id: str | None, state: dict) -> list[dict]:
    """The task before the person's new request is over, with their reaction and edits known: one `reuse` event per
    piece it used (not the one it saved), then each piece is graded. An apply model's failure marks the piece for
    review at the next frontier session."""
    from athos import autolearn
    if not task_id:
        return []
    # The session that wrote (or improved) a piece does not count its reuse: the same model, the same context, often
    # the same work seen twice.
    written = set(state.get("task_saved") or []) | set(state.get("saved") or [])
    used = [p for p in dict.fromkeys(state.get("task_loaded") or []) if p not in written]
    if not used:
        return []
    model = state.get("model")
    mode = autolearn.mode_for(model)
    if mode == autolearn.UNKNOWN or not session.observed(state):
        return []                                # a reuse is credited to a tier only when the model was seen

    tier = "frontier" if mode == autolearn.LEARN else "apply"
    items = evidence.of_task(task_id)
    out = []
    for pid in used:
        p = store.get(pid)
        if p is None:
            continue
        outcome, basis = _outcome(pid, tier, items)
        event = {"type": "reuse", "piece": pid, "version": p.version, "task_id": task_id,
                 "session_id": sid, "tier": tier, "model": model, "outcome": outcome,
                 "basis": basis, "status": store.status(p), "project": p.projects[0] if p.projects else None}
        ev.audit(event)
        out.append(event)
        if "reaction_corrected" in basis and outcome not in ("corrected", "failed"):
            _set_confidence(p, WEAK_NEGATIVE)      # words only: confidence, never the status
        if outcome == "clean":
            _set_confidence(p, CLEAN_REUSE)
        elif outcome in ("corrected", "failed"):
            _set_confidence(p, NEGATIVE_REUSE)
            strong = bool(set(basis) & STRONG_NEGATIVE)
            if tier == "apply":
                mark_review(pid, f"{outcome} on {model}: {', '.join(basis)}")
            if not evaluate(pid, trigger=f"reuse {outcome}"):
                demote(pid, f"{outcome} reuse on {tier} ({', '.join(basis)})", strong)
            continue
        evaluate(pid, trigger=f"reuse {outcome}")
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


def mark_review(piece_id: str, why: str) -> None:
    """A piece failed on an apply model: the next frontier session's index says so."""
    with paths.locked(_review_file()):
        data = reviews(strict=True)
        data[piece_id] = {"why": why, "at": ev._iso(ev.now())}
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
