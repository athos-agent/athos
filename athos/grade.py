"""Grading: where each learned piece stands (candidate, verified, retired), on what basis, and how it moves.

Every move, and every decision not to move, is a `grade` event with its basis. Nothing is deleted: a status change is a
new version of the piece (store.set_status), so `athos revert` restores the one before.
"""

from __future__ import annotations

from athos import eval as ev, evidence, store

# Confidence: where a piece starts and how evidence moves it (0 to 1). A legacy piece has none and is never scored.
VERIFIER_PASS = 0.2
VERIFIER_FAIL = -0.1


def note(piece_id: str, was: str, now: str, basis: str, **more) -> None:
    """The `grade` audit event: a piece's status before and after (the same when it did not move) and why."""
    p = store.get(piece_id)
    project = p.projects[0] if p and p.projects else None
    from athos import load
    named = load.loggable([p], project) if p else piece_id
    ev.audit({"type": "grade", "piece": piece_id, "version": p.version if p else None, "from": was, "to": now,
              "basis": basis, "project": project, **more},
             line=f"{named}: {was} → {now} · {basis}" if was != now else f"{named}: stays {now} · {basis}",
             project=project)


def _bump_confidence(p: store.Piece, delta: float) -> str:
    base = store.confidence(p)
    value = 0.5 if base is None else base
    return f"{max(0.05, min(1.0, value + delta)):.2f}"


def _add_evidence(p: store.Piece, token: str) -> list[str]:
    items = [e for e in p.evidence if not e.startswith(token.split(":", 1)[0] + ":")] + [token]
    return items[-8:]


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
                       confidence=_bump_confidence(p, VERIFIER_PASS if outcome == "pass" else VERIFIER_FAIL),
                       **({"last_verified": store.today()} if outcome == "pass" else {}))
        failed = sorted(c for c, ok in (out.get("verdict") or {}).items() if not ok)
        basis = "verifier_passed" if outcome == "pass" else "verifier_failed: " + ", ".join(failed)
    else:
        basis = f"verifier_{outcome}: {out.get('error')}"
    moved = evaluate(piece_id, trigger=basis)
    if not moved:
        note(piece_id, was, was, basis, verifier=outcome, verifier_model=out.get("model"),
             same_model_fallback=out.get("same_model_fallback"))
    _learn(p, outcome, basis, out)


def _learn(p: store.Piece, outcome: str, basis: str, out: dict) -> None:
    project = p.projects[0] if p.projects else None
    ev.audit({"type": "learn", "task_id": out.get("task_id"), "decision": "graded", "reason": basis,
              "piece": p.id, "version": p.version, "verifier": outcome, "verifier_model": out.get("model"),
              "worker_model": out.get("worker_model"), "same_model_fallback": out.get("same_model_fallback"),
              "project": project, **evidence.counts(evidence.of_task(out.get("task_id")))})


def evaluate(piece_id: str, trigger: str = "") -> bool:
    """Move a piece when the rules say so; True when it moved. (Promotion and demotion come with the next version.)"""
    return False
