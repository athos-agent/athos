"""Capture: when a task ends, Claude itself writes down the know-how it used, as one piece.

The Stop hook does not extract anything on its own and calls no model: when enough work happened since the last
capture, it asks Claude (who has the whole context) to decide whether the task taught something reusable and, if so,
to save it with `athos save`. Nothing new leaves the machine.
"""

from __future__ import annotations

import os
import re

from athos import eval as ev, paths, session, store

THRESHOLD = 3          # tool calls in the turn before a Stop asks for one (a release took 3); one must change something

# A task that follows a checklist carries know-how worth keeping even when it changes no file (a lawyer reviewing a
# contract only reads and answers): the word itself, a list the person pasted, or a checklist file the agent opened.
CHECKLIST = re.compile(r"check[- ]?lists?\b|lista de (verificaci[oó]n|control|chequeo|comprobaci[oó]n)"
                       r"|\bprotocol[oe]?s?\b", re.IGNORECASE)
LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)]|\[[ xX]\])\s+\S", re.MULTILINE)

FORMAT = """{cmd} save <<'EOF'
---
title: <short imperative title>
when: <the situation this applies to, specific enough to match a future request>
id: <only to improve an existing piece: its id>
note: <only when improving: what changed and why>
---
## #<statement_id>
**When:** <the moment in the task this step applies, as you would recognise it mid-task>
**Do:** <the action, concrete enough to check: a command, a file, a question to the person, a refusal>
**Because:** <the reason or the evidence: an incident, a measurement, the person's decision>
**Links:** <[[page#statement]] of what applies next or alongside, in this piece or another one>

## #<next_statement_id>
...
EOF

One statement per step, in the order the task goes. Keep the person's exact conventions verbatim (names, message
formats, paths, flags); never turn them into placeholders. No secrets, tokens or personal data. Links are the
trajectory: link a statement to the one applied right after it or with it in this task, including statements of
other pieces loaded in this session; never link by topic alone. When improving an old piece written as numbered steps,
rewrite it as statements."""


GUIDE = """## Saving know-how (Athos)

When a task in this session teaches something reusable (how it was solved, the criteria, the steps, the mistakes
avoided), Athos's Stop hook asks once with a short line. Then either save exactly one piece by running:

{format}

or, if nothing reusable came out of it, just stop. If a piece already loaded in this session covers the task, improve
it (its `id:` and a `note:`) instead of creating a new one. Don't announce the save in your answer and don't print the
piece: Athos itself shows the user one line with what was saved and where it is available."""


def guide(cmd: str = "athos") -> str:
    """The capture instructions, given once at session start (out of the user's sight) so the Stop hook can be short."""
    return GUIDE.format(format=FORMAT.format(cmd=cmd))


def origin_for(session_id: str, transcript_path: str | None = None) -> dict:
    state = session.load(session_id)
    model = state.get("model") or session.model_from_transcript(transcript_path)
    return {"platform": state.get("platform", "claude-code"), "model": model}


def save_text(text: str, session_id: str = "default", cwd: str | None = None,
              transcript_path: str | None = None) -> tuple[store.Piece, str | None]:
    """Save a piece written by Claude. With an existing `id` it improves that piece (new version, history line,
    diff returned); otherwise it creates a new one. Raises ValueError when title, when or body is missing."""
    data, body = store.parse_frontmatter(text.strip())
    body = body.strip()
    title, when = data.get("title", "").strip(), data.get("when", "").strip()
    pid = data.get("id", "").strip()
    origin = origin_for(session_id, transcript_path)
    project = paths.project_of(cwd)
    existing = store.get(pid) if pid else None
    if existing is not None:
        if not (body or title or when):
            raise ValueError("nothing to change")
        piece, diff = store.update(pid, data.get("note", ""), body=body or None, title=title or None,
                                   when=when or None, origin=origin, projects=[project])
    else:
        missing = [k for k, v in (("title", title), ("when", when), ("body", body)) if not v]
        if missing:
            raise ValueError("missing " + ", ".join(missing))
        piece, diff = store.create(title, when, body, projects=[project], origin=origin, piece_id=pid or None), None
    state = session.load(session_id)
    state["saved"] = sorted(set(state.get("saved", [])) | {piece.id})
    state["tools_since_capture"] = state["work_since_capture"] = 0
    session.save(session_id, state)
    ev.note_saved(session_id, piece.id)
    from athos import wiki
    try:
        rebuilt = wiki.rebuild()
        if wiki.agents_target():
            wiki.install_agents(wiki.agents_target())
    except OSError:
        rebuilt = None
    state = session.load(session_id)
    state["last_saved"] = {"id": piece.id, "title": piece.title, "version": piece.version,
                           "platforms": ["Claude Code", *sync_other_agents()]}
    try:
        same_moment = wiki.overlaps(piece)
    except OSError:
        same_moment = []
    state["wiki"] = rebuilt and {"broken": rebuilt["lint"]["broken"], "agents": rebuilt["agents"],
                                 "overlaps": same_moment}
    session.save(session_id, state)
    return piece, diff


def sync_other_agents() -> list[str]:
    """Where the new piece is also ready: once the person exported the know-how for Codex and Muse Code (both read
    ~/.agents/skills), every save refreshes that export, so the piece is there with no extra step."""
    from athos.adapters import codex
    d = codex.skills_dir()
    try:
        if not any(x.name.startswith(codex.SKILL_PREFIX) for x in d.iterdir()):
            return []
        codex.export_skills(d)
    except OSError:
        return []
    return ["Codex", "Muse Code"]


def _counts(event: dict) -> bool:
    """Only the main conversation's own work counts: a subagent's tool calls (a background agent included) fire the
    hook with the parent's session id, and Athos's own commands are not work to capture."""
    if event.get("agent_id"):
        return False
    cmd = str((event.get("tool_input") or {}).get("command", ""))
    return not re.search(r"(^|[\s/])athos(\s|$)", cmd)


# Tools that only look: a turn made of them (reading files, searching, checking a PR) taught nothing to keep.
READ_TOOLS = {"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "ToolSearch", "TodoWrite", "ListMcpResourcesTool",
              "ReadMcpResourceTool", "AskUserQuestion",
              # Muse Code's
              "read_file", "read_skill", "search", "list_dir", "glob", "grep", "web_fetch", "web_search",
              "submit_reminder_decision"}
READ_COMMANDS = {"ls", "cat", "head", "tail", "less", "grep", "rg", "egrep", "find", "which", "type", "wc", "echo", "pwd",
                 "file", "stat", "du", "df", "jq", "sort", "uniq", "cut", "tr", "diff", "cmp", "date", "env", "printenv",
                 "whoami", "uname", "test", "[", "true", "cd", "sleep", "column", "basename", "dirname", "realpath"}
READ_SUBCOMMANDS = {"git": {"status", "log", "diff", "show", "fetch", "branch", "remote", "rev-parse", "merge-base",
                            "ls-files", "blame", "describe", "config"},
                    "gh": {"pr view", "pr list", "pr checks", "pr diff", "pr status", "run view", "run list",
                           "issue view", "issue list", "repo view", "api", "auth status", "search"}}


def _read_only_shell(cmd: str) -> bool:
    """A shell command that only reads: every piece of its chain is a known read-only command and nothing is written
    to a file. `sed -n` reads; `sed -i` and any other unknown command count as work."""
    if re.search(r"(?<![0-9&])>(?!&|\s*/dev/null)", cmd):
        return False
    for part in re.split(r"&&|\|\||[;|\n]", cmd):
        words = [w for w in part.strip().split() if not re.match(r"^[A-Z_][A-Z0-9_]*=", w)]
        if not words:
            continue
        head = words[0].rsplit("/", 1)[-1]
        if head == "sed":
            if "-n" not in words or "-i" in words:
                return False
        elif head in READ_SUBCOMMANDS:
            rest = " ".join(w for w in words[1:] if not w.startswith("-"))
            if not any(rest == sub or rest.startswith(sub + " ") for sub in READ_SUBCOMMANDS[head]):
                return False
            if head == "gh" and rest.startswith("api") and re.search(r"-X\s*(POST|PUT|PATCH|DELETE)", part):
                return False
        elif head not in READ_COMMANDS:
            return False
    return True


def _does_work(event: dict) -> bool:
    """Whether a tool call changed something (an edit, a write, a command that is not a pure read). Calls with no tool
    name, or a tool Athos does not know, count as work."""
    tool = event.get("tool_name") or ""
    if tool in READ_TOOLS:
        return False
    if tool in ("Bash", "bash"):
        return not _read_only_shell(str((event.get("tool_input") or {}).get("command", "")))
    return True


def mentions_checklist(text: str) -> bool:
    """A checklist in the request: named as such, or three or more list items the person typed or pasted."""
    return bool(CHECKLIST.search(text or "")) or len(LIST_ITEM.findall(text or "")) >= 3


def note_request(event: dict) -> None:
    """UserPromptSubmit, after the task has started: remember whether this request works from a checklist."""
    if mentions_checklist(event.get("prompt", "")):
        session.update(event.get("session_id", "default"), checklist=True)


def count_tool(event: dict) -> None:
    if not _counts(event):
        return
    sid = event.get("session_id", "default")
    state = session.load(sid)
    tin = event.get("tool_input") or {}
    if any(CHECKLIST.search(str(tin.get(k, ""))) for k in ("file_path", "path", "command", "pattern")):
        state["checklist"] = True                               # the agent opened or searched a checklist
    state["tools_since_capture"] = state.get("tools_since_capture", 0) + 1
    if _does_work(event):
        state["work_since_capture"] = state.get("work_since_capture", 0) + 1
    session.save(sid, state)


def enabled() -> bool:
    return os.environ.get("ATHOS_CAPTURE", "").lower() not in ("off", "0", "false", "no")


def stop_decision(event: dict, cmd: str = "athos") -> dict | None:
    """The Stop hook's answer: `{"decision": "block", "reason": ...}` asks Claude to capture; None lets it stop."""
    if not enabled():
        return None
    if event.get("stop_hook_active"):
        return None
    sid = event.get("session_id", "default")
    state = session.load(sid)
    # Ask only after real work: enough tool calls, and at least one that changed something. A turn of reads and
    # checks (answering a question, looking at a PR) ends quietly.
    # A checklist the task followed is worth asking about even without file changes, unless a piece already led it.
    checklist = bool(state.get("checklist")) and not state.get("task_loaded")
    if not checklist and (state.get("tools_since_capture", 0) < THRESHOLD or not state.get("work_since_capture", 0)):
        return None
    state["tools_since_capture"] = state["work_since_capture"] = 0
    state["checklist"] = False
    state["asked"] = state.get("asked", 0) + 1
    session.save(sid, state)
    if state.get("guide"):
        # One short line: the full instructions went in at session start, out of the user's sight (and again after a
        # compaction, which starts the session anew).
        from athos import start
        if checklist:                       # the reason it asks is the checklist: say so
            if start.lang() == "es":
                return {"decision": "block",
                        "reason": f"Athos: esta tarea siguió un checklist, y eso es know-how valioso. Guardalo como "
                                  f"forma de trabajar con `{cmd} save`, como dice la guía de la sesión, o terminá."}
            return {"decision": "block",
                    "reason": f"Athos: this task followed a checklist, which is know-how worth keeping. Save it as a "
                              f"piece with `{cmd} save` as the session guide says, or just stop."}
        if start.lang() == "es":            # the person reads this line too: in their language
            return {"decision": "block",
                    "reason": f"Athos: ¿algo de esta tarea vale la pena guardar? Guardá o mejorá una forma de "
                              f"trabajar con `{cmd} save` como dice la guía de la sesión, o terminá."}
        return {"decision": "block",
                "reason": f"Athos: anything reusable to keep? Save or improve one piece with `{cmd} save` as the "
                          f"session guide says, or just stop."}
    used = state.get("loaded", [])
    improve = (f" Pieces loaded in this session: {', '.join(used)}. If this task refined one of them, improve it "
               f"(give its id and a note) instead of creating a duplicate.") if used else ""
    lead = "Athos: this task followed a checklist, which is know-how worth keeping. " if checklist else "Athos: "
    reason = (lead + "Before you stop, decide whether this task taught reusable know-how: how it was solved, the "
              "criteria, the steps, the mistakes avoided. If it did not, just stop. If it did, save exactly one piece "
              "by running:\n\n" + FORMAT.format(cmd=cmd) + "\n\nDon't announce it: Athos shows the user what was "
              "saved." + improve)
    return {"decision": "block", "reason": reason}
