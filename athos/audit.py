"""`athos audit`: read Athos's own log back and say what it did wrong.

It folds `<home>/events.jsonl` by session and checks each session against a fixed list of rules, one per way Athos
has been seen to misbehave: loading another project's piece, loading in a project that has none of its own, giving
the agent's edits to the person, recording the wrong model, injecting too much, firing a special path on text the
person did not write, running two versions at once, and, for autonomous learning, learning on weak evidence, saving on
an apply model, verifying without the independent verifier, a verifier given more than paths, and spending past the
daily cap. Those last rules read the whole log, since the verifier and the grading run outside any session.

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
import re
from pathlib import Path

from athos import control, eval as ev, store

RULES = (
    ("other_project_load", "a piece of another project loaded without the request naming that project"),
    ("load_without_own_pieces", "a piece loaded in a project that has no pieces of its own"),
    ("edit_without_basis", "an edit given to the person with no evidence that the person made it"),
    ("model_inconsistent", "a request recorded under a model other than the one that answered it (or, for older "
                           "sessions, the session's models disagree with themselves or the transcript)"),
    ("injected_over_cap", "more characters added to one request than the router's cap"),
    ("trigger_not_from_person", "a special path (save, adjust, gallery, share) fired on text the person didn't write"),
    ("version_mismatch", "two versions of Athos at work: the hooks' and the command line's, or two in one session"),
    ("private_piece_named", "a private piece named in any output"),
    ("weak_evidence_learning", "a piece saved by autonomous learning with only the model's opinion as evidence"),
    ("save_in_apply_mode", "a piece saved on an apply model (it must never happen)"),
    ("promotion_without_verifier", "a piece verified without a passing verdict of the independent verifier"),
    ("verifier_saw_summary", "a verifier given anything but the paths of its fixed input files (the worker's "
                             "summary, the conversation, other text), or a bundle with any other entry"),
    ("verifier_over_cap", "model runs Athos started in one day above the daily cap of runs or of cost"),
    ("candidate_set_aside", "a candidate the verifier rejected version after version, set aside for the person: the "
                            "model no longer rewrites it and only the person can fix, keep or retire it"),
    ("public_not_declared", "the repository the audit runs in is pushed to a code-hosting site and its .athos.toml "
                            "does not say whether it is public"),
    ("marker_name_ignored", "the repository the audit runs in has a .athos.toml whose name is not the folder's and "
                            "was never accepted on this machine, so Athos uses the folder's name"),
)
WEAK_EVIDENCE = {"", "model", "model_opinion", "self_report"}
AUDIT_TYPES = {"route", "edit_seen", "model", "trigger", "hook_error", "learn", "grade", "ui", "context", "piece_opened",
               "verify", "model_run", "reuse", "reverify", "correction"}


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

    def __init__(self, sid: str, evs: list[dict], pieces: list[store.Piece], show: bool, here=None):
        self.sid, self.evs, self.show, self.here = sid, evs, show, here
        self.of = lambda kind: [e for e in evs if e.get("type") == kind]
        self.starts, self.ends, self.routes = self.of("task_start"), self.of("task_end"), self.of("route")
        self.project = _project_of(evs)
        self.byid = {p.id: p for p in pieces}
        self.profile = set(control.profile_ids())
        self.own = [p for p in pieces if self.project and self.project in p.projects]
        self.start_of = {e.get("task_id"): e for e in self.starts}
        self.routed_tasks = {e.get("task_id") for e in self.routes}

    def name(self, pid: str) -> str:
        """A piece as the audit may print it: by id when it is this project's or general, or when asked to show."""
        p = self.byid.get(pid)
        if self.here is not None:             # run in a repository marked public: only what may load there
            return pid if self.here.may_name(pid) else "a piece of another project"
        if self.show or p is None or not p.projects or (self.project and self.project in p.projects):
            return pid
        return "a piece of another project"

    def foreign(self, pid: str) -> bool:
        """Another project's piece. A profile piece is not, whatever its tags: it applies in every project."""
        p = self.byid.get(pid)
        return bool(p and p.projects and self.project and self.project not in p.projects and pid not in self.profile)

    def loads(self) -> list[tuple[str, str, str]]:
        """(task id, piece id, how it is known) for every load of the session: the route event's choice when the task
        has one (since 0.1.116 a frontier model is only offered it, in an index: then the pieces it opened, from
        `piece_opened`), else the pieces its task_end lists (which also count pages the model opened itself)."""
        out = [(r.get("task_id"), pid, "route") for r in self.routes if r.get("delivery") != "index"
               for pid in r.get("chosen") or []]
        out += [(r.get("task_id"), pid, "handed_over") for r in self.routes if r.get("delivery") != "index"
                for pid in r.get("handed_over") or []]
        out += [(e.get("task_id"), e.get("piece"), "opened") for e in self.of("piece_opened") if e.get("piece")]
        for e in self.ends:
            if e.get("task_id") not in self.routed_tasks:
                out += [(e.get("task_id"), pid, "task_end") for pid in e.get("pieces") or []]
        return list(dict.fromkeys(out))


def _other_project_load(c: _Ctx) -> dict:
    """Loads (the router's choice, the pages it handed over to, the pages the model opened) and, for a frontier
    model, the pieces its index offered: naming another project's piece to the model is already reaching it."""
    found, partial = [], False
    offered = [(r.get("task_id"), pid, "offered") for r in c.routes if r.get("delivery") == "index"
               for pid in r.get("offered") or []]
    for tid, pid, how in list(dict.fromkeys(c.loads() + offered)):
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
    basis = ("route events (chosen, handed over, offered in an index) and the pieces the model opened"
             if c.routes and not partial else
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
                reached = list(chosen) + list(r.get("handed_over") or [])
                odd = [pid for pid in reached if c.foreign(pid) and not named & set(c.byid[pid].projects)]
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
    fixed = {(e.get("task_id"), e.get("original_at")) for e in c.of("correction")
             if e.get("target") == "learned_from_edit"}
    found = [{"task_id": e.get("task_id"), "piece": c.name(e.get("piece") or ""),
              "piece_basis": "current_step" if e.get("statement") else "first_task_piece",
              **({"corrected": True} if (e.get("task_id"), e.get("at")) in fixed else {})} for e in old]
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


def _model_per_request(c: _Ctx, models: list[dict]) -> dict:
    """Since 0.1.113 the model is resolved for every request (`model` events with a `stage`). A switch in the middle of
    a session, recorded on the requests after it, is not an anomaly. A request recorded under a model other than the
    one whose replies answered it is; so is a task_start whose model no prompt event explains.

    Since 0.1.165 a request may be decided on a guess (the person's configured default model, `observed` false) or on
    `unknown`, until a tool hook or the end of the turn observes the model (a `model` event with `corrects`). A guess
    corrected that way is judged by the observation, not flagged for itself; a guess never corrected is judged as it
    was recorded. `decided_on_guess` counts the requests decided on a guess or on unknown, `guess_wrong_tier` those
    whose observed model turned out to be of another tier."""
    from athos import session, tiers
    found = []
    at_prompt = {m.get("task_id"): m for m in models if m.get("stage") == "prompt"}
    at_end = {m.get("task_id"): m for m in models if m.get("stage") == "end"}
    fixes = {}
    for m in models:
        if m.get("corrects") is not None and m.get("stage") != "prompt":
            fixes[m.get("task_id")] = m          # the last observation that replaced a guess, per task
    checked = guesses = wrong_tier = 0
    for s in c.starts:
        tid, recorded = s.get("task_id"), s.get("model")
        told = at_prompt.get(tid)
        if told is not None and told.get("model") != recorded:
            found.append({"task_id": tid, "recorded": recorded, "model_event": told.get("model")})
        guessed = told is not None and (told.get("observed") is False
                                        or told.get("source") in (*session.GUESS_SOURCES, "unknown"))
        effective = recorded
        if guessed:
            guesses += 1
            fix = fixes.get(tid)
            if fix and fix.get("model"):
                effective = fix["model"]
                if tiers.tier_of(fix["model"]) != tiers.tier_of(recorded):
                    wrong_tier += 1
        answered = (at_end.get(tid) or {}).get("answered") or []
        if answered:
            checked += 1
            if effective not in answered:
                found.append({"task_id": tid, "recorded": recorded, "answered": answered,
                              "source": (told or {}).get("source"), **({"guessed": True} if guessed else {})})
    basis = (f"model events per request: the model recorded at each request (or, for one decided on a guess, the "
             f"model observed later in the task) against the replies that answered it ({checked} of {len(c.starts)} "
             f"tasks had their replies read; {guesses} decided on a guess or on unknown)")
    out = _result("model_inconsistent", _status(found, False), found, basis)
    out.update(decided_on_guess=guesses, guess_wrong_tier=wrong_tier)
    return out


def _model_inconsistent(c: _Ctx, transcripts: bool) -> dict:
    found = []
    models = c.of("model")
    if any(m.get("stage") for m in models):
        return _model_per_request(c, models)
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
    """Since 0.1.114 a route event carries `injected_total`, everything the prompt hook handed the model (the edit
    notice, a share request and a rating came on top of the router's text, uncounted); older route events only the
    router's own `injected_chars`."""
    from athos import load
    if c.routes:
        def cap(r: dict) -> int:
            return (r.get("thresholds") or {}).get("inject_cap", load.INJECT_CAP)

        def size(r: dict) -> int:
            return r.get("injected_total", r.get("injected_chars")) or 0
        found = [{"task_id": r.get("task_id"), "injected_total": size(r), "injected_chars": r.get("injected_chars"),
                  "cap": cap(r)} for r in c.routes if size(r) > cap(r)]
        older = not all("injected_total" in r for r in c.routes)
        return _result("injected_over_cap", _status(found, older), found,
                       "route events: everything the prompt hook handed the model (injected_total)" +
                       ("; older route events count only the router's text (injected_chars)" if older else ""))
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
             for t in triggers if t.get("stage") != "verify" and t.get("from_person") is not True
             and t.get("acted", True)]
    # Since 0.1.120 a path may act on text that reads as the person's and be checked against the transcript later:
    # one the transcript then gave to the harness is an anomaly, even when what it changed was undone.
    found += [{"task_id": t.get("task_id"), "trigger": t.get("trigger"), "verified": False, "hook": t.get("hook"),
               "undone": ",".join(t.get("undone") or []) or "nothing"}
              for t in triggers if t.get("stage") == "verify" and t.get("verified") is False]
    return _result("trigger_not_from_person", _status(found, False), found,
                   "trigger events that acted (from_person false, or unclear: an unknown leading tag, or no transcript "
                   "entry for the prompt under origin_check strict), and those the transcript gave to the harness when "
                   "checked afterwards")


OLDER_REWRITES = ("an older Athos that rewrites a piece drops the frontmatter lines it does not know (visibility, "
                  "status, risk, confidence, evidence): a private piece becomes visible again and a learned one loses "
                  "its status. Update every agent's Athos (`athos doctor`) before saving")


def _version_mismatch(c: _Ctx, versions: dict | None) -> dict:
    found = []
    written = sorted({e.get("v") for e in c.evs if e.get("type") in AUDIT_TYPES and e.get("v")})
    if len(written) > 1:
        found.append({"what": "the session's events were written by more than one version", "versions": written,
                      "risk": OLDER_REWRITES})
    agents = (versions or {}).get("agents") or {}
    hooks, cli = agents.get("claude-code"), agents.get("path")
    if hooks and cli and hooks != cli:
        found.append({"what": "checked now on this machine: Claude Code's plugin and the `athos` on PATH differ",
                      "plugin": hooks, "cli": cli, "risk": OLDER_REWRITES})
    basis = "the version on each audit event" + (", and the installed versions now" if versions else "")
    partial = not written
    if not written and not versions:
        return _result("version_mismatch", "not_evaluated", [], "no versions on the events and none read now")
    return _result("version_mismatch", _status(found, partial), found,
                   basis + ("; the session's own events carry no version (written before 0.1.110)" if partial else ""))


def _private_piece_named(c: _Ctx) -> dict:
    """A private piece (today's `visibility`) loaded, ranked, offered or named for a session outside its projects: in
    the route events, or in this project's log.md lines written while the session ran (a piece id counts as a whole
    word). In a repository marked public every piece that may not load there counts as private (control.may_see:
    another project's, or a profile piece not allowed in public). Athos does not see the agent's replies, so a clean
    result covers only what Athos itself wrote; with no route events nothing was checked."""
    if not c.routes:
        return _result("private_piece_named", "not_evaluated", [], "no route events for this session")
    public = any(r.get("public") for r in c.routes)
    private = {pid: p for pid, p in c.byid.items() if store.private(p)}
    if public and c.project:
        private.update({pid: p for pid, p in c.byid.items() if not control.may_see(p, c.project, True)})
    if not private:
        return _result("private_piece_named", "clean", [], "route events; no piece is private in today's store")
    outside = {pid for pid, p in private.items()
               if not (c.project and c.project in p.projects) or (public and not control.may_see(p, c.project, True))}
    found = []
    for r in c.routes:
        ids = set(r.get("chosen") or []) | set(r.get("handed_over") or []) | set(r.get("offered") or []) | {
            x.get("piece") for x in r.get("candidates") or []}
        hits = (ids & outside) | (ids & set(private) if r.get("public") else set())
        if hits:
            found.append({"task_id": r.get("task_id"), "where": "route event", "pieces": len(hits)})
    times = sorted(t for t in (ev._parse(e.get("at") or "") for e in c.evs) if t)
    lines = _log_lines(c.project, times[0], times[-1]) if c.project and times else []
    words = [re.compile(rf"(?<![\w-]){re.escape(pid)}(?![\w-])") for pid in outside]
    named = sum(1 for line in lines if any(w.search(line) for w in words))
    if named:
        found.append({"where": "log.md", "lines": named})
    return _result("private_piece_named", _status(found, False), found,
                   "route events and this project's log.md lines written during the session, against today's "
                   "visibility" + (" and, in a repository marked public, every piece that may not load there" if public
                                   else "") + " (the agent's replies are not seen)")


def _log_lines(project: str, since=None, until=None) -> list[str]:
    """This project's lines in log.md (and its rotated copy), only those stamped between `since` and `until` (to the
    minute, UTC) when given."""
    import datetime as _dt
    lo = since.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if since else ""
    hi = until.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if until else "9999"
    out = []
    for f in (ev.log_file().with_name("log.1.md"), ev.log_file()):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            if not (f"] route | {project} |" in line or f" | {project} | " in line):
                continue
            stamp = line[len(ev.LOG_PREFIX):len(ev.LOG_PREFIX) + 16] if line.startswith(ev.LOG_PREFIX) else ""
            if stamp and not (lo <= stamp <= hi):
                continue
            out.append(line)
    return out


def _weak_evidence_learning(c: _Ctx) -> dict:
    learns = [e for e in c.of("learn") if e.get("decision") == "saved"]
    if not learns:
        return _result("weak_evidence_learning", "not_evaluated", [], "no autonomous save in this session")
    found = [{"task_id": e.get("task_id"), "piece": c.name(e.get("piece") or ""), "evidence": e.get("evidence"),
              "strong": e.get("strong")}
             for e in learns if (not e.get("strong") if "strong" in e
                                 else set(e.get("evidence") or [""]) <= WEAK_EVIDENCE)]
    return _result("weak_evidence_learning", _status(found, False), found,
                   "learn events (saved): the count of strong items, an exit status or an artifact the hooks saw")


def _version_at_least(evs: list[dict], wanted: tuple) -> bool:
    for e in evs:
        try:
            if tuple(int(x) for x in str(e.get("v") or "").split(".")) >= wanted:
                return True
        except ValueError:
            continue
    return False


def _save_in_apply_mode(c: _Ctx) -> dict:
    """An autonomous save on a model that is not frontier, or (since 0.1.124, when apply models stopped saving) any
    task of an apply model that saved a piece."""
    from athos import tiers
    found = [{"task_id": e.get("task_id"), "piece": c.name(e.get("piece") or ""), "model": e.get("model"),
              "how": "autonomous"} for e in c.of("learn")
             if e.get("decision") == "saved" and (e.get("mode") != "learn" or e.get("tier") != tiers.FRONTIER)]
    if not _version_at_least(c.evs, (0, 1, 124)):
        status = _status(found, True) if found or c.of("learn") else "not_evaluated"
        return _result("save_in_apply_mode", status, found,
                       "recorded before 0.1.124, when an apply model could still save: only autonomous saves judged")
    for e in c.ends:
        model = e.get("model")
        if e.get("saved") and model and model != "unknown" and tiers.tier_of(model) != tiers.FRONTIER:
            found.append({"task_id": e.get("task_id"), "piece": ", ".join(c.name(p) for p in e["saved"]),
                          "model": model, "how": "task_end"})
    return _result("save_in_apply_mode", _status(found, False), found,
                   "learn events and the pieces each task saved, with the model that answered it")


def _project_events(c: _Ctx, everything: list[dict], kinds: set[str]) -> list[dict]:
    """Events of these kinds about the session's project (the verifier and the grading run outside any session)."""
    return [e for e in everything if e.get("type") in kinds and (not c.project or e.get("project") in (c.project,
                                                                                                         None))]


def _promotion_without_verifier(c: _Ctx, everything: list[dict]) -> dict:
    evs = _project_events(c, everything, {"grade", "verify"})
    promotions = [e for e in evs if e.get("type") == "grade" and e.get("to") == "verified"
                  and e.get("from") != "verified"]
    if not promotions:
        return _result("promotion_without_verifier", "not_evaluated", [], "no piece of this project was verified")
    found = []
    for g in promotions:
        before = [e for e in evs if e.get("type") == "verify" and e.get("piece") == g.get("piece")
                  and e.get("outcome") == "pass" and e.get("paths_only") is not False
                  and e.get("bundle_clean") is not False and (e.get("at") or "") <= (g.get("at") or "")]
        if not before:
            found.append({"piece": c.name(g.get("piece") or ""), "at": g.get("at"), "basis": g.get("basis")})
    return _result("promotion_without_verifier", _status(found, False), found,
                   "grade events to verified, each against an earlier passing verify event of the piece")


def _verifier_saw_summary(c: _Ctx, everything: list[dict]) -> dict:
    """Structurally: the prompt the verifier got (kept in its bundle) must be the fixed text with the bundle's input
    paths and nothing else, its inputs exactly the fixed set (verify.INPUTS; or the six of a run recorded before the
    history excerpt, or the four files of one recorded before the repository snapshot), and its bundle only the fixed
    entries."""
    from athos import verify
    runs = [e for e in _project_events(c, everything, {"verify"}) if e.get("prompt_file") or e.get("inputs")]
    if not runs:
        return _result("verifier_saw_summary", "not_evaluated", [], "no verifier ran for this project")
    found = []
    for e in runs:
        problems = []
        if e.get("paths_only") is False:
            problems.append("prompt not paths only (recorded)")
        if sorted(e.get("inputs") or []) not in [sorted(n.values()) for n, _text in verify.GENERATIONS]:
            problems.append("inputs other than the fixed set")
        bundle, prompt_file = e.get("bundle"), e.get("prompt_file")
        if e.get("bundle_clean") is False:
            problems.append("the bundle carried the worker's narrative (recorded)")
        elif bundle and os.path.isdir(bundle) and not verify.bundle_clean(bundle):
            problems.append("the bundle carries a commit message, the piece's frontmatter or an entry outside the "
                            "fixed set")
        if bundle and prompt_file and os.path.isfile(prompt_file):
            if not verify.kept_prompt_ok(Path(prompt_file).read_text(errors="ignore"), bundle):
                problems.append("the kept prompt is not the fixed text with the bundle's input paths")
        if problems:
            found.append({"piece": c.name(e.get("piece") or ""), "at": e.get("at"), "problems": problems})
    return _result("verifier_saw_summary", _status(found, False), found,
                   "verify events, and the prompt each run kept, checked against the fixed text and the input paths")


def _candidate_set_aside(c: _Ctx, everything: list[dict]) -> dict:
    """Pieces of this project set aside after repeated rejections (grade._maybe_set_aside) that are still candidates
    and still marked: the person's attention is needed."""
    from athos import grade
    marks = {pid: m for pid, m in grade.reviews().items() if (m or {}).get("kind") == "set_aside"}
    asides = [e for e in _project_events(c, everything, {"grade"}) if str(e.get("basis") or "").startswith("set_aside")]
    if not asides:
        return _result("candidate_set_aside", "not_evaluated", [], "no piece of this project was set aside")
    found, seen = [], set()
    for e in reversed(asides):
        pid = e.get("piece") or ""
        p = store.get(pid)
        if pid in seen or pid not in marks or p is None or p.status != "candidate":
            continue
        seen.add(pid)
        found.append({"piece": c.name(pid), "at": e.get("at"), "attempts": e.get("attempts"),
                      "failed": ",".join(e.get("failed") or []), "fix": f"athos show {pid}; edit it, or retire it"})
    return _result("candidate_set_aside", _status(found, False), found,
                   "grade events that set a piece aside, against the review marks and the piece's status now")


def _verifier_over_cap(everything: list[dict]) -> dict:
    """Per UTC day, each model run Athos started against the caps it recorded (a cap raised during the day applies to
    the runs after it)."""
    # One entry per run: its settled event, or only its reservation when no settled event came (a killed run, which
    # counts the whole cap it held); a run that never started counts nothing.
    settled = {e.get("run_id") for e in everything if e.get("type") == "model_run" and e.get("phase") == "settled"}
    runs = []
    for e in everything:
        if e.get("type") != "model_run":
            continue
        if e.get("phase") == "reserved":
            if e.get("run_id") not in settled:
                runs.append({**e, "cost_counted": e.get("usd_reserved") or 0.0})
        elif e.get("started", True) and e.get("phase") != "refused":
            runs.append(e)
    if not runs:
        return _result("verifier_over_cap", "not_evaluated", [], "Athos started no model run")
    days: dict[str, list[dict]] = {}
    for e in runs:
        days.setdefault(str(e.get("at", ""))[:10], []).append(e)
    found = []
    for day, group in sorted(days.items()):
        cost, over = 0.0, None
        for n, e in enumerate(group, 1):            # each run against the caps in force when it ran
            if isinstance(e.get("cost_counted"), (int, float)):     # what the ledger counted for it (since 0.1.156)
                cost += e["cost_counted"]
            else:
                cost += e["cost_usd"] if isinstance(e.get("cost_usd"), (int, float)) else \
                    float(e.get("usd_estimate_per_run") or 0)
            runs_cap, usd_cap = e.get("runs_per_day"), e.get("usd_per_day")
            if (isinstance(runs_cap, int) and n > runs_cap) or \
                    (isinstance(usd_cap, (int, float)) and cost > usd_cap + 1e-9):
                over = {"day": day, "runs": n, "runs_per_day": runs_cap, "usd": round(cost, 4), "usd_per_day": usd_cap}
        if over:
            found.append(over)
    return _result("verifier_over_cap", _status(found, False), found,
                   "model_run events per UTC day (a run with no reported cost counts the cap it reserved)")


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
            "injected_max": max((r.get("injected_total", r.get("injected_chars")) or 0 for r in routes), default=None),
            "session_start_chars": max((e.get("injected_total") or 0 for e in c.of("context")), default=None),
            "edits_to_person": (len([e for e in c.of("edit_seen") if e.get("decision") == "attributed"
                                     and e.get("attributed_to") == "person"])
                                or len(c.of("learned_from_edit"))),
            "models": sorted({e.get("model") for e in c.starts if e.get("model")}),
            "triggers": len(c.of("trigger")), "hook_errors": len(c.of("hook_error")),
            "own_pieces": len(c.own), "audit_events": bool(set(e.get("type") for e in c.evs) & AUDIT_TYPES),
            "learning": _learning(c), "ui_changes": len(c.of("ui"))}


def _learning(c: _Ctx) -> dict:
    """Whether the model keeps what tasks taught on its own: the frontier tasks that qualified (strong evidence, no
    save before the end; `qualified` under `ask: guide`, `asked` under `ask: stop`), the autonomous saves, the tasks
    that ended without one (`model_saved_nothing`), saves refused, and qualified tasks whose session never got the
    autonomous guide."""
    learns = c.of("learn")
    by = lambda d, r=None: [e for e in learns if e.get("decision") == d and (r is None or e.get("reason") == r)]
    return {"qualified": len(by("qualified")), "asked": len(by("asked")), "saved": len(by("saved")),
            "saved_nothing": len(by("skipped", "model_saved_nothing")),
            "refused": len([e for e in by("skipped") if e.get("reason") not in (
                "model_saved_nothing", "no_strong_evidence", "last_verification_failed", "correction_after_success",
                "apply_model")]),
            "without_guide": len([e for e in by("qualified") if not e.get("guide")])}


def _public_not_declared(c: _Ctx, cwd: str | None) -> dict:
    """The folder the audit runs in, when it is this session's project: a remote on a code-hosting site (from the
    repository's own git configuration; no network call) and no `public` in its `.athos.toml`. Athos cannot know
    whether that copy is public, and without the marker it treats the repository as private: another project's
    pieces load there when a request names it."""
    from athos import paths
    if not cwd:
        return _result("public_not_declared", "not_evaluated", [], "no folder to look at")
    here, mark = paths.locate(cwd)
    if c.project and here != c.project:
        return _result("public_not_declared", "not_evaluated", [],
                       "the session's project is not the folder the audit runs in")
    hosts = paths.code_remotes(cwd)
    found = [{"project": here, "pushed_to": h, "fix": "athos public (or athos public off)"} for h in hosts[:1]] \
        if hosts and "public" not in mark else []
    return _result("public_not_declared", _status(found, False), found,
                   "the local git configuration's remotes and the repository's .athos.toml (no network call: Athos "
                   "cannot know whether a repository is public)")


def _marker_name_ignored(cwd: str | None) -> dict:
    """The folder the audit runs in: a marker `name` other than the folder's own that the person never accepted
    (`athos public name`). Athos ignores it, since whoever wrote the repository wrote its marker."""
    from athos import paths
    if not cwd:
        return _result("marker_name_ignored", "not_evaluated", [], "no folder to look at")
    here, mark = paths.locate(cwd)
    found = [{"project": here, "marker_name": mark["name_ignored"], "fix": "athos public name (to accept it)"}] \
        if mark.get("name_ignored") else []
    return _result("marker_name_ignored", _status(found, False), found,
                   "the .athos.toml of the folder the audit runs in, against the names accepted on this machine")


def check(sid: str, evs: list[dict], pieces: list[store.Piece] | None = None, versions: dict | None = None,
          show: bool = False, transcripts: bool = True, cwd: str | None = None,
          everything: list[dict] | None = None, here=None) -> dict:
    """One session: its summary and every rule's result. `cwd`: the folder the audit runs in, for the rules that look
    at the repository itself. `everything`: the whole log, for the rules about the verifier and the grading, which run
    outside any session (read from the log when not given)."""
    c = _Ctx(sid, evs, store.all_pieces() if pieces is None else pieces, show and here is None, here)
    everything = ev.events() if everything is None else everything
    rules = [_other_project_load(c), _load_without_own_pieces(c), _edit_without_basis(c),
             _model_inconsistent(c, transcripts), _injected_over_cap(c), _trigger_not_from_person(c),
             _version_mismatch(c, versions), _private_piece_named(c), _weak_evidence_learning(c),
             _public_not_declared(c, cwd), _marker_name_ignored(cwd), _save_in_apply_mode(c), _promotion_without_verifier(c, everything),
             _verifier_saw_summary(c, everything), _verifier_over_cap(everything), _candidate_set_aside(c, everything)]
    return {"summary": _summary(c), "rules": rules,
            "anomalies": sum(r["count"] for r in rules if r["status"] == "flagged")}


def run(session: str | None = None, project: str | None = None, last: int | None = None, show: bool = False,
        versions: dict | None = None, transcripts: bool = True, cwd: str | None = None, here=None) -> dict:
    """`here` (control.Here), when the audit runs in a repository marked public: only that project's sessions are
    read, whatever was asked, and only what may load there is named."""
    events = ev.events()
    if here is not None:
        chosen = {s: evs for s, evs in pick(events, session, here.project, last if (last or session) else 1).items()
                  if _project_of(evs) == here.project}
    else:
        chosen = pick(events, session, project, last)
    pieces = store.all_pieces()
    return {"sessions": [check(s, evs, pieces, versions, show, transcripts, cwd, events, here)
                         for s, evs in chosen.items()],
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
        learning = m.get("learning") or {}
        if any(learning.values()):
            lines.append(f"  learning on its own: {learning['saved']} saved · {learning['qualified'] + learning['asked']}"
                         f" task(s) qualified without a save before the end ({learning['asked']} asked at the stop) · "
                         f"{learning['saved_nothing']} ended with nothing saved · {learning['refused']} save(s) refused"
                         + (f" · {learning['without_guide']} without the session guide" if learning['without_guide']
                            else ""))
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
