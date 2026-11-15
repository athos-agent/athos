"""`athos repair`: correct a session's polluted statistics without editing history.

Before 0.1.111 a project with no pieces of its own saw every piece, so pieces of other projects loaded into its
requests and every such task counted as a use of them; and before 0.1.112 the edit detector gave the agent's own edits
(a script, `sed -i`, a formatter) to the person, as `learned_from_edit` events. Those lines stay in `events.jsonl` as
they were written. This command appends `correction` events that say which of them were wrong, and the statistics
(`eval.tasks`, so `athos report`, the bars, curating and grading) stop counting them.

    learned_from_edit   an event of the session with no evidence that the person made the edit (no `basis`: written
                        by the detector before 0.1.112)
    task_pieces         a piece a task of the session counted as used that was only injected by mistake: a piece of
                        another project, or any piece when the session's project has no pieces of its own (it then
                        saw every piece); a piece the model opened itself (`piece_opened`) is a real use and stays

It is a dry run unless `--apply` is given, and running it twice writes nothing new.
"""

from __future__ import annotations

from athos import audit, eval as ev, store

TARGETS = ("learned_from_edit", "task_pieces")
PIECE_MODES = ("mistaken", "foreign", "all", "none")


def _corrected(events: list[dict]) -> set[tuple]:
    return {(e.get("target"), e.get("task_id"), e.get("piece"), e.get("original_at")) for e in events
            if e.get("type") == "correction"}


def plan(session: str, pieces: str = "mistaken", events: list[dict] | None = None,
         all_pieces: list[store.Piece] | None = None) -> dict:
    """What `--apply` would write for one session (a unique prefix of its id is enough): the corrections, each with
    its target, task, piece and reason, and how many were already written."""
    if pieces not in PIECE_MODES:
        raise ValueError(f"--pieces: one of {', '.join(PIECE_MODES)}")
    events = ev.events() if events is None else events
    groups = audit.pick(events, session=session)
    if len(groups) != 1:
        raise LookupError(f"{len(groups)} sessions match {session!r}: give more of its id")
    sid, evs = next(iter(groups.items()))
    project = audit._project_of(evs)
    known = {p.id: p for p in (store.all_pieces() if all_pieces is None else all_pieces)}
    own = any(project and project in p.projects for p in known.values())
    done = _corrected(events)
    out: list[dict] = []
    for e in evs:
        if e.get("type") == "learned_from_edit" and not e.get("basis"):
            out.append({"target": "learned_from_edit", "task_id": e.get("task_id"), "piece": e.get("piece"),
                        "original_at": e.get("at"), "reason": "no_evidence_the_person_edited"})
    opened = {(e.get("task_id"), e.get("piece")) for e in evs if e.get("type") == "piece_opened"}
    if pieces != "none":
        for e in evs:
            if e.get("type") != "task_end":
                continue
            for pid in e.get("pieces") or []:
                p = known.get(pid)
                foreign = bool(p and p.projects and project and project not in p.projects)
                wrong = (pieces == "all" or foreign or (pieces == "mistaken" and project and not own))
                if not wrong or (e.get("task_id"), pid) in opened:
                    continue
                reason = "another_project" if foreign else ("project_without_own_pieces" if not own else "asked_all")
                out.append({"target": "task_pieces", "task_id": e.get("task_id"), "piece": pid,
                            "original_at": None, "reason": reason})
    unique, seen = [], set()
    for c in out:
        key = (c["target"], c["task_id"], c["piece"], c["original_at"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    fresh = [c for c in unique if (c["target"], c["task_id"], c["piece"], c["original_at"]) not in done]
    return {"session_id": sid, "project": project, "own_pieces": own, "pieces_mode": pieces,
            "corrections": fresh, "already": len(unique) - len(fresh)}


def apply(found: dict) -> int:
    """Append the planned `correction` events; returns how many were written."""
    for c in found["corrections"]:
        ev.audit({"type": "correction", "session_id": found["session_id"], **c, "by": "athos repair"})
    if found["corrections"]:
        ev.log_line("correction", found.get("project"), f"session {found['session_id'][:8]}: "
                    f"{len(found['corrections'])} correction(s) by athos repair")
    return len(found["corrections"])


def render(found: dict, applied: int | None = None, show: bool = False) -> str:
    by = {t: [c for c in found["corrections"] if c["target"] == t] for t in TARGETS}
    known = {p.id: p for p in store.all_pieces()}

    def name(pid):
        p = known.get(pid)
        if show or p is None or not p.projects or (found["project"] and found["project"] in p.projects):
            return pid
        return "a piece of another project"
    lines = [f"Session {found['session_id']} · project {found['project'] or '-'}"
             + ("" if found["own_pieces"] else " (no pieces of its own)"),
             f"  learned_from_edit without evidence: {len(by['learned_from_edit'])}",
             f"  uses counted by mistake: {len(by['task_pieces'])} in "
             f"{len({c['task_id'] for c in by['task_pieces']})} task(s)"]
    for c in by["task_pieces"][:10]:
        lines.append(f"    {c['task_id']}: {name(c['piece'])} ({c['reason']})")
    if len(by["task_pieces"]) > 10:
        lines.append(f"    … and {len(by['task_pieces']) - 10} more (--json)")
    if found["already"]:
        lines.append(f"  already corrected before: {found['already']}")
    if applied is None:
        lines.append("Dry run: nothing written. `--apply` appends these as correction events; history is not edited.")
    else:
        lines.append(f"{applied} correction event(s) written to the log; history is not edited.")
    return "\n".join(lines)
