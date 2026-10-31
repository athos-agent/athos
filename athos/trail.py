"""The trail of the current task: which of the person's know-how it walks and how, as the person would see a model's
thinking. Kept in the session state (`trail`, reset by each new task) and appended to `events.jsonl` as `trail` events,
so any surface can draw it: the Claude Code pane, `athos watch`, a page.

Items, in the order they happened:
    piece   a piece loaded for the request, with the request's words that loaded it
    read    a piece the agent opened on its own (`athos show`, or its file in the store)
    step    a statement of a piece the agent says it is on (`athos step <piece>#<statement>`); the one before is done
    new     a step the agent did that no loaded piece has (`athos step --new "<what>"`): it goes into the next save
    agent   a subagent the agent started, with what it was asked to do
    skill   a skill the agent used
"""

from __future__ import annotations

import os
import re
import subprocess
import time

from athos import paths, session, store

SHOW = re.compile(r"(?:^|[\s/;&|])athos\s+show\s+([A-Za-z0-9_-]+)")
# `athos step …` as the agent typed it, seen by the tool hook: in a sandbox (Codex, Muse Code) the command itself may
# not reach ~/.athos, but the hook runs outside it.
STEP = re.compile(r"(?:^|[\s/;&|'\"])athos['\"]?\s+step\s+(?:--new\s+(?:\"([^\"]*)\"|'([^']*)'|(\S+))|([^\s;&|'\"]+))")
STEP_TOOLS_AGENT = {"Task", "Agent"}


def items(session_id: str) -> list[dict]:
    return list(session.load(session_id).get("trail") or [])


def note(session_id: str, item: dict) -> None:
    """Add one item to the task's trail (a repeat of the last one is dropped) and to the event log."""
    from athos import eval as ev
    state = session.load(session_id)
    trail = list(state.get("trail") or [])
    if trail and {k: v for k, v in trail[-1].items() if k != "t"} == item:
        return
    if item["kind"] == "step":
        if any(x["kind"] == "step" and x["piece"] == item["piece"] and x["step"] == item["step"] for x in trail):
            for x in trail:                            # going back to a step: it is the current one again
                if x["kind"] == "step":
                    x["done"] = not (x["piece"] == item["piece"] and x["step"] == item["step"])
            state["trail"] = trail
            session.save(session_id, state)
            return
        for x in trail:
            if x["kind"] == "step":
                x["done"] = True
        item = {**item, "done": False}
    if item["kind"] in ("read", "piece") and any(x["kind"] in ("read", "piece") and x["piece"] == item["piece"]
                                                 for x in trail):
        return
    trail.append({**item, "t": round(time.time(), 1)})
    state["trail"] = trail[-60:]
    session.save(session_id, state)
    ev.append({"type": "trail", "session_id": session_id, "task_id": state.get("task_id"), "at": ev._iso(ev.now()),
               **item})


def finish(session_id: str) -> None:
    """The task ended: its current step is done too."""
    state = session.load(session_id)
    trail = state.get("trail") or []
    if any(x["kind"] == "step" and not x.get("done") for x in trail):
        for x in trail:
            if x["kind"] == "step":
                x["done"] = True
        session.save(session_id, state)


def on_tool(event: dict) -> None:
    """PostToolUse: what the tool call says about the trail (a subagent, a skill, a piece opened)."""
    if event.get("agent_id"):
        return
    sid = event.get("session_id", "default")
    if not session.load(sid).get("task_id") and event.get("cwd"):
        from athos import cli                          # a hook with its own session (Muse Code): this folder's task
        sid = cli._current_session(event["cwd"]).get("session_id") or sid
    name = event.get("tool_name") or ""
    tin = event.get("tool_input") or {}
    if name in STEP_TOOLS_AGENT:
        note(sid, {"kind": "agent", "name": str(tin.get("subagent_type") or "general-purpose"),
                   "why": str(tin.get("description") or "")[:120]})
    elif name == "Skill":
        note(sid, {"kind": "skill", "name": str(tin.get("skill") or tin.get("name") or "")})
    elif STEP.search(str(tin.get("command", ""))):
        for m in STEP.finditer(str(tin.get("command", ""))):
            new = m.group(1) or m.group(2) or m.group(3)
            try:
                step(sid, None if new else m.group(4), new)
            except SystemExit:
                pass
    else:
        pid = None
        m = SHOW.search(str(tin.get("command", "")))
        if m:
            pid = m.group(1)
        else:
            f = str(tin.get("file_path") or tin.get("path") or tin.get("filePath") or "")
            kh = str(paths.know_how())
            if f.startswith(kh) and f.endswith(".md"):
                pid = os.path.basename(f)[:-3]
        p = store.get(pid) if pid else None
        if p:
            note(sid, {"kind": "read", "piece": p.id, "title": p.title})


def step(session_id: str, ref: str | None, new: str | None) -> str:
    """`athos step <piece>#<statement>` / `athos step --new "<what>"`, run by the agent as it moves through a task."""
    if new:
        note(session_id, {"kind": "new", "text": new.strip()[:160]})
        return "ok"
    piece, _, stmt = (ref or "").lstrip("[").rstrip("]").partition("#")
    if not piece and stmt:                          # `#statement` alone: the piece the task follows
        loaded = session.load(session_id).get("task_loaded") or []
        piece = loaded[0] if loaded else ""
    p = store.get(piece)
    if not p or not stmt:
        raise SystemExit(f"athos step: expected <piece>#<statement> (got {ref!r})")
    note(session_id, {"kind": "step", "piece": p.id, "step": stmt})
    return "ok"


def label(when: str, do: str, sid: str) -> str:
    """A step as a person reads it in a task list: the action, i.e. the first clause of what to do ("Resumir en cinco
    líneas", "Revisar una por una, citando el número de cláusula"), cut at a word; else its moment; else its id in
    words. The moment ("con el contrato a la vista") goes inside the step, not in its title."""
    for text in (do, when):
        t = re.sub(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]", lambda m: m.group(2) or m.group(1), text or "")
        t = re.split(r"(?<=[.;:])\s|\s[—–]\s|\n", t.strip(), maxsplit=1)[0].strip().rstrip(".;: ")
        if t:
            if len(t) > 90:
                t = t[:t.rfind(" ", 0, 88)].rstrip(",;:( ") + "…"
            return t[0].upper() + t[1:]
    return sid.replace("_", " ").replace("-", " ").capitalize()


def view(state: dict) -> dict:
    """What the pane draws: each piece the task walks, as a page (what it is for, its steps as a task list with what
    to do and why, the pages it leads to), the steps the agent reported (done, current, ahead), what happened beside
    them, and the steps that were new."""
    from athos import eval as ev, wiki
    trail = state.get("trail") or []
    # The piece the agent reports steps of comes first, then the others by relevance (task_why keeps the ranking;
    # task_loaded is sorted by name, and put an unrelated piece first on screen, 2026-10-30).
    order: list[str] = []
    for pid in ([x["piece"] for x in trail if x.get("kind") == "step"] + list(state.get("task_why") or {})
                + list(state.get("task_loaded") or []) + [x["piece"] for x in trail if x.get("piece")]):
        if pid not in order:
            order.append(pid)
    why = state.get("task_why") or {}
    tasks = ev.tasks()

    def state_of(pid: str, sid: str) -> str:
        x = next((x for x in trail if x["kind"] == "step" and x["piece"] == pid and x["step"] == sid), None)
        return ("done" if x.get("done") else "now") if x else "ahead"

    def as_step(s, depth: int = 0) -> dict:
        d = {"id": s.id, "label": ("↳ " if depth else "") + label(s.when, s.do, s.id), "when": s.when[:200],
             "do": s.do[:400], "because": s.because[:300], "state": state_of(s.page, s.id)}
        return {**d, "piece": s.page, "depth": depth} if depth else d

    # A step that hands over to another page (**Calls:** / **If:**) shows that page's statements right under it, as
    # sub-steps, so the person sees the method expand only where the case needs it; the page isn't listed again.
    calls = {pid: {c["page"] for s in wiki.statements(store.get(pid)) for c in s.calls}
             for pid in order if store.get(pid)}
    order = [pid for pid in order if not any(pid in pages for q, pages in calls.items() if q != pid)]
    pieces = []
    for pid in order[:3]:
        p = store.get(pid)
        if not p:
            continue
        steps = []
        for s in wiki.statements(p):
            steps.append(as_step(s))
            for c in s.calls:
                q = store.get(c["page"])
                if not q or q.id == p.id:
                    continue
                subs = wiki.statements(q)
                if c["statement"]:
                    subs = subs[next((i for i, x in enumerate(subs) if x.id == c["statement"]), 0):]
                for i, sub in enumerate(subs):
                    row = as_step(sub, 1)
                    if i == 0 and c["if"]:
                        row["if"] = c["if"]
                    steps.append(row)
        how = "loaded" if pid in (state.get("task_loaded") or []) else "read"
        see = [{"id": q, "title": store.get(q).title} for q in wiki.links_of(p)[:3] if store.get(q)]
        pieces.append({"id": pid, "title": p.title, "version": p.version, "when": p.when[:600], "how": how,
                       "why": why.get(pid, []), "record": ev.record(pid, tasks), "see": see, "steps": steps})
    beside = [{k: v for k, v in x.items() if k != "t"} for x in trail if x["kind"] in ("agent", "skill")]
    # Files the person edited by hand after the agent wrote them (athos/edits.py): the agent proposed a rule in the
    # answer; [Keep this rule] sends the request that saves it in its step, so nobody has to type it.
    learned = state.get("learned_from_edit") or {}
    edits = [{**f, "keep": keep_rule_prompt(f)} for f in learned.get("files") or []
             if learned.get("task_id") == state.get("task_id")]
    new = [x["text"] for x in trail if x["kind"] == "new"]
    return {"task_id": state.get("task_id"), "request": state.get("task_request", ""), "pieces": pieces,
            "connectors": [{k: c.get(k) for k in ("name", "what", "active", "set_up", "start")}
                           for c in state.get("task_connectors") or []],
            "beside": beside, "new": new, "edits": edits, "busy": bool(trail) or bool(pieces)}


def keep_rule_prompt(f: dict) -> str:
    """What [Keep this rule] sends: an adjust request for the step the edit belongs to, in the person's language."""
    from athos import capture, start
    es = start.lang() == "es"
    ref = f"{f['piece']}#{f['statement']}" if f.get("statement") else f["piece"]
    what = (f"guardá la regla que propusiste por mi edición de {f['name']}" if es
            else f"keep the rule you proposed from my edit of {f['name']}")
    return f"{capture.ADJUST_PREFIX['es' if es else 'en']} {ref}: {what}"


# ------------------------------------------------------------------------------------------------ the greeting
def person_name() -> str:
    """How to greet the person: the name they gave `athos start`, else the first name in git's config."""
    from athos import start
    name = (start.config().get("name") or "").strip()
    if not name:
        try:
            name = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True,
                                  timeout=2).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            name = ""
    return name.split()[0] if name else ""


def greeting(lang: str, hour: int | None = None) -> str:
    hour = time.localtime().tm_hour if hour is None else hour
    part = 0 if 5 <= hour < 12 else 1 if 12 <= hour < 20 else 2
    hello = {"es": ("Buen día", "Buenas tardes", "Buenas noches"),
             "en": ("Good morning", "Good afternoon", "Good evening")}.get(lang, ("Hello",) * 3)[part]
    name = person_name()
    return f"{hello}, {name}" if name else hello
