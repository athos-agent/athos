"""`athos audit`: read Athos's own log back and say what it did wrong.

It folds `<home>/events.jsonl` by session and checks each session against a fixed list of rules, one per way Athos
has been seen to misbehave: loading another project's piece, loading in a project that has none of its own, giving
the agent's edits to the person, recording the wrong model, injecting too much, firing a special path on text the
person did not write, running two versions at once, and learning on weak evidence.

Sessions recorded before the audit events existed (`route`, `edit_seen`, `model`, `trigger`, `hook_error`) are checked
as far as their `task_start` / `task_end` / `learned_from_edit` lines allow. Every rule says how it was judged:

    flagged         the rule found something
    clean           the rule was checked and found nothing
    partial         checked with older, weaker data (said in `basis`); a clean partial result is not a proof
    not_evaluated   the data the rule needs is not there (said in `basis`)

Read-only: nothing is written. A piece of another project is named only with `show=True`; requests are never shown.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from athos import control, eval as ev, store

RULES = (
    ("other_project_load", "a piece of another project loaded without the request naming that project"),
    ("load_without_own_pieces", "a piece loaded in a project that has no pieces of its own"),
    ("edit_without_basis", "an edit given to the person with no evidence that the person made it"),
    ("model_inconsistent", "the model recorded for the session's tasks disagrees with itself or the transcript"),
    ("injected_over_cap", "more characters added to one request than the router's cap"),
    ("trigger_not_from_person", "a special path (save, adjust, gallery, share) fired on text the person didn't write"),
    ("version_mismatch", "two versions of Athos at work: the hooks' and the command line's, or two in one session"),
    ("private_piece_named", "a private piece named in any output"),
    ("weak_evidence_learning", "a piece saved by autonomous learning with only the model's opinion as evidence"),
)
WEAK_EVIDENCE = {"", "model", "model_opinion", "self_report"}
AUDIT_TYPES = {"route", "edit_seen", "model", "trigger", "hook_error", "learn", "grade", "ui"}


# ------------------------------------------------------------------------------------------------ gathering
def sessions(events: list[dict]) -> dict[str, list[dict]]:
    """Every event that names a session, grouped by it in log order; a mark joins its task's session."""
    by_task = {e["task_id"]: e.get("session_id") for e in events if e.get("type") == "task_start" and e.get("task_id")}
    out: dict[str, list[dict]] = {}
    for e in events:
        sid = e.get("session_id") or by_task.get(e.get("task_id"))
        if sid:
            out.setdefault(sid, []).append(e)
    return out


def _project_of(evs: list[dict]) -> str | None:
    found = [e.get("project") for e in evs if e.get("type") in ("task_start", "route") and e.get("project")]
    return max(set(found), key=found.count) if found else None


def pick(events: list[dict], session: str | None = None, project: str | None = None,
         last: int | None = None) -> dict[str, list[dict]]:
    """The sessions asked for: one by id (a unique prefix is enough), those of a project, the last N (by their latest
    event), or combinations; with nothing asked, the last one."""
    groups = sessions(events)
    if session:
        hits = [s for s in groups if s == session] or [s for s in groups if s.startswith(session)]
        groups = {s: groups[s] for s in hits}
    if project:
        groups = {s: evs for s, evs in groups.items() if _project_of(evs) == project}
    ordered = sorted(groups, key=lambda s: max((e.get("at") or "") for e in groups[s]))
    if last or not (session or project):
        ordered = ordered[-(last or 1):]
    return {s: groups[s] for s in ordered}


# ------------------------------------------------------------------------------------------------ the rules
def _result(rule: str, status: str, found: list[dict], basis: str) -> dict:
    return {"rule": rule, "status": status, "count": len(found), "basis": basis, "found": found}


def _status(found: list, partial: bool) -> str:
    return "flagged" if found else ("partial" if partial else "clean")


class _Ctx:
    """One session's events, sorted by kind, plus the store as it is today."""

    def __init__(self, sid: str, evs: list[dict], pieces: list[store.Piece], show: bool):
        self.sid, self.evs, self.show = sid, evs, show
        self.of = lambda kind: [e for e in evs if e.get("type") == kind]
        self.starts, self.ends, self.routes = self.of("task_start"), self.of("task_end"), self.of("route")
        self.project = _project_of(evs)
        self.byid = {p.id: p for p in pieces}
        self.own = [p for p in pieces if self.project and self.project in p.projects]
        self.start_of = {e.get("task_id"): e for e in self.starts}
        self.routed_tasks = {e.get("task_id") for e in self.routes}

    def name(self, pid: str) -> str:
        """A piece as the audit may print it: by id when it is this project's or general, or when asked to show."""
        p = self.byid.get(pid)
        if self.show or p is None or not p.projects or (self.project and self.project in p.projects):
            return pid
        return "a piece of another project"

    def foreign(self, pid: str) -> bool:
        p = self.byid.get(pid)
        return bool(p and p.projects and self.project and self.project not in p.projects)

    def loads(self) -> list[tuple[str, str, str]]:
        """(task id, piece id, how it is known) for every load of the session: the route event's choice when the task
        has one, else the pieces its task_end lists (which also count pages the model opened itself)."""
        out = [(r.get("task_id"), pid, "route") for r in self.routes for pid in r.get("chosen") or []]
        for e in self.ends:
            if e.get("task_id") not in self.routed_tasks:
                out += [(e.get("task_id"), pid, "task_end") for pid in e.get("pieces") or []]
        return list(dict.fromkeys(out))


def _other_project_load(c: _Ctx) -> dict:
    found, partial = [], False
    for tid, pid, how in c.loads():
        if not c.foreign(pid):
            continue
        route = next((r for r in c.routes if r.get("task_id") == tid), None)
        piece_projects = set(c.byid[pid].projects)
        if route is not None:
            named = set(route.get("named_projects") or []) & piece_projects
            known = True
        else:
            start = c.start_of.get(tid) or {}
            head, chars = start.get("request") or "", start.get("request_chars") or 0
            named = {q for q in piece_projects if control._named(q, head)}
            known = chars <= len(head)
            partial = True
        if not named:
            found.append({"task_id": tid, "piece": c.name(pid), "from": how,
                          **({} if known else {"note": "only the request's first 120 characters were kept"})})
    basis = ("route events" if c.routes and not partial else
             "task_end pieces (pages the model opened count too), the 120-character request head, and each piece's "
             "projects in today's store")
    return _result("other_project_load", _status(found, partial), found, basis)


def _load_without_own_pieces(c: _Ctx) -> dict:
    if c.routes and all(r.get("scope_reason") for r in c.routes):
        # Before 0.1.111 such a project saw every piece (`auto:project-without-pieces`): any load there is flagged.
        # Since then it sees only the profile (`auto:no-own-pieces`), and another project's pieces when the request
        # names that project: a load of another project's piece the request didn't name is still flagged.
        found = []
        for r in c.routes:
            reason, chosen = r.get("scope_reason") or "", r.get("chosen") or []
            if reason == "auto:project-without-pieces" and chosen:
                found.append({"task_id": r.get("task_id"), "loaded": len(chosen)})
            elif reason.startswith("auto:no-own-pieces"):
                named = set(r.get("named_projects") or [])
                odd = [pid for pid in chosen if c.foreign(pid) and not named & set(c.byid[pid].projects)]
                if odd:
                    found.append({"task_id": r.get("task_id"), "loaded": len(odd)})
        return _result("load_without_own_pieces", _status(found, False), found, "route events (scope_reason)")
    if not c.project:
        return _result("load_without_own_pieces", "not_evaluated", [], "no project recorded for the session")
    found = [] if c.own else [{"task_id": tid, "piece": c.name(pid), "from": how} for tid, pid, how in c.loads()]
    return _result("load_without_own_pieces", _status(found, True), found,
                   "task_end pieces, against the pieces tagged with this project in today's store")


def _edit_without_basis(c: _Ctx) -> dict:
    seen = [e for e in c.of("edit_seen") if e.get("attributed_to") == "person" and e.get("decision") != "pending"]
    old = c.of("learned_from_edit")
    found = [{"task_id": e.get("task_id"), "piece": c.name(e.get("piece") or ""), "detector": e.get("detector"),
              "piece_basis": e.get("piece_basis")} for e in seen if not e.get("basis")]
    if seen or (c.routes and not old):
        return _result("edit_without_basis", _status(found, False), found,
                       "edit_seen events" if seen else "edit_seen events: none gave a change to the person")
    found = [{"task_id": e.get("task_id"), "piece": c.name(e.get("piece") or ""),
              "piece_basis": "current_step" if e.get("statement") else "first_task_piece"} for e in old]
    return _result("edit_without_basis", _status(found, True), found,
                   "learned_from_edit events (written before edit_seen existed; they carry no evidence of who edited)")


def transcript_of(sid: str) -> str | None:
    """Claude Code's transcript of a session, when it is on this machine (read-only, best effort)."""
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    hits = glob.glob(str(root / "*" / f"{glob.escape(sid)}.jsonl"))
    return hits[0] if hits else None


def _transcript_models(path: str) -> list[tuple[str, str]]:
    """(time, model) of each assistant reply in a transcript."""
    out = []
    try:
        with open(path, errors="ignore") as fh:
            for line in fh:
                if '"assistant"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                msg = row.get("message") if isinstance(row, dict) else None
                model = msg.get("model") if isinstance(msg, dict) else None
                if isinstance(model, str) and model and not model.startswith("<") and row.get("timestamp"):
                    out.append((row["timestamp"], model))
    except OSError:
        return []
    return out


def _model_inconsistent(c: _Ctx, transcripts: bool) -> dict:
    found = []
    models = c.of("model")
    recorded = [e.get("model") for e in c.starts + c.ends if e.get("model") not in (None, "", "unknown")]
    explained = {m.get("model") for m in models}
    if len(set(recorded)) > 1 and not set(recorded) <= explained:
        found.append({"what": "different models recorded in one session with no model event for them",
                      "models": sorted(set(recorded))})
    for m in models:
        if m.get("seen_in_transcript") and m.get("model") and m["seen_in_transcript"] != m["model"]:
            found.append({"task_id": m.get("task_id"), "recorded": m["model"], "transcript": m["seen_in_transcript"]})
    if models:
        return _result("model_inconsistent", _status(found, False), found, "model events")
    path = transcript_of(c.sid) if transcripts else None
    if not path:
        status = "flagged" if found else "not_evaluated"
        return _result("model_inconsistent", status, found,
                       "no model events and no transcript found for this session")
    replies = [(ev._parse(t), m) for t, m in _transcript_models(path)]
    ends = {e.get("task_id"): ev._parse(e.get("at") or "") for e in c.ends}
    for s in c.starts:
        began, done = ev._parse(s.get("at") or ""), ends.get(s.get("task_id"))
        if not began or not done:
            continue
        ran = sorted({m for t, m in replies if t and began <= t <= done})
        if ran and (len(ran) > 1 or ran[0] != s.get("model")):
            found.append({"task_id": s.get("task_id"), "recorded": s.get("model"), "transcript": ran})
    return _result("model_inconsistent", _status(found, True), found,
                   "task_start models against the replies in Claude Code's transcript (no model events yet)")


def _injected_over_cap(c: _Ctx) -> dict:
    from athos import load
    if c.routes:
        found = [{"task_id": r.get("task_id"), "injected_chars": r.get("injected_chars"),
                  "cap": (r.get("thresholds") or {}).get("inject_cap", load.INJECT_CAP)} for r in c.routes
                 if (r.get("injected_chars") or 0) > (r.get("thresholds") or {}).get("inject_cap", load.INJECT_CAP)]
        return _result("injected_over_cap", _status(found, False), found,
                       "route events (since 0.1.111 a page that doesn't fit is cut, and the cut is recorded)")
    found = []
    for e in c.ends:
        pieces = [c.byid[p] for p in e.get("pieces") or [] if p in c.byid]
        size = len(load.inject_text(pieces)) if pieces else 0
        if size > load.INJECT_CAP:
            found.append({"task_id": e.get("task_id"), "estimated_chars": size, "cap": load.INJECT_CAP})
    return _result("injected_over_cap", _status(found, True), found,
                   "estimated from today's size of the pieces each task_end lists (no route events yet)")


def _trigger_not_from_person(c: _Ctx) -> dict:
    triggers = c.of("trigger")
    if not triggers:
        if c.routes:
            return _result("trigger_not_from_person", "clean", [], "trigger events: none fired")
        return _result("trigger_not_from_person", "not_evaluated", [], "no trigger events (written since 0.1.110)")
    # Since 0.1.111 a trigger event says whether the path acted; one that held back (`acted` false) did not fire.
    found = [{"task_id": t.get("task_id"), "trigger": t.get("trigger"), "wrapper": t.get("wrapper"),
              "from_person": t.get("from_person"), "signal": t.get("origin_signal")}
             for t in triggers if t.get("from_person") is not True and t.get("acted", True)]
    return _result("trigger_not_from_person", _status(found, False), found,
                   "trigger events that acted (from_person false, or unclear: an unknown leading tag, or no transcript "
                   "entry for the prompt)")


def _version_mismatch(c: _Ctx, versions: dict | None) -> dict:
    found = []
    written = sorted({e.get("v") for e in c.evs if e.get("type") in AUDIT_TYPES and e.get("v")})
    if len(written) > 1:
        found.append({"what": "the session's events were written by more than one version", "versions": written})
    agents = (versions or {}).get("agents") or {}
    hooks, cli = agents.get("claude-code"), agents.get("path")
    if hooks and cli and hooks != cli:
        found.append({"what": "checked now on this machine: Claude Code's plugin and the `athos` on PATH differ",
                      "plugin": hooks, "cli": cli})
    basis = "the version on each audit event" + (", and the installed versions now" if versions else "")
    partial = not written
    if not written and not versions:
        return _result("version_mismatch", "not_evaluated", [], "no versions on the events and none read now")
    return _result("version_mismatch", _status(found, partial), found,
                   basis + ("; the session's own events carry no version (written before 0.1.110)" if partial else ""))


def _private_piece_named(c: _Ctx) -> dict:
    """A private piece (today's `visibility`) loaded, ranked or named for a session outside its projects: in the
    route events, or in this project's log.md lines. Athos does not see the agent's replies, so a clean result covers
    only what Athos itself wrote."""
    private = {pid: p for pid, p in c.byid.items() if store.private(p)}
    if not private:
        return _result("private_piece_named", "clean", [], "no piece is private in today's store")
    outside = {pid for pid, p in private.items() if not (c.project and c.project in p.projects)}
    found = []
    for r in c.routes:
        ids = set(r.get("chosen") or []) | set(r.get("handed_over") or []) | {x.get("piece") for x in
                                                                                r.get("candidates") or []}
        hits = (ids & outside) | (ids & set(private) if r.get("public") else set())
        if hits:
            found.append({"task_id": r.get("task_id"), "where": "route event", "pieces": len(hits)})
    lines = _log_lines(c.project) if c.project else []
    named = sum(1 for line in lines if any(pid in line for pid in outside))
    if named:
        found.append({"where": "log.md", "lines": named})
    return _result("private_piece_named", _status(found, not c.routes), found,
                   "route events and this project's log.md lines, against today's visibility (the agent's replies "
                   "are not seen)")


def _log_lines(project: str) -> list[str]:
    """This project's lines in log.md (and its rotated copy)."""
    out = []
    for f in (ev.log_file().with_name("log.1.md"), ev.log_file()):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        out += [line for line in text.splitlines() if f"] route | {project} |" in line or f" | {project} | " in line]
    return out


def _weak_evidence_learning(c: _Ctx) -> dict:
    learns = [e for e in c.of("learn") if e.get("decision") == "saved"]
    if not learns:
        return _result("weak_evidence_learning", "not_evaluated", [], "no learn events (autonomous learning is not "
                                                                      "written yet)")
    found = [{"task_id": e.get("task_id"), "piece": c.name(e.get("piece") or ""), "evidence": e.get("evidence")}
             for e in learns if set(e.get("evidence") or [""]) <= WEAK_EVIDENCE]
    return _result("weak_evidence_learning", _status(found, False), found, "learn events")


# ------------------------------------------------------------------------------------------------ the report
def _summary(c: _Ctx) -> dict:
    times = [e.get("at") for e in c.evs if e.get("at")]
    loads = c.loads()
    routes = c.routes
    return {"session_id": c.sid, "project": c.project, "from": min(times, default=None),
            "to": max(times, default=None), "tasks": len(c.starts), "routes": len(routes),
            "routes_person": sum(1 for r in routes if r.get("request_kind") == "person"),
            "tasks_with_loads": len({tid for tid, _, _ in loads}),
            "loads_other_project": len({tid for tid, pid, _ in loads if c.foreign(pid)}),
            "injected_max": max((r.get("injected_chars") or 0 for r in routes), default=None),
            "edits_to_person": (len([e for e in c.of("edit_seen") if e.get("decision") == "attributed"
                                     and e.get("attributed_to") == "person"])
                                or len(c.of("learned_from_edit"))),
            "models": sorted({e.get("model") for e in c.starts if e.get("model")}),
            "triggers": len(c.of("trigger")), "hook_errors": len(c.of("hook_error")),
            "own_pieces": len(c.own), "audit_events": bool(set(e.get("type") for e in c.evs) & AUDIT_TYPES)}


def check(sid: str, evs: list[dict], pieces: list[store.Piece] | None = None, versions: dict | None = None,
          show: bool = False, transcripts: bool = True) -> dict:
    """One session: its summary and every rule's result."""
    c = _Ctx(sid, evs, store.all_pieces() if pieces is None else pieces, show)
    rules = [_other_project_load(c), _load_without_own_pieces(c), _edit_without_basis(c),
             _model_inconsistent(c, transcripts), _injected_over_cap(c), _trigger_not_from_person(c),
             _version_mismatch(c, versions), _private_piece_named(c), _weak_evidence_learning(c)]
    return {"summary": _summary(c), "rules": rules,
            "anomalies": sum(r["count"] for r in rules if r["status"] == "flagged")}


def run(session: str | None = None, project: str | None = None, last: int | None = None, show: bool = False,
        versions: dict | None = None, transcripts: bool = True) -> dict:
    events = ev.events()
    chosen = pick(events, session, project, last)
    pieces = store.all_pieces()
    return {"sessions": [check(s, evs, pieces, versions, show, transcripts) for s, evs in chosen.items()],
            "rules": [{"rule": r, "means": m} for r, m in RULES]}


def render(report: dict) -> str:
    if not report["sessions"]:
        return "athos audit: no session matches."
    lines = []
    for s in report["sessions"]:
        m = s["summary"]
        lines.append(f"Session {m['session_id']} · project {m['project'] or '-'} · {m['from'] or '?'} → "
                     f"{m['to'] or '?'}")
        lines.append(f"  {m['tasks']} tasks · {m['routes']} route events ({m['routes_person']} the person's) · "
                     f"loads in {m['tasks_with_loads']} tasks, another project's in {m['loads_other_project']} · "
                     f"{m['edits_to_person']} edits given to the person · models {', '.join(m['models']) or '-'} · "
                     f"{m['triggers']} triggers · {m['hook_errors']} hook errors · {m['own_pieces']} pieces of its own")
        if not m["audit_events"]:
            lines.append("  (recorded before the audit events: some rules are partial or could not be checked)")
        for r in s["rules"]:
            mark = {"flagged": "✗", "clean": "✓", "partial": "~", "not_evaluated": "?"}[r["status"]]
            count = f" {r['count']}" if r["status"] == "flagged" else ""
            lines.append(f"  {mark} {r['rule']}: {r['status']}{count} · {r['basis']}")
            for f in r["found"][:5]:
                lines.append("      " + ", ".join(f"{k}={v}" for k, v in f.items()))
            if len(r["found"]) > 5:
                lines.append(f"      … and {len(r['found']) - 5} more (--json)")
        lines.append(f"  {s['anomalies']} anomalies.")
        lines.append("")
    lines.append("✗ flagged · ✓ checked, nothing found · ~ checked with older data, not a proof · ? not checked. "
                 "Requests are never shown; another project's pieces are named only with --show.")
    return "\n".join(lines)
