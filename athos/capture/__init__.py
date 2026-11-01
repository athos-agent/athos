"""Capture: turning a finished task into a saved way of working.

Athos never extracts know-how by itself and never calls a model here. It keeps count of the work done in the current
request; when a task ends after real work (or after following a checklist), the Stop hook asks the agent, which holds
the whole context, whether anything reusable came out of it and, if so, to write one piece with `athos save`.
Everything stays on this machine.
"""

from __future__ import annotations

import os
import re
from typing import NamedTuple

from athos import eval as ev, paths, session, store

THRESHOLD = 3          # tool calls before a Stop asks for one (a release took 3), when one of them edited a file
WORK_MIN = 5           # or this many calls that changed something (commands), when no file was edited
# Replayed over 706 real requests (8 sessions, 2026-10-25..29): any 3 calls with one command asked in 49% of requests
# and a third of the asks ended in a save; an edit or 5 commands asks in 34% and keeps three quarters of the saves.
# In an interactive Claude Code session the model is not asked at all: the band above the prompt offers [Save].
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch",
              # Muse Code's and OpenCode's
              "write_file", "edit_file", "write", "edit", "patch", "multiedit"}
SAVE = re.compile(r"(^|[\s/])athos[\"']?\s+save\b")
_ATHOS_COMMAND = re.compile(r"(^|[\s/])athos(\s|$)")

# A task that follows a checklist carries know-how worth keeping even when it changes no file (a lawyer reviewing a
# contract only reads and answers): the word itself, a list the person pasted, or a checklist file the agent opened.
CHECKLIST = re.compile(r"check[- ]?lists?\b|lista de (verificaci[oó]n|control|chequeo|comprobaci[oó]n)"
                       r"|\bprotocol[oe]?s?\b", re.IGNORECASE)
LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)]|\[[ xX]\])\s+\S", re.MULTILINE)
# A checklist file the request names ("con mi checklist (mi-checklist.md)") is the person's own, like a typed list.
CHECKLIST_FILE = re.compile(r"[\w./-]*check[-_ ]?list[\w-]*\.(?:md|txt|docx?|pdf|csv|xlsx?)\b", re.IGNORECASE)

# The frontmatter of a saved piece, each key with the hint the agent fills in. Same keys `store` reads, and the same
# wording as commands/capture.md.
_FRONTMATTER_HINTS = (
    ("title", "short imperative title"),
    ("when", "the situation this applies to, specific enough to match a future request"),
    ("id", "only to improve an existing piece: its id"),
    ("note", "only when improving: what changed and why"),
)
_STATEMENT_TEMPLATE = """## #<statement_id>
**When:** <the moment in the task this step applies, as you would recognise it mid-task>
**Do:** <the action, concrete enough to check: a command, a file, a question to the person, a refusal>
**Because:** <the reason or the evidence: an incident, a measurement, the person's decision>
**Links:** <[[page#statement]] of what applies next or alongside, in this piece or another one>

## #<next_statement_id>
..."""
_WRITING_RULES = """One statement per step, in the order the task goes. Keep the person's exact conventions verbatim (names, message
formats, paths, flags); never turn them into placeholders. No secrets, tokens or personal data. Links are the
trajectory: link a statement to the one applied right after it or with it in this task, including statements of
other pieces loaded in this session; never link by topic alone. When improving an old piece written as numbered steps,
rewrite it as statements."""


def _save_format() -> str:
    """The heredoc the agent runs to save, with `{cmd}` left in for the caller to fill."""
    header = "\n".join(f"{key}: <{hint}>" for key, hint in _FRONTMATTER_HINTS)
    command = "{cmd} save <<'EOF'"
    return "\n".join((command, "---", header, "---", _STATEMENT_TEMPLATE, "EOF", "", _WRITING_RULES))


FORMAT = _save_format()


GUIDE = """## Saving know-how (Athos)

When a task in this session teaches something reusable (how it was solved, the criteria, the steps, the mistakes
avoided), the person may press [Save] (a request that starts "Athos · save:"), or Athos's Stop hook asks once with a
short line. Then either save exactly one piece by running:

{format}

or, if nothing reusable came out of it, just stop. If a piece already loaded in this session covers the task, improve
it (its `id:` and a `note:`) instead of creating a new one. Don't announce the save in your answer and don't print the
piece: Athos itself shows the user one line with what was saved and where it is available.

The person watches the task's trail in Athos's pane. When a task follows none of their know-how but takes several
steps of real work, run `{cmd} step --new "<the step, in a few words, in the person's language>"` as you start each
main step (not each action), so the way of working drafts itself as you go. Say nothing about it in your answer."""


def guide(cmd: str = "athos") -> str:
    """The capture instructions, given once at session start (out of the user's sight) so the Stop hook can be short."""
    return GUIDE.format(format=FORMAT.format(cmd=cmd), cmd=cmd)


def origin_for(session_id: str, transcript_path: str | None = None) -> dict:
    """Where a piece was written: the platform the session runs on and the model, from the session state or, failing
    that, from the transcript."""
    known = session.load(session_id)
    return {"platform": known.get("platform", "claude-code"),
            "model": known.get("model") or session.model_from_transcript(transcript_path)}


def _fields(text: str) -> tuple[dict, str, str, str, str]:
    """The parts of a piece as the agent sent it: all frontmatter, then title, when, id and body, trimmed."""
    meta, body = store.parse_frontmatter(text.strip())
    title, when, piece_id = (meta.get(key, "").strip() for key in ("title", "when", "id"))
    return meta, title, when, piece_id, body.strip()


class _Written(NamedTuple):
    piece: store.Piece
    diff: str | None             # None for a new piece
    improved: bool


def _write_piece(text: str, origin: dict, project: str) -> _Written:
    """Create the piece, or improve the one its `id` names."""
    meta, title, when, piece_id, body = _fields(text)
    if piece_id and store.get(piece_id) is not None:
        if not any((body, title, when)):
            raise ValueError("nothing to change")
        piece, diff = store.update(piece_id, meta.get("note", ""), body=body or None, title=title or None,
                                   when=when or None, origin=origin, projects=[project])
        return _Written(piece, diff, True)
    absent = [name for name, value in (("title", title), ("when", when), ("body", body)) if not value]
    if absent:
        raise ValueError("missing " + ", ".join(absent))
    piece = store.create(title, when, body, projects=[project], origin=origin, piece_id=piece_id or None)
    return _Written(piece, None, False)


def _reset_counters(session_id: str, saved_id: str) -> None:
    """A save closes the request's capture: the piece joins the session's saved list and the counters start over."""
    saved = set(session.load(session_id).get("saved", []))
    session.update(session_id, saved=sorted(saved | {saved_id}), tools_since_capture=0, work_since_capture=0)
    ev.note_saved(session_id, saved_id)


def _refresh_wiki() -> dict | None:
    """Rebuild the wiki index (and the trajectory agents, when installed). None when the disk refused."""
    from athos import wiki
    try:
        rebuilt = wiki.rebuild()
        target = wiki.agents_target()
        if target:
            wiki.install_agents(target)
    except OSError:
        return None
    return rebuilt


def _overlaps(piece: store.Piece) -> list:
    from athos import wiki
    try:
        return wiki.overlaps(piece)
    except OSError:
        return []


def save_text(text: str, session_id: str = "default", cwd: str | None = None,
              transcript_path: str | None = None) -> tuple[store.Piece, str | None]:
    """`athos save`: store the piece the agent wrote, tagged with this session's origin and the project of `cwd`.

    A piece whose `id:` names one already in the store improves it (a new version and a history line, and the diff
    comes back); any other is created, and the diff is None. ValueError when a new piece lacks title, when or body,
    or an improvement changes nothing. Then the session's tallies reset, the wiki and exports refresh, and the
    session learns what was saved for the band to show."""
    written = _write_piece(text, origin_for(session_id, transcript_path), paths.project_of(cwd))
    piece = written.piece
    _reset_counters(session_id, piece.id)
    rebuilt = _refresh_wiki()
    summary = {"id": piece.id, "title": piece.title, "version": piece.version,
               "platforms": ["Claude Code", *sync_other_agents()]}
    if written.improved:
        # The piece changed: the corrections the person made on it before are the tests of the new version.
        pending = recheck(piece.id)
        if pending:
            summary.update(tests=pending, recheck=recheck_words(pending))
    wiki_state = rebuilt and {"broken": rebuilt["lint"]["broken"], "agents": rebuilt["agents"],
                              "overlaps": _overlaps(piece)}
    session.update(session_id, last_saved=summary, wiki=wiki_state)
    return written.piece, written.diff


def recheck(piece_id: str) -> int:
    """How many past corrections of this piece `athos test` can re-check (athos/cases.py)."""
    from athos import cases
    try:
        return len(cases.tests(piece_id))
    except OSError:
        return 0


def recheck_words(n: int) -> str:
    from athos import start
    if start.lang() == "es":
        return f"{n} corrección pasada para volver a probar" if n == 1 else \
            f"{n} correcciones pasadas para volver a probar"
    return f"{n} past correction{'s' if n != 1 else ''} to re-check"


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


def _command_of(event: dict) -> str:
    """The shell command a tool call ran, or "" for any other tool."""
    return str((event.get("tool_input") or {}).get("command", ""))


def _is_persons_work(event: dict) -> bool:
    """Whether a tool call belongs to the person's task. Subagents (background ones too) report under the parent's
    session id, so anything carrying an agent id is left out; so are Athos's own commands."""
    from_subagent = bool(event.get("agent_id"))
    return not from_subagent and _ATHOS_COMMAND.search(_command_of(event)) is None


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


# What the band's [Save] button sends, as the person's own short words: the save itself, for the task that just
# ended, not a new task. The prompt hook adds the instruction out of sight (SAVE_CONTEXT).
SAVE_PROMPT = {"en": "Athos · save: keep this task as a way of working",
               "es": "Athos · guardar: guardá esta tarea como forma de trabajar"}
SAVE_CONTEXT = ("The person pressed [Save]: keep what the task that just ended taught as exactly one way of working, "
                "with `{cmd} save` as the session guide says (improve the piece that task used, if it used one, with "
                "its id and a note). Reply in one short line, in the person's language; Athos shows what was saved.")


# [Adjust] on a step of the pane fills the prompt with this prefix and the step; the person writes the change.
ADJUST_PREFIX = {"en": "Athos · adjust", "es": "Athos · ajustar"}
# Muse Spark in OpenCode went looking for the piece in a skill folder synced from Claude Desktop (2026-10-30): the
# store is the only copy that counts, and `athos show` prints it. Its first save sent only the changed statement and
# dropped the rest.
ADJUST_CONTEXT = ("The person pressed [Adjust] on a step of their know-how and wrote how it should change. Read that "
                  "piece with `{cmd} show <id>` (the store is the only copy that counts; skill folders hold exports), "
                  "then improve it now with `{cmd} save` (its `id:` and a `note:` with the change): send every "
                  "statement of the piece, with only that one rewritten unless the change needs more (a save keeps "
                  "only what it is sent). Then go on with the task as changed. Reply in one short line, in the "
                  "person's language.")


def is_adjust_prompt(text: str) -> bool:
    return (text or "").lstrip().startswith(tuple(ADJUST_PREFIX.values()))


def is_save_prompt(text: str) -> bool:
    return (text or "").lstrip().startswith(("Athos · save:", "Athos · guardar:"))


def mentions_checklist(text: str) -> bool:
    """A checklist in the request: named as such, or three or more list items the person typed or pasted."""
    return bool(CHECKLIST.search(text or "")) or len(LIST_ITEM.findall(text or "")) >= 3


def note_request(event: dict) -> None:
    """UserPromptSubmit, after the task has started: remember whether this request works from a checklist."""
    prompt = event.get("prompt", "")
    # Per request, like the rest of capture. A list the person typed is new know-how even when a piece was loaded:
    # their own checklist on top of a generic one is exactly what the piece should learn.
    session.update(event.get("session_id", "default"), checklist=mentions_checklist(prompt),
                   checklist_typed=len(LIST_ITEM.findall(prompt)) >= 3 or bool(CHECKLIST_FILE.search(prompt)),
                   saved_in_request=False, offer=None)


def _bump(state: dict, counter: str) -> None:
    state[counter] = state.get(counter, 0) + 1


def _opens_checklist_file(tool_input: dict) -> bool:
    """The person's own checklist file, opened by the agent (a path argument, not a word in a command or a search)."""
    return any(CHECKLIST_FILE.search(str(tool_input.get(key, ""))) for key in ("file_path", "path", "filePath"))


def count_tool(event: dict) -> None:
    """PostToolUse: add one tool call to the request's tally (and to the work and edit tallies when it changed
    something). Running `athos save` instead closes the tally: the request's know-how is being kept."""
    sid = event.get("session_id", "default")
    tool_input = event.get("tool_input") or {}
    if not event.get("agent_id") and SAVE.search(str(tool_input.get("command", ""))):
        # The know-how of this request is being kept: nothing left to ask about until new work happens.
        session.update(sid, saved_in_request=True, tools_since_capture=0, work_since_capture=0, edits_since_capture=0,
                       checklist=False, checklist_typed=False)
        return
    if _is_persons_work(event):
        tally = session.load(sid)
        if _opens_checklist_file(tool_input):
            tally["checklist"] = tally["checklist_typed"] = True
        _bump(tally, "tools_since_capture")
        if _does_work(event):
            _bump(tally, "work_since_capture")
        if (event.get("tool_name") or "") in EDIT_TOOLS:
            _bump(tally, "edits_since_capture")
        session.save(sid, tally)


def enabled() -> bool:
    return os.environ.get("ATHOS_CAPTURE", "").lower() not in ("off", "0", "false", "no")


def _walked_known_way(state: dict) -> bool:
    """The task walked a way of working the person already has, step by step, and needed no step it lacks."""
    kinds = {entry.get("kind") for entry in state.get("trail") or []}
    return "step" in kinds and "new" not in kinds


def _followed_checklist(state: dict) -> bool:
    """A checklist drove the task and is worth keeping: no piece led it, or the person brought their own on top."""
    if not state.get("checklist"):
        return False
    return not state.get("task_loaded") or bool(state.get("checklist_typed"))


def _enough_work(state: dict) -> bool:
    """A file edited within enough tool calls, or several commands that changed something."""
    tools, work, edits = (state.get(k, 0) for k in ("tools_since_capture", "work_since_capture", "edits_since_capture"))
    return bool(edits and tools >= THRESHOLD) or work >= WORK_MIN


def _grounds_to_ask(state: dict) -> str:
    """Why the Stop hook should ask about this request: "checklist", "work", or "" for no reason at all.

    Nothing to ask when the request already saved, or when it only followed know-how the person has (a pasted
    contract's numbered clauses once read as the person's own checklist and asked: Codex, 2026-10-30). Otherwise a
    checklist the task followed, or real work, earns the question; reads and checks end quietly."""
    if state.get("saved_in_request") or _walked_known_way(state):
        return ""
    if _followed_checklist(state):
        return "checklist"
    return "work" if _enough_work(state) else ""


# The one line the Stop hook says when the session guide is already in context, by language and by whether the
# reason is a checklist. The person reads it too, so it follows their language.
_SHORT_ASK = {
    ("es", True): "Athos: esta tarea siguió un checklist, y eso es know-how valioso. Guardalo como forma de trabajar "
                  "con `{cmd} save`, como dice la guía de la sesión, o terminá.",
    ("en", True): "Athos: this task followed a checklist, which is know-how worth keeping. Save it as a piece with "
                  "`{cmd} save` as the session guide says, or just stop.",
    ("es", False): "Athos: ¿algo de esta tarea vale la pena guardar? Guardá o mejorá una forma de trabajar con "
                   "`{cmd} save` como dice la guía de la sesión, o terminá.",
    ("en", False): "Athos: anything reusable to keep? Save or improve one piece with `{cmd} save` as the session "
                   "guide says, or just stop.",
}


def _short_ask(cmd: str, checklist: bool) -> str:
    from athos import start
    lang = "es" if start.lang() == "es" else "en"
    return _SHORT_ASK[(lang, checklist)].format(cmd=cmd)


def _full_ask(cmd: str, checklist: bool, loaded: list[str]) -> str:
    """The self-contained request for sessions that never got the guide: why it asks, the format, and which loaded
    pieces to improve rather than duplicate."""
    opening = "Athos: this task followed a checklist, which is know-how worth keeping. " if checklist else "Athos: "
    ask = ("Before you stop, decide whether this task taught reusable know-how: how it was solved, the criteria, the "
           "steps, the mistakes avoided. If it did not, just stop. If it did, save exactly one piece by running:")
    closing = "Don't announce it: Athos shows the user what was saved."
    if loaded:
        closing += (f" Pieces loaded in this session: {', '.join(loaded)}. If this task refined one of them, improve "
                    f"it (give its id and a note) instead of creating a duplicate.")
    return opening + ask + "\n\n" + FORMAT.format(cmd=cmd) + "\n\n" + closing


def stop_decision(event: dict, cmd: str = "athos", offer: bool = False) -> dict | None:
    """The Stop hook's answer: `{"decision": "block", "reason": ...}` asks Claude to capture; None lets it stop.
    With `offer`, the model is not asked: the task is recorded as worth offering to save, and the band above the
    prompt shows the person a [Save] button (interactive Claude Code)."""
    if event.get("stop_hook_active") or not enabled():
        return None                      # never inside its own continuation, nor when the person turned it off
    session_id = event.get("session_id", "default")
    state = session.load(session_id)
    grounds = _grounds_to_ask(state)
    if grounds and offer:
        session.update(session_id, offer={"task_id": state.get("task_id"), "reason": grounds})
    if not grounds or offer:
        return None                      # quiet, or the band offers [Save] instead of asking the model
    # Asked once per stretch of work: the tallies start over.
    session.update(session_id, tools_since_capture=0, work_since_capture=0, edits_since_capture=0, checklist=False,
                   checklist_typed=False, asked=state.get("asked", 0) + 1)
    # With the guide given at session start (out of the user's sight, and again after a compaction), one line is
    # enough; otherwise the request carries the whole format.
    followed = grounds == "checklist"
    text = _short_ask(cmd, followed) if state.get("guide") else _full_ask(cmd, followed, state.get("loaded", []))
    return dict(decision="block", reason=text)
