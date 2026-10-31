"""The know-how as a wiki: pages, statements, links, an index, and the trajectories they make.

A piece is a page. Its body is a list of **statements**, the smallest unit you can check:

    ## #run_guard
    **When:** about to commit or push to the public repo.
    **Do:** run `python3 tools/guard.py .` and stop on any finding.
    **Because:** a private name reached a public PR once.
    **Links:** [[bump-the-plugin-version#bump]] · [[land-a-change#open_pr]]

Links are trajectories, not topics: a statement links to what applies **next or alongside** it in a real task, so a
task is done by walking: the index → the entry statement → its links, while they apply. `[[page]]` and
`[[page#statement]]` are the same links Obsidian reads, so `~/.athos/know-how` opens as a wiki there.

A step can hand over to another page, the way work is modular: `**Calls:** [[page]]` runs that page's statements
as sub-steps and comes back; `**If:** <condition> → [[page]]` does it only when the condition holds (a contract over
$50k → the deep guarantee audit). The trail shows the sub-steps under the step that called them.

Older pieces (numbered steps, no statements) still load and walk as one block; the lint lists them to convert.

`Index.md` (rebuilt on every save) lists each situation and where its walk starts. A walk that reaches more than one
page is a **trajectory**, and each trajectory becomes a subagent in markdown (`<home>/agents/athos-<page>.md`),
regenerated whenever one of its pages improves, so the agents evolve with the know-how they walk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from athos import paths, store

INDEX = "Index.md"
STATEMENT = re.compile(r"^## #([a-z0-9][a-z0-9_-]*)\s*$", re.M)
FIELD = re.compile(r"^\*\*(When|Do|Because|Links|Calls|If):\*\*\s*(.*)$", re.M)
LINK = re.compile(r"\[\[([a-z0-9][a-z0-9-]*)(?:#([a-z0-9][a-z0-9_-]*))?(?:\|[^\]]*)?\]\]")
AGENT_PREFIX = "athos-"
OVERLAP = 0.4          # share of the words two **When** lines have in common to call them the same moment
STALE_DAYS = 30
STOPWORDS = set("the a an and or to of in on for with when about is are be it its this that from by as at into after "
                "before any your you user asked asks ask".split())


@dataclass
class Statement:
    page: str
    id: str
    when: str = ""
    do: str = ""
    because: str = ""
    links: list[tuple[str, str | None]] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)   # [{"page", "statement", "if"}]: the sub-routines of this step

    @property
    def ref(self) -> str:
        return f"{self.page}#{self.id}"


def statements(p: store.Piece) -> list[Statement]:
    """The page's statements in order. A page without them is one implicit statement, `#steps`, holding the body."""
    parts = STATEMENT.split(p.body)
    if len(parts) == 1:
        return [Statement(p.id, "steps", p.when, p.body.strip(), "", LINK.findall(p.body))]
    out = []
    for sid, text in zip(parts[1::2], parts[2::2]):
        f = {k.lower(): v.strip() for k, v in FIELD.findall(text)}
        out.append(Statement(p.id, sid, f.get("when", ""), f.get("do", ""), f.get("because", ""), LINK.findall(text),
                             calls_of(f.get("calls", ""), f.get("if", ""))))
    return out


def calls_of(calls: str, cond: str) -> list[dict]:
    """The pages a step hands over to: every link of `**Calls:**`, and those after the arrow of `**If:**`, with the
    condition that sends the task there."""
    out = [{"page": pg, "statement": st or None, "if": ""} for pg, st in LINK.findall(calls)]
    if cond:
        head, _, tail = re.split(r"\s*(→|->|=>)\s*", cond, maxsplit=1) if re.search(r"→|->|=>", cond) else ("", "", cond)
        why = LINK.sub("", head).strip().rstrip(":,")
        out += [{"page": pg, "statement": st or None, "if": why} for pg, st in LINK.findall(tail)]
    return out


def is_wiki(p: store.Piece) -> bool:
    return bool(STATEMENT.search(p.body))


def links_of(p: store.Piece) -> list[str]:
    """The pages this one leads to, in order of first mention, itself left out."""
    seen: list[str] = []
    for page, _ in LINK.findall(p.body):
        if page != p.id and page not in seen:
            seen.append(page)
    return seen


def walk(start: str, pages: dict[str, store.Piece], limit: int = 8) -> list[str]:
    """The trajectory from a page: depth-first along its links, in the order written, each page once."""
    out: list[str] = []

    def go(pid: str) -> None:
        if pid in out or pid not in pages or len(out) >= limit:
            return
        out.append(pid)
        for nxt in links_of(pages[pid]):
            go(nxt)
    go(start)
    return out


def lint(pieces: list[store.Piece] | None = None) -> dict:
    """What keeps the wiki navigable: links that resolve, unique statement ids, pages reachable from the index (an
    entry page, or linked from one), and which pages still use the old numbered format."""
    pieces = store.all_pieces() if pieces is None else pieces
    pages = {p.id: p for p in pieces}
    broken, dupes = [], []
    for p in pieces:
        ids = [s.id for s in statements(p)]
        dupes += [f"{p.id}#{i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
        for page, sid in LINK.findall(p.body):
            target = pages.get(page)
            if target is None or (sid and sid not in {s.id for s in statements(target)}):
                broken.append(f"{p.id} → [[{page}{'#' + sid if sid else ''}]]")
    linked_to = {t for p in pieces for t in links_of(p)}
    return {"pages": len(pieces), "statements": sum(len(statements(p)) for p in pieces),
            "links": sum(len(links_of(p)) for p in pieces), "broken": broken, "duplicate_ids": dupes,
            "entries": sorted(pages.keys() - linked_to),
            "old_format": sorted(p.id for p in pieces if not is_wiki(p))}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_]{3,}", text.lower())} - STOPWORDS


def overlaps(piece: store.Piece, pieces: list[store.Piece] | None = None) -> list[str]:
    """Statements of other pages, in the same project, for the same moment as one of this page's statements, that
    neither links to the other. Two pages saying what to do at the same moment can contradict each other: the agent
    that saved this page checks they agree, and keeps what is right in one place (the save reports them in the same
    turn; nothing is overwritten)."""
    pieces = store.all_pieces() if pieces is None else pieces
    projects = set(piece.projects)
    out = []
    for s in statements(piece):
        ws = _words(s.when)
        if s.id == "steps" or len(ws) < 3:
            continue
        for p in pieces:
            if p.id == piece.id or (projects and p.projects and not projects & set(p.projects)):
                continue
            for o in statements(p):
                wo = _words(o.when)
                if o.id == "steps" or len(wo) < 3 or len(ws & wo) / len(ws | wo) < OVERLAP:
                    continue
                if (o.page, o.id) in s.links or (o.page, None) in s.links or (s.page, s.id) in o.links:
                    continue                                   # linked on purpose: applied together
                out.append(f"{s.ref} ~ {o.ref}")
    return out


def stale(pieces: list[store.Piece] | None = None, tasks: list[dict] | None = None,
          today: str | None = None) -> list[str]:
    """Candidates to retire, from the recorded tasks (nothing is removed): pages no task loaded in the last
    STALE_DAYS days, pages whose marked tasks mostly failed, and links between pages that were never loaded together
    although the first one was, three times or more since the version that wrote the link."""
    import datetime as dt
    from athos import eval as ev
    pieces = store.all_pieces() if pieces is None else pieces
    tasks = ev.tasks() if tasks is None else tasks
    day = dt.date.fromisoformat(today) if today else dt.date.today()
    cutoff = (day - dt.timedelta(days=STALE_DAYS)).isoformat()
    out = []
    for p in sorted(pieces, key=lambda p: p.id):
        used = [t for t in tasks if p.id in t.get("pieces", [])]
        if p.created and p.created <= cutoff and not any((t.get("started") or "") >= cutoff for t in used):
            out.append(f"{p.id}: not loaded in {STALE_DAYS} days")
        marked = [t for t in used if t.get("result") in ("ok", "corrected", "failed")]
        if len(marked) >= 3 and sum(t["result"] == "failed" for t in marked) * 2 > len(marked):
            out.append(f"{p.id}: most of its {len(marked)} marked tasks failed")
        # A link counts only from the version that wrote it: tasks before it could not follow it.
        since = next((m.group(1) for h in p.history[:1] for m in [re.match(r"v\d+ (\d{4}-\d{2}-\d{2})", h)] if m),
                     p.created or "")
        after = [t for t in used if (t.get("started") or "")[:10] > since]   # the day after: history keeps dates only
        if len(after) >= 3:
            for nxt in links_of(p):
                if not any(nxt in t.get("pieces", []) for t in after):
                    out.append(f"{p.id} → {nxt}: never loaded together in {len(after)} tasks since v{p.version}")
    return out


def dataset(pieces: list[store.Piece] | None = None, tasks: list[dict] | None = None) -> list[dict]:
    """The know-how as data to evaluate or specialise a model on: one row per statement (what to do at which moment,
    and why, with how the tasks that used its page turned out) and one row per marked task (the request, the pages it
    used, the agent and model, and your mark). Unmarked tasks are left out: their outcome is unknown."""
    from athos import eval as ev
    pieces = store.all_pieces() if pieces is None else pieces
    tasks = ev.tasks() if tasks is None else tasks
    marked = [t for t in tasks if t.get("result") in ("ok", "corrected", "failed")]
    rows: list[dict] = []
    for p in sorted(pieces, key=lambda p: p.id):
        outcome = {r: sum(1 for t in marked if p.id in t.get("pieces", []) and t["result"] == r)
                   for r in ("ok", "corrected", "failed")}
        for st in statements(p):
            rows.append({"kind": "statement", "page": p.id, "id": st.id, "title": p.title, "version": p.version,
                         "projects": p.projects, "when": st.when, "do": st.do, "because": st.because,
                         "links": [f"{pg}#{sid}" if sid else pg for pg, sid in st.links], "outcome": outcome})
    for t in sorted(marked, key=lambda t: t.get("started") or ""):
        rows.append({"kind": "task", "task_id": t["task_id"], "request": t.get("request", ""),
                     "pieces": t.get("pieces", []), "saved": t.get("saved", []), "platform": t.get("platform"),
                     "model": t.get("model"), "project": t.get("project"), "result": t["result"],
                     "started": t.get("started")})
    return rows


def index_text(pieces: list[store.Piece] | None = None) -> str:
    """`Index.md`: per project, each situation and the statement its walk starts at; then the trajectories."""
    pieces = store.all_pieces() if pieces is None else pieces
    pages = {p.id: p for p in pieces}
    by_project: dict[str, list[store.Piece]] = {}
    for p in sorted(pieces, key=lambda p: p.title.lower()):
        by_project.setdefault((p.projects or ["(any project)"])[0], []).append(p)
    out = ["# Index", "", "Where a task starts: each page and the situation it is for. A walk begins at the page's first",
           "statement and follows its links while they apply. Rebuilt by Athos on every save: edit the pages, not",
           "this file.", ""]
    for project in sorted(by_project):
        out += [f"## {project}", ""]
        for p in by_project[project]:
            first = statements(p)[0]
            out.append(f"- **[[{p.id}#{first.id}|{p.title}]]**: {p.when}")
        out.append("")
    trails = trajectories(pieces)
    if trails:
        out += ["## Trajectories", "", "Walks that cross pages; each one is also a subagent (`athos-<page>`).", ""]
        for start, trail in trails.items():
            out.append("- " + " → ".join(f"[[{pid}|{pages[pid].title}]]" for pid in trail))
        out.append("")
    return "\n".join(out)


def trajectories(pieces: list[store.Piece] | None = None) -> dict[str, list[str]]:
    """Every walk that reaches more than one page, keyed by the page it starts from. Entry pages (nothing links to
    them) start one, so a trajectory is the whole chain, never its tail again; a loop with no entry page starts at
    the page that reaches the most."""
    pieces = store.all_pieces() if pieces is None else pieces
    pages = {p.id: p for p in pieces}
    linked_to = {t for p in pieces for t in links_of(p)}
    out, covered = {}, set()
    for pid in sorted(pages.keys() - linked_to):
        trail = walk(pid, pages)
        if len(trail) > 1:
            out[pid] = trail
            covered |= set(trail)
    # Pages that only link in a loop (A ↔ B) have no entry page: start from the one that leads to the most pages.
    rest = sorted((pid for pid in pages if pid not in covered and links_of(pages[pid])),
                  key=lambda pid: (-len(walk(pid, pages)), pid))
    for pid in rest:
        if pid in covered:
            continue
        trail = walk(pid, pages)
        if len(trail) > 1:
            out[pid] = trail
            covered |= set(trail)
    return out


def agent_text(trail: list[str], pages: dict[str, store.Piece]) -> str:
    """A subagent in markdown (Claude Code's format) that walks one trajectory of the person's know-how."""
    head = pages[trail[0]]
    desc = (f"{head.title}. Use when: {head.when}. Walks the person's know-how: "
            + " → ".join(pages[pid].title for pid in trail)).replace("\n", " ")
    versions = ", ".join(f"{pid} v{pages[pid].version}" for pid in trail)
    out = ["---", f"name: {AGENT_PREFIX}{head.id}", f"description: {store._quote(desc)}", "---", "",
           f"<!-- Generated by Athos from {versions}. It is rebuilt whenever one of these pages improves: edit the "
           "pages in ~/.athos/know-how, not this file. -->", "",
           "You carry out one kind of task the way the person does it, from their own know-how. Walk the statements "
           "below in order, following a link only while its **When** applies. Cite each statement you follow as "
           "`[[page#id]]` in your report, and list every decision you left to the person instead of making it.", ""]
    for pid in trail:
        p = pages[pid]
        out += [f"## {p.title} (`{pid}`)", f"When: {p.when}", ""]
        for s in statements(p):
            if s.id == "steps":
                out += [s.do, ""]
                continue
            out.append(f"### [[{s.ref}]]")
            out += [f"**{k}:** {v}" for k, v in (("When", s.when), ("Do", s.do), ("Because", s.because)) if v]
            out.append("")
    out += ["## Before you hand back", "",
            "- Every statement whose When applied was followed, or you say why not.",
            "- Nothing the know-how leaves to the person (a choice, a budget, a tolerance) was decided by you.",
            "- If the task taught something these pages lack, say so in one line: the person's next session can add "
            "it, and this agent is rebuilt from the improved pages.", ""]
    return "\n".join(out)


def agents_dir() -> Path:
    return paths.home() / "agents"


def rebuild(pieces: list[store.Piece] | None = None) -> dict:
    """Index.md and the trajectory subagents, from the pages as they are now. Removes agents of trajectories that no
    longer exist. Returns what changed and the lint."""
    pieces = store.all_pieces() if pieces is None else pieces
    pages = {p.id: p for p in pieces}
    d = paths.know_how()
    d.mkdir(parents=True, exist_ok=True)
    (d / INDEX).write_text(index_text(pieces))
    trails = trajectories(pieces)
    adir = agents_dir()
    adir.mkdir(parents=True, exist_ok=True)
    keep, written = set(), []
    for start, trail in trails.items():
        f = adir / f"{AGENT_PREFIX}{start}.md"
        keep.add(f.name)
        text = agent_text(trail, pages)
        if not f.exists() or f.read_text() != text:
            f.write_text(text)
            written.append(f.name)
    removed = []
    for f in adir.glob(f"{AGENT_PREFIX}*.md"):
        if f.name not in keep:
            f.unlink()
            removed.append(f.name)
    try:
        retire = stale(pieces)
    except (OSError, ValueError):
        retire = []
    return {"agents": sorted(keep), "written": written, "removed": removed, "lint": lint(pieces), "stale": retire}


def agents_target() -> Path | None:
    """Where the person chose to install the trajectory agents (`athos wiki agents --install`), if they did."""
    try:
        t = (paths.home() / "agents-install").read_text().strip()
    except OSError:
        return None
    return Path(t) if t else None


def install_agents(dest: Path | None = None) -> int:
    """Copy the trajectory agents where Claude Code finds subagents (default ~/.claude/agents). Only Athos's own
    `athos-*.md` files are written or removed there."""
    dest = dest or Path.home() / ".claude" / "agents"
    dest.mkdir(parents=True, exist_ok=True)
    src = {f.name: f.read_text() for f in agents_dir().glob(f"{AGENT_PREFIX}*.md")}
    for name, text in src.items():
        (dest / name).write_text(text)
    for f in dest.glob(f"{AGENT_PREFIX}*.md"):
        if f.name not in src and "Generated by Athos" in f.read_text():
            f.unlink()
    return len(src)
