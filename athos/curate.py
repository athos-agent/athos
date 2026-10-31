"""Curating the memory: proposals that keep the ways of working tidy as they grow, each applied only when the person
says so.

The long-term memory (the pages) grows a page at a time, and nothing tidied it: pages used in a project they aren't
tagged with (so per-project loading misses them), pages nobody used for weeks, near-duplicates, links to pages that
no longer exist, and work that keeps coming back in a project's journal with no page for it. `proposals()` finds
them from what Athos already keeps locally (the pages and the task log); `apply()` does the two that are mechanical
(tag a page with a project, archive a page) and the rest are advice the person acts on. Nothing is deleted: an
archived page moves to `<home>/archive/` and `restore()` brings it back.

Three lessons from an earlier memory-consolidation system: failures teach "don't" rules (the person's own
corrections become a proposed step), a page that keeps going wrong is flagged for review, and each pass is logged
(`<home>/curate.json`) so a proposal the person dismissed doesn't come back and new ones are marked as new. Tests and
rehearsals (tasks in temporary or demo folders, or projects the person ignores) never produce proposals.
"""

from __future__ import annotations

import re
import shutil
from collections import Counter, defaultdict
from itertools import combinations
from datetime import date, timedelta

import json
import time

from athos import cases, eval as ev, paths, store, wiki

IDLE_DAYS = 45            # a page unused this long is proposed for the archive
SIMILAR = 0.5             # share of title + "when" words two pages have in common to look like the same thing
REPEAT = 3                # requests in a project, with no page, sharing two words, before proposing one
MIN_WORDS = 6             # shorter requests are conversation ("como viene?", "mergea 50"), not work
STOP = set("""a an and the of to for in on with by from or at as is are be this that it its your my our their
de del la el los las y o en con por para un una que se su sus al lo como""".split())


REVIEW_BAD = 3            # corrected or failed tasks before a page that mostly goes wrong is flagged
# Project names that read as a test or a rehearsal; `athos curate ignore <project>` adds any other.
PLAY = re.compile(r"(^|[-_ ])(prueba|test|tests|demo|tmp|scratch|sandbox|example)([-_ ]|$)", re.I)


def archive_dir():
    return paths.home() / "archive"


def state_file():
    return paths.home() / "curate.json"


def state() -> dict:
    try:
        st = json.loads(state_file().read_text())
    except (OSError, ValueError):
        st = {}
    return {"last": st.get("last"), "seen": st.get("seen", []), "dismissed": st.get("dismissed", []),
            "ignore": st.get("ignore", [])}


def _save_state(st: dict) -> None:
    state_file().write_text(json.dumps(st, indent=1))


def key(p: dict) -> str:
    """What makes a proposal the same one in a later pass."""
    return "|".join(str(p.get(k)) for k in ("kind", "id", "ids", "project", "link", "words"))


def play_projects(tasks: list[dict] | None = None) -> set[str]:
    """Projects that are tests or rehearsals: named like one, ignored by the person, or with every task in a
    temporary or demo folder."""
    tasks = ev.tasks() if tasks is None else tasks
    by: dict[str, list[bool]] = defaultdict(list)
    for t in tasks:
        if t.get("project"):
            by[t["project"]].append(bool(t.get("scratch")))
    auto = {p for p, flags in by.items() if flags and all(flags)}
    return auto | {p for p in by if PLAY.search(p)} | set(state()["ignore"])


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-záéíóúñü0-9]+", text.lower()) if len(w) > 2 and w not in STOP}


def _used() -> tuple[dict[str, Counter], dict[str, str]]:
    """Where each page was really used, per project, and the last day it was: a step walked or the page read in a
    task, or the page saved by it. A page that only loaded doesn't count: loading by mistake would tag it wrong."""
    project = {t["task_id"]: t.get("project") for t in ev.tasks()}
    where: dict[str, Counter] = defaultdict(Counter)
    last: dict[str, str] = {}
    for e in ev.events():
        pid, tid = e.get("piece"), e.get("task_id")
        if e.get("type") == "trail" and e.get("kind") in ("step", "read") and pid and project.get(tid):
            where[pid][project[tid]] += 1
            last[pid] = max(last.get(pid, ""), (e.get("at") or "")[:10])
    for t in ev.tasks():
        for pid in t.get("saved") or []:
            if t.get("project"):
                where[pid][t["project"]] += 1
            last[pid] = max(last.get(pid, ""), (t.get("ended") or "")[:10])
        for pid in t.get("pieces") or []:                  # loaded: enough to say it is still around, not where
            last[pid] = max(last.get(pid, ""), (t.get("started") or "")[:10])
    return where, last


def proposals(all_: bool = False) -> list[dict]:
    """Everything worth tidying now, in a stable order: tags, rules from corrections, pages to review, archive,
    near-duplicates, broken links, missing pages. Dismissed ones are left out unless `all_`; each is marked `new` when
    a previous pass didn't show it."""
    st = state()
    play = play_projects()
    out = [p for p in _all_proposals(play)
           if all_ or key(p) not in st["dismissed"]]
    for p in out:
        p["new"] = bool(st["last"]) and key(p) not in st["seen"]
    return out


def mark_pass(shown: list[dict]) -> None:
    """Remember this pass: when, and what it showed (so the next one can say what is new)."""
    st = state()
    st["last"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    st["seen"] = sorted(set(st["seen"]) | {key(p) for p in shown})
    _save_state(st)


def dismiss(p: dict) -> None:
    st = state()
    st["dismissed"] = sorted(set(st["dismissed"]) | {key(p)})
    _save_state(st)


def ignore(project: str) -> None:
    st = state()
    st["ignore"] = sorted(set(st["ignore"]) | {project})
    _save_state(st)


def _all_proposals(play: set[str]) -> list[dict]:
    pieces = store.all_pieces()
    by = {p.id: p for p in pieces}
    where, last = _used()
    out: list[dict] = []
    for p in pieces:
        for proj, n in where.get(p.id, Counter()).most_common():
            if proj not in p.projects and proj not in play:
                out.append({"kind": "tag", "id": p.id, "project": proj,
                            "why": f"«{p.title}» was used {n} time{'s' if n > 1 else ''} in {proj}, which it isn't "
                                   f"tagged with: per-project loading leaves it out there"})
    out += _rules(pieces) + _reviews(pieces, play)
    called = {c["page"] for p in pieces for s in wiki.statements(p) for c in s.calls}
    cutoff = (date.today() - timedelta(days=IDLE_DAYS)).isoformat()
    for p in pieces:
        seen = max(last.get(p.id, ""), p.last_used or "", p.created or "")
        if seen and seen < cutoff and p.id not in called:
            out.append({"kind": "archive", "id": p.id,
                        "why": f"«{p.title}» hasn't been used since {seen}; archived pages don't load and come back "
                               f"with `athos curate restore {p.id}`"})
    heads = {p.id: _words(p.title + " " + p.when) for p in pieces}
    ids = sorted(heads)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if not heads[a] or not heads[b]:
                continue
            share = len(heads[a] & heads[b]) / len(heads[a] | heads[b])
            if share >= SIMILAR:
                out.append({"kind": "similar", "ids": [a, b],
                            "why": f"«{by[a].title}» and «{by[b].title}» look like the same way of working "
                                   f"({share:.0%} of their words in common): keep one, or link them"})
    for link in wiki.lint(pieces).get("broken", []):
        out.append({"kind": "link", "link": link, "why": f"{link} points to a page or step that doesn't exist"})
    out += _missing_pages(by, play)
    return out


def _owners() -> dict[str, str]:
    """The page each task mostly walked: the one with the most steps reported. A correction belongs to it, not to
    every page that loaded with it (a correction of an incident triage was proposed for the postmortem page too,
    which the task never opened, 2026-10-31). Tasks with no steps reported have no owner and keep every page."""
    steps: dict[str, Counter] = defaultdict(Counter)
    for e in ev.events():
        if e.get("type") == "trail" and e.get("kind") == "step" and e.get("piece") and e.get("task_id"):
            steps[e["task_id"]][e["piece"]] += 1
    return {tid: c.most_common(1)[0][0] for tid, c in steps.items()}


def _rules(pieces: list[store.Piece]) -> list[dict]:
    """Failures teach "don't" rules: corrections the person made after a task that followed a page, newer than the
    page's last version, proposed as a step for it, with the request that does it ready to paste."""
    from athos import capture, start
    prefix = capture.ADJUST_PREFIX["es" if start.lang() == "es" else "en"]
    owner = _owners()
    out = []
    for p in pieces:
        since = (p.history[0].split()[1] if p.history and len(p.history[0].split()) > 1 else p.created) or ""
        fixes = [" ".join(c["correction"].split())[:120] for c in cases.tests(p.id)
                 if (c.get("at") or "")[:10] >= since and owner.get(c.get("task_id"), p.id) == p.id]
        if fixes:
            quoted = "; ".join(f"«{f}»" for f in fixes[:3])
            out.append({"kind": "rule", "id": p.id,
                        "why": f"«{p.title}»: after {len(fixes)} task{'s' if len(fixes) > 1 else ''} you corrected "
                               f"with {quoted}; a «don't» step would keep it from happening again",
                        "request": f"{prefix} {p.id}: add a step with what not to do, from my corrections: {quoted}"})
    return out


def _reviews(pieces: list[store.Piece], play: set[str]) -> list[dict]:
    """A page that keeps going wrong: at least REVIEW_BAD tasks corrected or failed, more than twice the good ones."""
    tasks = [t for t in ev.tasks() if t.get("project") not in play]
    out = []
    for p in pieces:
        used = [t for t in tasks if p.id in (t.get("pieces") or [])]
        good = sum(t["result"] == "ok" for t in used)
        bad = sum(t["result"] in ("corrected", "failed") for t in used)
        if bad >= REVIEW_BAD and bad > 2 * good:
            out.append({"kind": "review", "id": p.id,
                        "why": f"«{p.title}» went wrong in {bad} tasks and well in {good}: read it again, fix or "
                               f"archive it"})
    return out


def _missing_pages(by: dict[str, store.Piece], play: set[str] = frozenset()) -> list[dict]:
    """Work that keeps coming back in a project with no page for it: requests (real ones, not "how is it going?" or
    "merge 50") that loaded nothing and share a pair of distinctive words. One proposal per project, its most
    repeated work: the first version proposed "mergea" and "como viene" (2026-10-31)."""
    from athos import journal
    out = []
    groups: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for t in ev.tasks():
        req = " ".join((t.get("request") or "").split())
        if (t.get("project") and t["project"] not in play and not t.get("pieces") and len(req.split()) >= MIN_WORDS
                and not journal.NOISE.match(req) and not req.startswith("<")):
            groups[t["project"]].append((req, {w for w in _words(req) if len(w) >= 5}))
    for proj, reqs in sorted(groups.items()):
        pairs = Counter(pair for _, ws in reqs for pair in combinations(sorted(ws), 2))
        if not pairs:
            continue
        (w1, w2), n = pairs.most_common(1)[0]
        if n < REPEAT:
            continue
        sample = [r[:60] for r, ws in reqs if w1 in ws and w2 in ws][:3]
        out.append({"kind": "new", "project": proj, "words": [w1, w2],
                    "why": f"in {proj}, {n} requests about «{w1} {w2}» followed no way of working (e.g. "
                           + "; ".join(f"«{x}»" for x in sample) + "): save one the next time it comes up"})
    return out


def apply(p: dict) -> str:
    """Do a mechanical proposal: tag a page with a project (a new version) or archive it. The rest is advice."""
    if p["kind"] == "tag":
        page, _ = store.update(p["id"], f"curate: also for project {p['project']}", projects=[p["project"]])
        return f"«{page.title}» now loads in {p['project']} too (v{page.version})"
    if p["kind"] == "archive":
        src = store.get(p["id"])
        if src is None:
            raise KeyError(p["id"])
        archive_dir().mkdir(parents=True, exist_ok=True)
        shutil.move(str(src.path), str(archive_dir() / f"{src.id}.md"))
        return f"«{src.title}» archived; `athos curate restore {src.id}` brings it back"
    raise ValueError("this one is advice: act on it yourself (athos show, athos save)")


def restore(piece_id: str) -> str:
    f = archive_dir() / f"{piece_id}.md"
    if not f.is_file():
        raise KeyError(piece_id)
    if (paths.know_how() / f.name).exists():
        raise FileExistsError(f"a page {piece_id} already exists")
    shutil.move(str(f), str(paths.know_how() / f.name))
    return f"«{store.get(piece_id).title}» is back"
